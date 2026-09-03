"""E4e -- iraksama korumasi: Guard 1, Guard 2 ve tirman-tekrar-atla zinciri.

NEDEN VAR (olculdu, 2026-09-03): kestirim bozuldugunda `_mount_translate`
8 s'lik butcesini doldurana kadar bekliyordu ve o sure boyunca araci hedeften
UZAKLASTIRIYORDU -- kalan mesafe 0.2596 -> 0.5502 m buyurken gercek hiz 2 m/s'e
cikti ve yuk hedeften 10.19 m oteye dustu. Bir de servo, yakinsama HIC
saglanmadan atesleniyordu.

Bu dosya uc seyi cakiyor:
  1. Guard 1 -- kalan mesafe N=5 tick ust uste buyudugunde donguden erken cikis
  2. Guard 2 -- yakinsamayan/iraksayan durumda SERVO ATESLENMEZ
  3. Zincir  -- tirman(5 m) -> son adimi tekrarla -> hala kotuyse ATLA ve
                yuku aracta birak (interlock 'birakildi' isaretlenmez)
"""
import math

import pytest

from core.config.parameters import (
    MOUNT_TRANSLATE_DIVERGE_TICKS,
    MOUNT_TRANSLATE_DIVERGE_EPS_M,
    MOUNT_TRANSLATE_TOLERANCE_M,
    PAYLOAD_RELEASE_MAX_GROUND_SPEED_M_S,
)


# --------------------------------------------------------------------------
# Guard 1: ardisik buyume dedektorunun saf mantigi
# --------------------------------------------------------------------------
def _streak_would_fire(residuals, ticks=MOUNT_TRANSLATE_DIVERGE_TICKS,
                       eps=MOUNT_TRANSLATE_DIVERGE_EPS_M,
                       tol=MOUNT_TRANSLATE_TOLERANCE_M):
    """centering_controller._mount_translate icindeki sayacin birebir aynisi."""
    prev = None
    streak = 0
    for r in residuals:
        if r <= tol:
            return False                      # yakinsadi, donguden cikar
        if prev is not None and r > prev + eps:
            streak += 1
        else:
            streak = 0
        prev = r
        if streak >= ticks and r > tol:
            return True
    return False


def test_guard1_fires_on_the_measured_diverging_series():
    """run4'un gercek imzasi: kalan mesafe tekduze buyuyor."""
    series = [0.26 + 0.02 * i for i in range(20)]     # 20 tick, hep buyuyor
    assert _streak_would_fire(series) is True


def test_guard1_silent_on_the_measured_healthy_series():
    """run5/run6: yakinsayan pencerelerde gorulen en uzun ardisik buyume 1'di."""
    # run6 imzasi: genel egilim asagi, arada tek tik gurultu.
    series = [0.166, 0.149, 0.152, 0.132, 0.116, 0.118, 0.101, 0.089,
              0.079, 0.081, 0.070, 0.062, 0.054]
    assert max(_consecutive_growth(series)) <= 1
    assert _streak_would_fire(series) is False


def _consecutive_growth(series, eps=MOUNT_TRANSLATE_DIVERGE_EPS_M):
    out, cur = [], 0
    for i in range(1, len(series)):
        if series[i] > series[i - 1] + eps:
            cur += 1
        else:
            out.append(cur)
            cur = 0
    out.append(cur)
    return out


def test_guard1_ignores_sub_millimetre_noise():
    """EPS olu bandi olmasa duz gurultu bile sayaci doldururdu."""
    series = [0.40 + 0.0001 * i for i in range(30)]   # 0.1 mm/tick
    assert _streak_would_fire(series) is False


def test_guard1_threshold_sits_in_the_measured_gap():
    """Olculen seri uzunluklari: 1x8, 2x2, 3x3, 9x1, 12x1.
    3 ile 9 arasinda hic seri yok; N bu bosluga dusmeli."""
    observed = [1] * 8 + [2] * 2 + [3] * 3 + [9] + [12]
    healthy_max = 3          # yakinsayan pencerelerde 1, iraksayan proxy'de 3
    shortest_bad = 9
    assert healthy_max < MOUNT_TRANSLATE_DIVERGE_TICKS < shortest_bad
    assert not any(healthy_max < x < shortest_bad for x in observed)


# --------------------------------------------------------------------------
# Guard 2 + zincir: sahte servis
# --------------------------------------------------------------------------
class _Flight:
    def __init__(self, speed=0.0):
        self.speed = speed

    async def get_velocity_ned(self):
        return (self.speed, 0.0, 0.0)

    async def get_global_position(self):
        return (47.0, 8.0, 0.45)


class _Centering:
    """Iraksayan kestirimi taklit eder: istenirse hep yakinsamaz."""

    def __init__(self, converge_after=None, diverged=False):
        self.converge_after = converge_after   # None = hic yakinsama
        self.calls = 0
        self.last_translate_diverged = diverged
        self.altitudes = []
        self.nudges = 0

    async def go_to_and_center(self, shape_type, altitude_m=None, alt_tolerance_m=None):
        self.calls += 1
        self.altitudes.append(altitude_m)
        if self.converge_after is None:
            return False
        return self.calls >= self.converge_after

    async def descend_to_release(self, shape_type, altitude_m, mount):
        return altitude_m

    async def nudge_forward(self, d):
        self.nudges += 1


class _Service:
    """release_and_verify'in guard'a ait kismini izole eden ince kabuk.

    Gercek PayloadReleaseService'in _release_gate_ok metodunu AYNEN kullanir --
    kopyalanmaz, ithal edilir; yoksa test kendi kopyasini dogrulardi."""

    from core.mission.payload_release import PayloadReleaseService
    _release_gate_ok = PayloadReleaseService._release_gate_ok

    def __init__(self, centering, flight):
        self.centering = centering
        self.flight = flight
        self.events = []

    def _publish(self, code, message="", severity=None, data=None):
        self.events.append((code, data or {}))


@pytest.mark.asyncio
async def test_gate_blocks_when_final_step_did_not_converge():
    svc = _Service(_Centering(), _Flight(speed=0.0))
    assert await svc._release_gate_ok("MAVI_ALTIGEN", False) is False
    assert any(c == "PAYLOAD_RELEASE_GATE_BLOCKED" for c, _ in svc.events)


@pytest.mark.asyncio
async def test_gate_blocks_when_translate_diverged_even_if_converged():
    """Guard 1 tetiklendiyse kapi KOSULSUZ kapali."""
    svc = _Service(_Centering(diverged=True), _Flight(speed=0.0))
    assert await svc._release_gate_ok("MAVI_ALTIGEN", True) is False
    blocked = [d for c, d in svc.events if c == "PAYLOAD_RELEASE_GATE_BLOCKED"]
    assert blocked and blocked[0]["translate_diverged"] is True


@pytest.mark.asyncio
async def test_gate_blocks_on_excess_ground_speed():
    fast = PAYLOAD_RELEASE_MAX_GROUND_SPEED_M_S + 0.2
    svc = _Service(_Centering(), _Flight(speed=fast))
    assert await svc._release_gate_ok("MAVI_ALTIGEN", True) is False


@pytest.mark.asyncio
async def test_gate_passes_when_everything_is_healthy():
    svc = _Service(_Centering(), _Flight(speed=0.05))
    assert await svc._release_gate_ok("MAVI_ALTIGEN", True) is True
    assert any(c == "PAYLOAD_RELEASE_GATE_PASSED" for c, _ in svc.events)


@pytest.mark.asyncio
async def test_gate_stays_open_when_velocity_telemetry_is_unavailable():
    """Telemetri kaybi birakmayi engellememeli -- birincil kapi zaten devrede."""
    class _NoVel(_Flight):
        async def get_velocity_ned(self):
            raise RuntimeError("stale")
    svc = _Service(_Centering(), _NoVel())
    assert await svc._release_gate_ok("MAVI_ALTIGEN", True) is True


@pytest.mark.asyncio
async def test_speed_gate_is_documented_as_blind_to_estimator_failure():
    """run4: EKF 0.05 m/s bildirirken gercek 3.00 m/s idi. Kapi bunu
    goremezdi -- olayin verisi bu sinirlamayi TASIMALI."""
    svc = _Service(_Centering(), _Flight(speed=0.05))
    await svc._release_gate_ok("MAVI_ALTIGEN", True)
    data = [d for c, d in svc.events if c == "PAYLOAD_RELEASE_GATE_PASSED"][0]
    assert "kor" in data["ground_speed_note"]


# --------------------------------------------------------------------------
# ENTEGRASYON: yapay iraksayan kestirim -> Guard 1 -> tirman -> tekrar -> atla
# --------------------------------------------------------------------------
class _DivergingFlight:
    """Kestirimi bozuk bir araci taklit eder: raporladigi konum, komut ne
    olursa olsun hedeften TEKDUZE UZAKLASIR. run4'te olculen imza budur --
    kalan mesafe 0.2596 -> 0.5502 m buyurken kontrolcu yakinsadigina
    inaniyordu."""

    def __init__(self, drift_m_per_tick=0.02, start_offset_m=0.30):
        # held'in UZERINDE baslamaz: ilk tick'te yakinsayip cikmasin diye
        # toleransin (5 cm) disinda, 0.30 m kuzeyde baslar -- run4'te
        # olculen baslangic kalanina (0.2596 m) yakin.
        self.lat = 47.0 + start_offset_m / 111320.0
        self.lon = 8.0
        self.drift = drift_m_per_tick
        self.setpoints = []

    async def get_global_position(self):
        return (self.lat, self.lon, 0.45)

    async def get_velocity_ned(self):
        return (0.05, 0.0, 0.0)          # EKF "duruyorum" diyor -- run4 gibi

    async def get_yaw_deg(self):
        return 0.0

    async def set_velocity_body(self, f, r, d, y):
        self.setpoints.append((f, r, d))
        # Komut ne olursa olsun kuzeye kayar: kestirim hareketi izlemiyor.
        self.lat += self.drift / 111320.0


@pytest.mark.asyncio
async def test_integration_guard1_fires_and_stops_early_on_diverging_estimate(monkeypatch):
    """GERCEK _mount_translate ile: iraksayan kestirimde butce dolmadan cikar
    ve MOUNT_TRANSLATE_ABORTED_DIVERGING yayinlar."""
    import asyncio
    from core.detection.detection_feed import DetectionFeed
    from core.navigation.centering_controller import CenteringController
    from core.config.parameters import MOUNT_TRANSLATE_BUDGET_S

    published = []

    class _Pub:
        def publish(self, event):
            published.append(event)

    flight = _DivergingFlight()
    controller = CenteringController(flight, DetectionFeed(stale_after_s=3600.0),
                                     camera=None, publisher=_Pub())
    # Tick beklemelerini kaldir: dongunun MANTIGI test ediliyor, saat degil.
    # ORIJINALI once yakala, yoksa yama kendini cagirir.
    _real_sleep = asyncio.sleep

    async def _no_wait(_delay, *a, **k):
        return await _real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _no_wait)

    held = {"lat": 47.0, "lon": 8.0}
    residual = await controller._mount_translate("MAVI_ALTIGEN", held)

    codes = [e.code for e in published]
    assert "MOUNT_TRANSLATE_ABORTED_DIVERGING" in codes, codes[-5:]
    assert controller.last_translate_diverged is True
    assert residual > MOUNT_TRANSLATE_TOLERANCE_M

    ev = next(e for e in published if e.code == "MOUNT_TRANSLATE_ABORTED_DIVERGING")
    # Kanit olayin ICINDE olmali -- post-analiz baska kaynak aramasin.
    assert ev.data["growth_streak"] >= MOUNT_TRANSLATE_DIVERGE_TICKS
    assert ev.data["residual_m"] > ev.data["residual_at_streak_start_m"]
    assert len(ev.data["recent_residual_m"]) >= MOUNT_TRANSLATE_DIVERGE_TICKS
    # 8 s'lik butceyi TUKETMEDEN cikmis olmali.
    assert ev.data["elapsed_s"] < MOUNT_TRANSLATE_BUDGET_S
    # DONE olayi da iraksamayi tasimali.
    done = next(e for e in published if e.code == "MOUNT_TRANSLATE_DONE")
    assert done.data["diverged"] is True
    assert done.data["converged"] is False


class _NeverConvergingCentering(_Centering):
    """Guard'i tetikleyen kestirim: hicbir adim yakinsamaz ve iraksama
    bayragi kalkik."""

    def __init__(self):
        super().__init__(converge_after=None, diverged=True)


@pytest.mark.asyncio
async def test_integration_climb_retry_then_skip_and_payload_is_retained():
    """Tam zincir: kapi kapali -> 5 m'ye tirman -> son adimi tekrarla ->
    hala kapali -> SERVO ATESLENMEZ, yuk aracta kalir."""
    from mocks.mock_payload_actuator import MockPayloadActuator
    from mocks.mock_camera_source import MockCameraSource
    from core.detection.detection_feed import DetectionFeed
    from core.mission.payload_release import PayloadReleaseService
    from core.config.parameters import (PAYLOAD_RELEASE_RETRY_ALTITUDE_M,
                                        PAYLOAD_APPROACH_ALTITUDES_M)

    actuator = MockPayloadActuator()
    centering = _NeverConvergingCentering()
    published = []

    class _Pub:
        def publish(self, event):
            published.append(event)

    svc = PayloadReleaseService(actuator, DetectionFeed(stale_after_s=3600.0),
                                MockCameraSource(), centering,
                                flight=_Flight(speed=0.05), publisher=_Pub())
    result = await svc.release_and_verify("MAVI_ALTIGEN")

    codes = [e.code for e in published]
    assert "PAYLOAD_RELEASE_GATE_BLOCKED" in codes
    assert "PAYLOAD_RELEASE_RETRY" in codes
    assert "PAYLOAD_RETAINED" in codes

    # TIRMANIS gercekten 5 m'ye ve gorus kapisinin (2.0 m) UZERINE.
    assert PAYLOAD_RELEASE_RETRY_ALTITUDE_M in centering.altitudes
    assert PAYLOAD_RELEASE_RETRY_ALTITUDE_M > 2.0
    # Tekrar denemede son adim da yeniden calisti.
    assert centering.altitudes.count(PAYLOAD_APPROACH_ALTITUDES_M[-1]) >= 2

    # SERVO ATESLENMEDI.
    assert not any("release_payload" in c[0] for c in actuator.calls), actuator.calls
    assert svc.last_payload_retained is True
    assert result is False


@pytest.mark.asyncio
async def test_integration_retained_payload_is_not_marked_released():
    """B: interlock 'birakildi' isaretlenmezse gorev3_precondition kapali
    kalir. Once bu KUSURDU -- mark_released kosulsuzdu ve kapiyi etkisiz
    kiliyordu."""
    from core.mission.interlock import PayloadInterlock
    from core.mission.gorev3_precondition import check_gorev3_precondition

    class _Svc:
        last_payload_retained = True

    interlock = PayloadInterlock()
    retained = bool(getattr(_Svc(), "last_payload_retained", False))
    if not retained:                       # gorev2_fsm ile ayni dal
        interlock.mark_released("MAVI_ALTIGEN")
    assert interlock.payload_1_released is False
    assert check_gorev3_precondition(interlock) is False


def test_gorev2_fsm_marks_release_only_when_payload_actually_left():
    """gorev2_fsm'in her iki bırakma yolunda da kosullu oldugunu cakar."""
    import inspect
    from core.mission import gorev2_fsm
    src = inspect.getsource(gorev2_fsm)
    assert src.count("last_payload_retained") == 2
    # mark_released artik kosulsuz cagrilmiyor: her cagri bir else dalinda.
    for shape in ("MAVI_ALTIGEN", "KIRMIZI_UCGEN"):
        idx = src.index(f'self.interlock.mark_released("{shape}")')
        assert "else:" in src[max(0, idx - 200):idx]
