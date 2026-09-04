"""
GOREV G / O5 -- get_global_position()'in irtifa bileseni datum'u.

OLCULEN KUSUR (docs/gorevG-O5-datum-mekanizma.md): sistem kendi icinde
tutarsizdi --
  SETPOINT : goto_position_ned_and_hold(n, e, -alt, ...)  NED / EKF-ORIJINI
  OKUMA    : get_global_position()[2] = relative_altitude_m  HOME-REFERANSLI
Fark ref_alt - home.alt kadar; iki kosumda -0.1768 / -0.1786 m olculdu ve
jsonl'den olculen -0.177 / -0.179 ile 1 mm'nin altinda ortustu. Kayma
0.16 m'den 16 m'ye kadar SABIT (carpan degil, referans hatasi).

Bu dosya, okumanin SETPOINT'lerle ayni cerceveden geldigini korur.
"""
import pytest

from mocks.mock_flight_backend import MockFlightBackend


class _Pos:
    def __init__(self, lat, lon, rel):
        self.latitude_deg = lat
        self.longitude_deg = lon
        self.relative_altitude_m = rel


class _NedPos:
    def __init__(self, n, e, d):
        self.position = type("P", (), {"north_m": n, "east_m": e, "down_m": d})()


class _Backend:
    """Gercek MavsdkBackendBase.get_global_position govdesini kosturur;
    yalnizca onbellek/tazelik katmanini yerine koyar."""
    def __init__(self, rel_alt, down_m):
        self._position = _Pos(47.4, 8.5, rel_alt)
        self._position_velocity_ned = _NedPos(1.0, 2.0, down_m)

    @staticmethod
    def _fresh(x, *a, **k):
        return x

    from mavsdk_common.mavsdk_backend_base import MavsdkBackendBase as _B
    get_global_position = _B.get_global_position
    get_position_ned = _B.get_position_ned


@pytest.mark.asyncio
async def test_irtifa_NED_kaynagindan_gelir_relative_altitude_DEGIL():
    """Olculen vaka: EKF -z = 0.301 iken relative_altitude_m = 0.123."""
    b = _Backend(rel_alt=0.123, down_m=-0.301)
    lat, lon, alt = await b.get_global_position()
    assert alt == pytest.approx(0.301), "relative_altitude_m'e dusuldu"
    assert lat == 47.4 and lon == 8.5, "lat/lon kaynagi degismemeli"


@pytest.mark.asyncio
async def test_okuma_ile_SETPOINT_ayni_cerceveden():
    """get_position_ned()[2] setpoint'in cercevesi; okuma onun negatifi
    olmali -- iki cerceve bir daha karismasin."""
    b = _Backend(rel_alt=0.123, down_m=-0.301)
    _, _, alt = await b.get_global_position()
    _, _, down = await b.get_position_ned()
    assert alt == pytest.approx(-down)


@pytest.mark.asyncio
async def test_datum_kaymasi_artik_okumaya_BINMIYOR():
    """relative_altitude_m ne olursa olsun okuma degismemeli."""
    a = await _Backend(rel_alt=0.123, down_m=-0.301).get_global_position()
    b = await _Backend(rel_alt=99.0, down_m=-0.301).get_global_position()
    assert a[2] == b[2] == pytest.approx(0.301)


@pytest.mark.asyncio
async def test_yerdeyken_ve_yuksekte_isaret_dogru():
    """NED down pozitif = asagi; irtifa = -down."""
    assert (await _Backend(0.0, down_m=0.0).get_global_position())[2] == pytest.approx(0.0)
    assert (await _Backend(0.0, down_m=-15.0).get_global_position())[2] == pytest.approx(15.0)


@pytest.mark.asyncio
async def test_mock_backend_hala_tutarli():
    """Mock, iki kaynagi da tasiyor ve tutarli olmali -- yoksa testlerin
    tamami gercek kod yolunu yanlis taklit eder."""
    m = MockFlightBackend()
    _, _, alt = await m.get_global_position()
    _, _, down = await m.get_position_ned()
    assert alt == pytest.approx(-down), (
        f"mock tutarsiz: get_global_position={alt}, get_position_ned down={down}")
