"""PHASE 7 testleri: vision-gudumlu yaklasma + FLEX-21 kanca otelemesi.

Kanitlananlar:
  1. Eski "0.30 m geri -> gorunurluk onayi -> 0.60 m ileri" dansi
     GITTI; yerine go_to_and_center geldi.
  2. FLEX-21 TBD (None) iken HICBIR oteleme uygulanmiyor ve davranis
     ongorulebilir kaliyor -- akis cokmuyor, sadece uyariyor.
  3. FLEX-21 dolu iken oteleme TAM OLARAK bir kez, dogru degerle
     uygulaniyor.
  4. V33 payload dizisi (deploy/await_capture/grapple = catch_box_down/
     grapple/catch_box_up) DEGISMEDI ve yeni akisla dogru entegre.
  5. Deprecated sabitler kod yolundan gercekten cikti.
"""
import pytest

from mocks.mock_camera_source import MockCameraSource
from mocks.mock_flight_backend import MockFlightBackend
from mocks.mock_payload_manager import MockPayloadManager

from core.detection.types import Detection
from core.mission.gorev3_pickup import Gorev3PickupPhase
from core.mission.rectangle_alignment_strategy import RectangleAlignmentStrategy
from core.position_log.position_store import PositionStore
from core.config.parameters import GOREV3_DESCENT_ALTITUDE_M
from payload import payload_config

from test_gorev3_pickup import _RecordingCentering


class _RectangleUntilPickedUp:
    def __init__(self):
        self.picked_up = False

    async def detect(self, frame):
        if self.picked_up:
            return []
        return [Detection(shape_type="KIRMIZI_DIKDORTGEN", confidence=0.9,
                          center_px=(320, 240), bbox_px=(300, 220, 340, 260),
                          rotation_deg=15.0)]


class _PickupTriggering(MockPayloadManager):
    def __init__(self, detector, **kw):
        super().__init__(**kw)
        self._detector = detector

    async def catch_box_up(self):
        result = await super().catch_box_up()
        if result.success:
            self._detector.picked_up = True
            self._still_secured = True
        return result


def _build(tmp_path, centering=None, detector=None, manager=None):
    detector = detector or _RectangleUntilPickedUp()
    store = PositionStore(str(tmp_path / "p.json"))
    store.try_save("MAVI_ALTIGEN", 0.9, True, True, (41.0, 29.0, 15.0), "ilk")
    centering = centering or _RecordingCentering()
    manager = manager or _PickupTriggering(detector)
    phase = Gorev3PickupPhase(MockFlightBackend(), MockCameraSource(), detector,
                              manager, store, RectangleAlignmentStrategy(), centering)
    return phase, centering, manager, detector


# ---------------------------------------------------------------------------
# 1. Eski dans gitti
# ---------------------------------------------------------------------------

def test_deprecated_distance_constants_left_the_code_path():
    """GOREV3_RETREAT/ADVANCE_DISTANCE_M ve VISIBILITY_CONFIRM_FRAMES
    silinmedi ama gorev3_pickup ARTIK IMPORT ETMEMELI."""
    import inspect

    import core.mission.gorev3_pickup as pickup_module
    source = inspect.getsource(pickup_module)
    for name in ("GOREV3_RETREAT_DISTANCE_M", "GOREV3_ADVANCE_DISTANCE_M",
                 "GOREV3_PICKUP_VISIBILITY_CONFIRM_FRAMES"):
        assert not hasattr(pickup_module, name), f"{name} hala import ediliyor"
        # Yorumlarda anilmasi serbest, KOD yolunda olmamasi gerekiyor.
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            assert name not in stripped, f"{name} hala kod yolunda: {stripped}"


def test_deprecated_constants_still_exist_in_parameters():
    """Silinmediler -- proje deseni 'deprecate et, silme'."""
    from core.config import parameters

    assert parameters.GOREV3_RETREAT_DISTANCE_M == 0.30
    assert parameters.GOREV3_ADVANCE_DISTANCE_M == 0.60


@pytest.mark.asyncio
async def test_pickup_centers_over_target_instead_of_dancing(tmp_path):
    """Yeni akis: hedefin USTUNE merkezleniyor, alcalma irtifasinda."""
    phase, centering, _, _ = _build(tmp_path)

    assert await phase.run() is True
    assert centering.center_calls == [("KIRMIZI_DIKDORTGEN", GOREV3_DESCENT_ALTITUDE_M)]


@pytest.mark.asyncio
async def test_pickup_fails_cleanly_when_centering_does_not_converge(tmp_path):
    """Merkezlenemezse faz TEMIZ duser -- eski kor dansin aksine, artik
    hedefi gormeden alma pozisyonuna gidilmiyor."""
    phase, _, manager, _ = _build(tmp_path, centering=_RecordingCentering(centers=False))

    assert await phase.run() is False
    assert manager.calls == [], "merkezlenemeden payload dizisi calisti"


# ---------------------------------------------------------------------------
# 2. FLEX-21 TBD -> oteleme YOK, davranis bugunkuyle ayni
# ---------------------------------------------------------------------------

def test_flex21_is_still_tbd():
    """Phase 7 mekanizmayi kurar, DEGER yazmaz (bench/vision kalibrasyonu
    Phase 16). Deger sessizce girilirse bu test kirilir."""
    assert payload_config.FLEX_21_HOOK_MOUNT_OFFSET_BODY_M is None


@pytest.mark.asyncio
async def test_no_translation_applied_when_flex21_tbd(tmp_path):
    """TBD iken descend_to_release HIC cagrilmaz -- oteleme yok, akis
    cokmuyor, irtifayi zaten go_to_and_center kapatiyor."""
    phase, centering, _, _ = _build(tmp_path)

    assert await phase.run() is True
    assert centering.descend_calls == []


@pytest.mark.asyncio
async def test_uncalibrated_offset_is_warned_not_silent(tmp_path, caplog):
    """Kalibre edilmemis olmak SESSIZ kalmamali -- kanca kameranin
    hizalandigi noktaya iner ve sapma beklenir."""
    phase, _, _, _ = _build(tmp_path)

    with caplog.at_level("WARNING"):
        await phase.run()

    assert "FLEX-21" in caplog.text
    assert "UYGULANMIYOR" in caplog.text


# ---------------------------------------------------------------------------
# 3. FLEX-21 dolu -> oteleme TAM bir kez, dogru degerle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [(0.35, 0.0), (0.0, -0.12), (0.20, 0.08)])
async def test_translation_applied_exactly_once_when_calibrated(tmp_path, monkeypatch, offset):
    """Kalibre edilince oteleme dondurulmus kestirime TEK SEFER uygulanir
    ve tam olarak FLEX-21 degeriyle gecirilir."""
    monkeypatch.setattr(payload_config, "FLEX_21_HOOK_MOUNT_OFFSET_BODY_M", offset)
    phase, centering, _, _ = _build(tmp_path)

    assert await phase.run() is True
    assert centering.descend_calls == [
        ("KIRMIZI_DIKDORTGEN", GOREV3_DESCENT_ALTITUDE_M, offset)]


@pytest.mark.asyncio
async def test_offset_is_not_biased_into_the_centering_loop(tmp_path, monkeypatch):
    """OLCUMLE YASAKLI: ofseti merkezleme dongusune bias olarak vermek,
    dayandigi olcumu bozuyor (descend_to_release docstring'i: 40.1/32.5 cm
    vs 33.7-37.3 cm baseline). go_to_and_center'a ofset GECIRILMEMELI."""
    monkeypatch.setattr(payload_config, "FLEX_21_HOOK_MOUNT_OFFSET_BODY_M", (0.35, 0.0))
    recorded = {}

    class _Spy(_RecordingCentering):
        async def go_to_and_center(self, shape_type, altitude_m=None, **kw):
            recorded.update(kw)
            return await super().go_to_and_center(shape_type, altitude_m)

    phase, _, _, _ = _build(tmp_path, centering=_Spy())
    await phase.run()

    assert recorded.get("aim_offset_body_m") is None, \
        "ofset merkezleme dongusune bias olarak gecirildi"


@pytest.mark.asyncio
async def test_offset_read_at_call_time_not_import_time(tmp_path, monkeypatch):
    """Kalibrasyon sonrasi guncelleme aninda etkili olmali -- deger import
    aninda kopyalanmamali."""
    phase, centering, _, _ = _build(tmp_path)
    monkeypatch.setattr(payload_config, "FLEX_21_HOOK_MOUNT_OFFSET_BODY_M", (1.0, 2.0))

    await phase.run()

    assert centering.descend_calls == [
        ("KIRMIZI_DIKDORTGEN", GOREV3_DESCENT_ALTITUDE_M, (1.0, 2.0))]


# ---------------------------------------------------------------------------
# 4. V33 dizisi degismedi ve yeni akisla dogru entegre
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_v33_sequence_unchanged_and_runs_after_centering(tmp_path):
    """Payload dizisi AYNEN duruyor ve merkezlemeden SONRA calisiyor."""
    phase, centering, manager, _ = _build(tmp_path)

    assert await phase.run() is True
    assert [c[0] for c in manager.calls] == [
        "catch_box_down", "grapple", "catch_box_up"]
    assert centering.center_calls, "merkezleme payload dizisinden once olmali"


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_step", ["catch_box_down", "grapple", "catch_box_up"])
async def test_payload_failure_still_binding_after_new_approach(tmp_path, failing_step):
    """Phase 6.5'in davranisi korundu: mekanizma sonucu BAGLAYICI."""
    detector = _RectangleUntilPickedUp()
    phase, _, manager, _ = _build(
        tmp_path, detector=detector,
        manager=_PickupTriggering(detector, fail_on=failing_step))

    assert await phase.run() is False


# ---------------------------------------------------------------------------
# 5. SITL bulgusu (2026-08-24): dar irtifa bandi
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_final_approach_uses_the_tight_altitude_band(tmp_path):
    """Phase 15 kosu 1'de olculdu: dar band GECIRILMEZSE varsayilan
    +/-0.30 m bandi yanal yakinsamayi alt_err=+0.28 m ile kabul ediyor,
    arac ~0.58 m'de kaliyor ve FLEX-20 kapisi haklı olarak kapaniyor.

    Aritmetik kaniti da burada: 0.30 + tolerans <= FLEX-20 olmak ZORUNDA,
    yoksa mesru bir yakinsama bile kapiyi gecemez."""
    from core.config.parameters import GOREV3_PICKUP_ALTITUDE_TOLERANCE_M
    from payload import payload_config

    captured = {}

    class _Spy(_RecordingCentering):
        async def go_to_and_center(self, shape_type, altitude_m=None, **kw):
            captured.update(kw)
            return await super().go_to_and_center(shape_type, altitude_m)

    phase, _, _, _ = _build(tmp_path, centering=_Spy())
    assert await phase.run() is True

    assert captured.get("alt_tolerance_m") == GOREV3_PICKUP_ALTITUDE_TOLERANCE_M, \
        "son yaklasma gevsek varsayilan bantla yapiliyor"

    worst_case_altitude = GOREV3_DESCENT_ALTITUDE_M + GOREV3_PICKUP_ALTITUDE_TOLERANCE_M
    from gz_system.gz_hook_client import PAYLOAD_HALF_HEIGHT_M
    worst_case_clearance = worst_case_altitude - PAYLOAD_HALF_HEIGHT_M - 0.025
    assert worst_case_clearance <= payload_config.FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M, (
        f"en kotu durumda aciklik {worst_case_clearance:.3f} m, FLEX-20 "
        f"{payload_config.FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M} m -- mesru bir "
        f"yakinsama bile kapiyi gecemez")
