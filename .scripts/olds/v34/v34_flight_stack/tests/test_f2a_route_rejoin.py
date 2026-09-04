"""Görev F2-a -- ROUTE REJOIN kod yolunun ILK testleri.

NEDEN VAR: ENABLE_ROUTE_REJOIN bastan beri False oldugu icin
_detect_route_axis() / _rejoin_route_axis() HIC CALISMAMISTI -- ne testte, ne
SITL'de, ne ucusta. Bayragi acmak bu yolu ILK KEZ calistirmak demek. Bu dosya
bes senaryoyu cakiyor:

  1. eksen tespiti  -- rotanin KENDI koordinatlarindan, varsayimsiz
  2. yanal duzeltme -- DOGRU eksene uygulaniyor, digeri mevcut konumda kaliyor
  3. no-op halleri  -- eksen yok / pre-pursuit konumu yok
  4. zaman asimi    -- rejoin basarisiz olsa bile resume DEVAM EDER
  5. madde 2 guard'i -- Offboard'a GIRILMEDIYSE hic denenmez
"""
import pytest

from core.config.parameters import MISSION_ALTITUDE_M, ROUTE_REJOIN_TIMEOUT_S
from core.mission.gorev2_orchestrator import Gorev2Orchestrator


class _Item:
    def __init__(self, seq, command, x, y):
        self.seq, self.command, self.x, self.y = seq, command, x, y


def _wp(seq, lat, lon):
    return _Item(seq, 16, int(lat * 1e7), int(lon * 1e7))


class _Flight:
    def __init__(self, items=None, pos=(47.0, 8.0, 15.0)):
        self._items = items or []
        self._pos = pos
        self.stopped = False

    async def get_raw_mission_items(self):
        return self._items

    async def get_global_position(self):
        return self._pos

    async def stop_offboard(self):
        self.stopped = True


class _Centering:
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    async def goto_global_position_and_wait(self, lat, lon, alt, timeout_s=None):
        self.calls.append({"lat": lat, "lon": lon, "alt": alt, "timeout_s": timeout_s})
        return self.result


def _orch(flight=None, centering=None, axis=None, pre=(None, None), engaged=True):
    o = Gorev2Orchestrator.__new__(Gorev2Orchestrator)
    o.flight = flight or _Flight()
    o.centering = centering or _Centering()
    o._route_axis = axis
    o._pre_pursuit_lat, o._pre_pursuit_lon = pre
    o._offboard_engaged = engaged
    o.published = []
    o._publish = lambda code, msg="", severity=None, category=None, data=None: \
        o.published.append((code, data or {}))
    return o


# --- 1. eksen tespiti -------------------------------------------------------

@pytest.mark.asyncio
async def test_axis_detection_picks_the_axis_the_route_holds_fixed():
    """Rota kuzeye gidiyor (lat degisiyor, lon sabit) -> SABIT eksen 'lon'."""
    o = _orch(_Flight(items=[_wp(1, 47.3978, 8.5462), _wp(2, 47.3990, 8.5462)]))
    assert await o._detect_route_axis() == "lon"
    codes = [c for c, _ in o.published]
    assert "ROUTE_AXIS_DETECTED" in codes


@pytest.mark.asyncio
async def test_axis_detection_works_the_other_way_round_too():
    """Varsayim yapmiyor: dogu-bati rotada SABIT eksen 'lat' olmali."""
    o = _orch(_Flight(items=[_wp(1, 47.3978, 8.5450), _wp(2, 47.3978, 8.5480)]))
    assert await o._detect_route_axis() == "lat"


@pytest.mark.asyncio
async def test_axis_detection_refuses_a_route_it_cannot_interpret():
    """Global cerceve degilse ya da 2'den az waypoint varsa None -- rejoin
    yorumlayamadigi bir rotayi tehlikeye donusturmemeli."""
    o = _orch(_Flight(items=[_wp(1, 47.3978, 8.5462)]))
    assert await o._detect_route_axis() is None
    bad = _Item(1, 16, int(999.0 * 1e7), int(999.0 * 1e7))
    o2 = _orch(_Flight(items=[bad, _wp(2, 47.3978, 8.5462)]))
    assert await o2._detect_route_axis() is None


# --- 2. yanal duzeltme ------------------------------------------------------

@pytest.mark.asyncio
async def test_rejoin_restores_only_the_fixed_axis():
    """SABIT eksen pre-pursuit degerine doner; SEYAHAT ekseni MEVCUT konumda
    kalir -- yani yanal duzeltme, onceki bir noktaya donus DEGIL."""
    cen = _Centering()
    o = _orch(_Flight(pos=(47.3995, 8.5450, 3.0)), cen,
              axis="lon", pre=(47.3980, 8.5462))
    await o._rejoin_route_axis()
    assert len(cen.calls) == 1
    call = cen.calls[0]
    assert call["lon"] == 8.5462, "sabit eksen geri gelmedi"
    assert call["lat"] == 47.3995, "seyahat ekseni mevcut konumda kalmaliydi"


@pytest.mark.asyncio
async def test_rejoin_targets_route_cruise_altitude_not_the_descended_one():
    """Hatta donmek 3 boyutlu: merkezleme icin alcalmis irtifa degil, rotanin
    kendi seyir irtifasi hedeflenir."""
    cen = _Centering()
    o = _orch(_Flight(pos=(47.3995, 8.5450, 3.0)), cen, axis="lon", pre=(47.3980, 8.5462))
    await o._rejoin_route_axis()
    assert cen.calls[0]["alt"] == MISSION_ALTITUDE_M
    assert cen.calls[0]["timeout_s"] == ROUTE_REJOIN_TIMEOUT_S


@pytest.mark.asyncio
async def test_rejoin_handles_the_lat_fixed_case():
    cen = _Centering()
    o = _orch(_Flight(pos=(47.3995, 8.5450, 15.0)), cen, axis="lat", pre=(47.3980, 8.5462))
    await o._rejoin_route_axis()
    assert cen.calls[0]["lat"] == 47.3980 and cen.calls[0]["lon"] == 8.5450


# --- 3. no-op halleri -------------------------------------------------------

@pytest.mark.asyncio
async def test_rejoin_is_a_noop_without_a_detected_axis():
    cen = _Centering()
    o = _orch(centering=cen, axis=None, pre=(47.398, 8.546))
    await o._rejoin_route_axis()
    assert cen.calls == []


@pytest.mark.asyncio
async def test_rejoin_is_a_noop_without_a_pre_pursuit_position():
    cen = _Centering()
    o = _orch(centering=cen, axis="lon", pre=(None, None))
    await o._rejoin_route_axis()
    assert cen.calls == []


# --- 4. zaman asimi resume'u DURDURMAZ --------------------------------------

@pytest.mark.asyncio
async def test_timeout_is_reported_but_never_blocks_the_resume():
    """Best-effort: rejoin zaman asimina ugrasa bile normal resume surer."""
    cen = _Centering(result=False)
    o = _orch(_Flight(pos=(47.3995, 8.5450, 15.0)), cen, axis="lon", pre=(47.3980, 8.5462))
    await o._rejoin_route_axis()          # istisna FIRLATMAMALI
    codes = [c for c, _ in o.published]
    assert "ROUTE_REJOIN_TIMED_OUT" in codes
    assert "ROUTE_REJOIN_DONE" not in codes


@pytest.mark.asyncio
async def test_position_read_failure_degrades_to_noop():
    class _Bad(_Flight):
        async def get_global_position(self):
            raise RuntimeError("stale")
    cen = _Centering()
    o = _orch(_Bad(), cen, axis="lon", pre=(47.3980, 8.5462))
    await o._rejoin_route_axis()
    assert cen.calls == []


# --- 5. MADDE 2 GUARD'I -----------------------------------------------------

@pytest.mark.asyncio
async def test_rejoin_is_skipped_when_offboard_was_never_engaged():
    """F1 basarisizlik yolu: gecis basarisiz oldugu icin arac HOLD'da ve
    rotadan HIC AYRILMADI. Rejoin denenirse 15 s bosa beklenir."""
    cen = _Centering()
    o = _orch(_Flight(pos=(47.3995, 8.5450, 15.0)), cen,
              axis="lon", pre=(47.3980, 8.5462), engaged=False)
    await o._rejoin_route_axis()
    assert cen.calls == [], "Offboard'a girilmemisken rejoin denendi -- 15 s bosa gider"
    codes = [c for c, _ in o.published]
    assert "ROUTE_REJOIN_SKIPPED" in codes
    assert dict(o.published)["ROUTE_REJOIN_SKIPPED"]["reason"] == "offboard_never_engaged"


@pytest.mark.asyncio
async def test_guard_does_not_block_the_normal_engaged_path():
    """Guard yalnizca F1 halini kesmeli; normal yolda rejoin CALISMALI."""
    cen = _Centering()
    o = _orch(_Flight(pos=(47.3995, 8.5450, 15.0)), cen,
              axis="lon", pre=(47.3980, 8.5462), engaged=True)
    await o._rejoin_route_axis()
    assert len(cen.calls) == 1
    assert "ROUTE_REJOIN_SKIPPED" not in [c for c, _ in o.published]
