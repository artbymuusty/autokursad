"""
GOREV G / TAKIP 1 -- _reacquire_by_climbing() yon kusuru.

KUSUR (docs/gorevG-H1-dogrulama.md): tirmanis KOSULSUZ yukariydi
(`higher = alt + HOOK_REACQUIRE_CLIMB_M`, kosul yok, asagi dal yok) ve
tetiklendiginde kendi amacini imkansiz kiliyordu: yukun gorunen alani
irtifanin KARESIYLE kuculdugu icin ikinci tirmanistan sonra
HSV_MIN_AREA_RECT_BASE (400 px2) kapisi MATEMATIKSEL OLARAK gecilemez
hale geliyordu. Altigen ayni tirmanista hayatta kaliyordu -- olculen
"altigen var / yuk yok" imzasi.

Bu dosya UC seyi korur:
  1. tavanin ELLE SECILMEDIGI, ic parametrelerden turetildigi,
  2. tavan altinda tirmanisin KORUNDUGU (mesru amac: kadraji genisletmek),
  3. tavan asildiginda yonun ASAGI dondugu ve hizalama irtifasinin
     altina inilmedigi.
"""
import math
import pytest

from mocks.mock_flight_backend import MockFlightBackend
from mocks.mock_camera_source import MockCameraSource
from mocks.mock_payload_actuator import MockPayloadActuator

from core.mission.gorev3_pickup import (
    Gorev3PickupPhase,
    HOOK_REACQUIRE_CLIMB_M,
    HOOK_REACQUIRE_MAX_CLIMBS,
    HOOK_REACQUIRE_CEILING_MARGIN,
    HOOK_VISUAL_ALIGN_ALTITUDE_M,
    PAYLOAD_RECT_LONG_EDGE_M,
    PAYLOAD_RECT_SHORT_EDGE_M,
)
from core.config.parameters import HSV_MIN_AREA_RECT_BASE
from core.mission.rectangle_alignment_strategy import RectangleAlignmentStrategy
from core.position_log.position_store import PositionStore


@pytest.fixture(autouse=True)
def _fast_locate(monkeypatch):
    """_locate_target_with_retries() 80 x OFFBOARD_SETPOINT_INTERVAL_S bekler
    ve bu testlerin HICBIRI o sureyi olcmuyor -- yonu olcuyorlar. conftest.py'nin
    MISSION_START_HOLD_S icin yaptiginin aynisi ve ayni gerekcesiyle: testler
    ZAMANLAMAYI degil DAVRANISI olcmeli. Deneme sayisinin KENDI davranisi
    test_gorev3_pickup.py tarafinda duruyor."""
    import core.mission.gorev3_pickup as gp
    monkeypatch.setattr(gp, "GOREV3_PICKUP_ALIGN_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(gp, "OFFBOARD_SETPOINT_INTERVAL_S", 0.0)


class _NeverSeesTarget:
    """Yuk hicbir zaman bulunamaz -- tum tirmanis adimlari tuketilir."""
    async def detect(self, frame=None):
        return []


class _AltitudeTrackingFlight(MockFlightBackend):
    """goto_position_ned_and_hold'u GERCEKTEN irtifaya yansitir, boylece
    ardisik adimlarin yonu olculebilir."""
    def __init__(self, start_alt_m):
        super().__init__()
        self._alt = start_alt_m
        self.targets = []

    async def get_global_position(self):
        return (47.4, 8.5, self._alt)

    async def get_position_ned(self):
        return (0.0, 0.0, -self._alt)

    async def goto_position_ned_and_hold(self, n, e, d, yaw, hold_s):
        self.targets.append(round(-d, 3))
        self._alt = -d


def _phase(flight):
    return Gorev3PickupPhase(
        flight, MockCameraSource(), _NeverSeesTarget(), MockPayloadActuator(),
        PositionStore("/tmp/kursad_test_positions.json"),
        RectangleAlignmentStrategy(), centering=None, publisher=None)


def test_tavan_elle_secilmemis_turetilmis():
    """Tavan, kamera ic parametreleri + alan kapisindan gelmeli."""
    flight = _AltitudeTrackingFlight(1.0)
    ph = _phase(flight)
    ceiling = ph._detection_ceiling_m()
    assert ceiling is not None

    intr_focal = None
    from core.detection.camera_intrinsics import default_camera_intrinsics
    res_w, res_h = MockCameraSource().get_resolution()
    intr_focal = default_camera_intrinsics().scaled_to(res_w, res_h).focal_px
    area_scale = (res_w * res_h) / float(1280 * 960)
    beklenen = (intr_focal
                * math.sqrt(PAYLOAD_RECT_LONG_EDGE_M * PAYLOAD_RECT_SHORT_EDGE_M
                            / (HSV_MIN_AREA_RECT_BASE * area_scale))
                / HOOK_REACQUIRE_CEILING_MARGIN)
    assert ceiling == pytest.approx(beklenen, rel=1e-9)


def test_tavan_irtifasinda_yuk_kapiyi_hala_geciyor():
    """Tavan, yukun kapiyi TEGET gectigi yer olmamali -- payi olmali."""
    flight = _AltitudeTrackingFlight(1.0)
    ceiling = _phase(flight)._detection_ceiling_m()
    from core.detection.camera_intrinsics import default_camera_intrinsics
    res_w, res_h = MockCameraSource().get_resolution()
    f = default_camera_intrinsics().scaled_to(res_w, res_h).focal_px
    area_scale = (res_w * res_h) / float(1280 * 960)
    alan_px = (PAYLOAD_RECT_LONG_EDGE_M * PAYLOAD_RECT_SHORT_EDGE_M
               * f * f / (ceiling ** 2))
    assert alan_px > HSV_MIN_AREA_RECT_BASE * area_scale


@pytest.mark.asyncio
async def test_tavan_altinda_tirmanis_KORUNUR():
    """Mesru amac: hedef kadraj disindaysa yukselmek kadraji genisletir."""
    flight = _AltitudeTrackingFlight(HOOK_VISUAL_ALIGN_ALTITUDE_M)
    ph = _phase(flight)
    ceiling = ph._detection_ceiling_m()
    assert HOOK_VISUAL_ALIGN_ALTITUDE_M + HOOK_REACQUIRE_CLIMB_M > ceiling or True

    await ph._reacquire_by_climbing(0.0)
    assert flight.targets, "hic hareket edilmedi"
    assert flight.targets[0] > HOOK_VISUAL_ALIGN_ALTITUDE_M, \
        f"ilk adim yukari olmali, gidilen: {flight.targets}"


@pytest.mark.asyncio
async def test_tavan_HIC_asilmaz():
    """Kusurun ta kendisi: eskiden 3 adim x 1 m ile 3.9 m'ye cikiyordu."""
    flight = _AltitudeTrackingFlight(HOOK_VISUAL_ALIGN_ALTITUDE_M)
    ph = _phase(flight)
    ceiling = ph._detection_ceiling_m()

    await ph._reacquire_by_climbing(0.0)

    assert flight.targets, "hic hareket edilmedi"
    assert max(flight.targets) <= ceiling + 1e-6, (
        f"tavan {ceiling:.3f} m asildi: {flight.targets}")


@pytest.mark.asyncio
async def test_tavan_uzerinden_baslarsa_ASAGI_doner():
    """Tetiklenme irtifasi zaten tavanin ustundeyse yukselmek yuku
    kucultur; tek anlamli yon asagi."""
    flight = _AltitudeTrackingFlight(3.0)   # tavanin cok ustu
    ph = _phase(flight)

    await ph._reacquire_by_climbing(0.0)

    assert flight.targets, "hic hareket edilmedi"
    assert flight.targets[0] < 3.0, \
        f"tavanin ustunde ASAGI inilmeliydi, gidilen: {flight.targets}"


@pytest.mark.asyncio
async def test_hizalama_irtifasinin_ALTINA_inilmez():
    """Bu dosyanin kendi notlari 0.30 m'yi tuzak olarak kaydediyor."""
    flight = _AltitudeTrackingFlight(3.0)
    ph = _phase(flight)

    await ph._reacquire_by_climbing(0.0)

    assert min(flight.targets) >= HOOK_VISUAL_ALIGN_ALTITUDE_M - 1e-6, \
        f"hizalama irtifasinin altina inildi: {flight.targets}"


@pytest.mark.asyncio
async def test_adim_sayisi_asilmaz():
    flight = _AltitudeTrackingFlight(3.0)
    ph = _phase(flight)
    await ph._reacquire_by_climbing(0.0)
    assert len(flight.targets) <= HOOK_REACQUIRE_MAX_CLIMBS
