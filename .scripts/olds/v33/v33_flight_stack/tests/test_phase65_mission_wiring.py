"""PHASE 6.5 testleri: Gorev3 -> payload/PayloadManager migrasyonu.

Uc sey kanitlanir:
  1. GAZEBO YOLU: Phase 6 acceptance mantigi artik gercek mission giris
     noktasindan (Gorev3PickupPhase.run) tetiklendiginde de ayni sonuca
     ulasiyor -- payload UAV'i takip ediyor ve sekil yerden kalkiyor.
  2. REAL YOLU: kalibre edilmemis/sensorsuz backend'in firlattigi exception
     TEMIZ bir faz basarisizligina donusuyor -- cokme YOK, hang YOK.
  3. V33 SIRASI: catch_box_down -> grapple -> catch_box_up, tirmanmadan
     ONCE, tek blokta.
"""
import asyncio

import pytest

from mocks.mock_camera_source import MockCameraSource
from mocks.mock_flight_backend import MockFlightBackend
from mocks.mock_payload_manager import MockPayloadManager

from core.detection.types import Detection
from core.mission.gorev3_pickup import Gorev3PickupPhase
from core.mission.gorev3_redrop import Gorev3RedropPhase
from core.mission.rectangle_alignment_strategy import RectangleAlignmentStrategy
from core.position_log.position_store import PositionStore
from payload import PayloadManager, PayloadState
from payload.backends.gazebo_payload_backend import GazeboPayloadBackend
from payload.errors import PayloadCalibrationError

from test_phase6_hybrid_joint_layer import _FakeHookClient, _FakeJointWorld

_PAYLOAD = "payload_red"
_VEHICLE = "x500_mono_cam_down_0"


class _RectangleUntilPickedUp:
    def __init__(self):
        self.picked_up = False

    async def detect(self, frame):
        if self.picked_up:
            return []
        return [Detection(shape_type="KIRMIZI_DIKDORTGEN", confidence=0.9,
                          center_px=(320, 240), bbox_px=(300, 220, 340, 260),
                          rotation_deg=15.0)]


class _Centering:
    def __init__(self):
        self.calls = []

    async def goto_global_position_and_wait(self, lat, lon, alt) -> bool:
        self.calls.append((lat, lon, alt))
        return True

    async def go_to_and_center(self, shape_type, altitude_m=None, **kw) -> bool:
        # **kw KASITLI: uretim imzasi (alt_tolerance_m, aim_offset_body_m)
        # buyudugunde stub sessizce TypeError'a dusmesin. Bir stub, taklit
        # ettigi imzayi oldugundan DAR tanimlarsa kendi kirilganligini uretir.
        self.calls.append((shape_type, altitude_m))
        return True

    async def descend_to_release(self, shape_type, altitude_m, mount_body_m) -> float:
        self.calls.append((shape_type, altitude_m, tuple(mount_body_m)))
        return altitude_m


def _store(tmp_path):
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("MAVI_ALTIGEN", 0.9, True, True, (41.0, 29.0, 15.0), "ilk")
    return store


def _pickup(detector, payload_manager, tmp_path):
    return Gorev3PickupPhase(MockFlightBackend(), MockCameraSource(), detector,
                             payload_manager, _store(tmp_path),
                             RectangleAlignmentStrategy(), _Centering())


# ---------------------------------------------------------------------------
# 1. GAZEBO YOLU -- gercek mission giris noktasindan
# ---------------------------------------------------------------------------

class _WorldBoundDetector(_RectangleUntilPickedUp):
    """Sekil, payload GERCEKTEN araca bagliyken ve araci izliyorken
    gorunmez olur -- 'picked_up' bayragi elle set EDILMEZ, fake Gazebo
    dunyasinin joint durumundan TURETILIR."""

    def __init__(self, world: _FakeJointWorld):
        super().__init__()
        self._world = world

    async def detect(self, frame):
        self.picked_up = self._world.attached
        return await super().detect(frame)


@pytest.mark.asyncio
async def test_gazebo_pickup_through_mission_entry_point(tmp_path):
    """Phase 6 acceptance'in mission-katmani karsiligi: Gorev3PickupPhase.run()
    cagrilinca gercek PayloadManager + GazeboPayloadBackend zinciri surulur,
    joint olusur ve payload araci izler."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 0.339))
    client = _FakeHookClient(world)
    manager = PayloadManager(GazeboPayloadBackend(
        client, payload_model_name=_PAYLOAD, vehicle_model_name=_VEHICLE))
    detector = _WorldBoundDetector(world)

    ok = await _pickup(detector, manager, tmp_path).run()

    assert ok is True
    assert world.attached is True, "mission giris noktasindan joint OLUSMADI"
    assert manager.get_state() is PayloadState.TRANSPORTING

    # Phase 6 acceptance'in cekirdegi: payload UAV'i izliyor mu.
    payload_before = client.pose(_PAYLOAD)
    world.move_vehicle_to((0.0, 0.0, 0.839))
    assert client.pose(_PAYLOAD)[2] == pytest.approx(payload_before[2] + 0.5, abs=1e-6)


@pytest.mark.asyncio
async def test_gazebo_pickup_fails_when_out_of_envelope(tmp_path):
    """Arac envelope disindayken faz TEMIZ sekilde False donmeli ve
    simulasyona hicbir attach GITMEMELI."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 3.0))
    client = _FakeHookClient(world)
    manager = PayloadManager(GazeboPayloadBackend(
        client, payload_model_name=_PAYLOAD, vehicle_model_name=_VEHICLE))

    ok = await _pickup(_WorldBoundDetector(world), manager, tmp_path).run()

    assert ok is False
    assert client.published == []
    assert world.attached is False


# ---------------------------------------------------------------------------
# 2. REAL YOLU -- temiz basarisizlik, cokme/hang yok
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [
    PayloadCalibrationError("FLEX_14_SERVO2_ACTUATOR_INDEX kalibre edilmedi"),
    NotImplementedError("await_capture(): sensor yolu yok"),
])
@pytest.mark.parametrize("step", ["catch_box_down", "grapple", "catch_box_up"])
async def test_real_gap_becomes_clean_phase_failure(tmp_path, exc, step):
    """Kalibre edilmemis / sensorsuz Real backend hangi adimda patlarsa
    patlasin, faz TEMIZ False donmeli.

    Kritik: exception mission katmanindan DISARI SIZMAMALI. master_fsm.py
    zaten genel bir `except Exception` tutuyor ama o faz atifini kaybediyor;
    burada yakalamak GOREV3_PHASE_FAILED yolunu korur."""
    manager = MockPayloadManager(raise_on=step, exception=exc)
    detector = _RectangleUntilPickedUp()

    ok = await _pickup(detector, manager, tmp_path).run()

    assert ok is False
    assert [c[0] for c in manager.calls][-1] == step, "patlayan adima kadar ilerlemeli"


@pytest.mark.asyncio
async def test_real_gap_failure_does_not_hang(tmp_path):
    """'Sessiz takilma yok' iddiasini somut olarak sinar: faz makul bir
    surede DONMELI, sonsuza kadar beklememeli."""
    manager = MockPayloadManager(raise_on="catch_box_down",
                                 exception=PayloadCalibrationError("TBD"))
    phase = _pickup(_RectangleUntilPickedUp(), manager, tmp_path)

    ok = await asyncio.wait_for(phase.run(), timeout=10.0)
    assert ok is False


@pytest.mark.asyncio
async def test_redrop_converts_real_gap_to_clean_failure(tmp_path):
    """Redrop tarafinda da ayni: exception disari sizmaz, False doner."""
    store = PositionStore(str(tmp_path / "p.json"))
    store.try_save("KIRMIZI_UCGEN", 0.9, True, True, (41.0, 29.0, 40.0), "ilk")
    manager = MockPayloadManager(raise_on="release",
                                 exception=PayloadCalibrationError("FLEX-15 TBD"))
    phase = Gorev3RedropPhase(None, manager, store, _Centering())

    assert await phase.run() is False


# ---------------------------------------------------------------------------
# 3. Sozlesme: V33 sirasi ve sonucun BAGLAYICI olmasi
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("failing_step", ["catch_box_down", "grapple", "catch_box_up"])
async def test_pickup_stops_at_first_failing_step(tmp_path, failing_step):
    """DAVRANIS DEGISIKLIGI (operator onayli, 2026-08-23): eski kod
    activate_pickup_mechanism()'in donusunu ATIYORDU ve karari tamamen
    vision'a birakiyordu. Artik mekanizma sonucu BAGLAYICI: basarisiz
    adimdan sonra hicbir adim daha calismaz ve vision dogrulamasina HIC
    gecilmez."""
    manager = MockPayloadManager(fail_on=failing_step)
    detector = _RectangleUntilPickedUp()   # sekil hep gorunur kalir

    ok = await _pickup(detector, manager, tmp_path).run()

    assert ok is False
    executed = [c[0] for c in manager.calls]
    expected = ["catch_box_down", "grapple", "catch_box_up"]
    assert executed == expected[:expected.index(failing_step) + 1]


@pytest.mark.asyncio
async def test_pickup_requires_physical_confirmation_after_success(tmp_path):
    """GUNCELLENDI (PHASE 15, 2026-08-24): bu test eskiden "payload basarili
    olsa bile VISION dogrulamasi da gecmeli" diyordu. O dogrulama yeni
    yaklasma akisinda YAPISAL OLARAK GECILEMEZ hale geldi (arac payload'in
    ustune geldigi icin tasinan payload goruntude kaliyor) ve operator
    karariyla FIZIKSEL dogrulamayla degistirildi.

    Sozlesmenin OZU DEGISMEDI: mekanizmanin "tamam" demesi TEK BASINA
    yetmez. Burada mekanizma basarili ama yuk fiziksel olarak elde degil
    -> faz duser."""
    manager = MockPayloadManager(still_secured=False)
    detector = _RectangleUntilPickedUp()

    ok = await _pickup(detector, manager, tmp_path).run()

    assert ok is False
    assert [c[0] for c in manager.calls] == ["catch_box_down", "grapple", "catch_box_up"], \
        "payload dizisi tam calismaliydi -- basarisizlik fiziksel dogrulamadan gelmeli"


@pytest.mark.asyncio
async def test_payload_sequence_runs_before_verification_climb(tmp_path):
    """V33 sirasi: retract (catch_box_up) tirmanmadan ONCE tamamlanir."""
    flight = MockFlightBackend()
    manager = MockPayloadManager()
    world_detector = _RectangleUntilPickedUp()

    class _Tracking(MockPayloadManager):
        def __init__(self, flight):
            super().__init__()
            self._flight = flight
            self.moves_at_catch_box_up = None

        async def catch_box_up(self):
            self.moves_at_catch_box_up = len(self._flight.calls)
            world_detector.picked_up = True
            return await super().catch_box_up()

    tracking = _Tracking(flight)
    phase = Gorev3PickupPhase(flight, MockCameraSource(), world_detector, tracking,
                              _store(tmp_path), RectangleAlignmentStrategy(), _Centering())
    assert await phase.run() is True
    # catch_box_up tamamlandiktan SONRA hala ucus komutu verilmis olmali
    # (dogrulama tirmanislari) -- yani retract tirmanmadan once bitti.
    assert len(flight.calls) > tracking.moves_at_catch_box_up


# ---------------------------------------------------------------------------
# 4. Boot aninda kalibrasyon uyarisi (Phase 6.5 kapanis eki)
# ---------------------------------------------------------------------------

def test_boot_warning_fires_when_real_backend_uncalibrated(caplog):
    """Kalibrasyon eksikligi ucusun ORTASINDA degil, KALKISTAN ONCE
    gorunur olmali. Repoda FLEX-14..19 halen TBD oldugu icin bu uyari
    bugun gercekten uretiliyor olmali."""
    from payload.backends.real_payload_backend import (
        uncalibrated_flex_names, warn_if_uncalibrated)

    assert uncalibrated_flex_names(), "FLEX-14..19 artik TBD degilse bu testi guncelleyin"
    with caplog.at_level("WARNING"):
        missing = warn_if_uncalibrated()

    assert "Real Payload Backend kalibre edilmemis" in caplog.text
    assert "BASARISIZ olacak" in caplog.text
    assert "FLEX_14_SERVO2_ACTUATOR_INDEX" in caplog.text
    assert len(missing) == 6


def test_boot_warning_is_silent_when_calibrated(monkeypatch, caplog):
    """Kalibre edildiginde uyari SUSMALI -- yoksa kalici gurultu olur ve
    gercek bir uyari oldugunda kimse bakmaz."""
    from payload import payload_config
    from payload.backends.real_payload_backend import (
        REQUIRED_FLEX_NAMES, warn_if_uncalibrated)

    for name in REQUIRED_FLEX_NAMES:
        monkeypatch.setattr(payload_config, name, 1)
    with caplog.at_level("WARNING"):
        missing = warn_if_uncalibrated()

    assert missing == []
    assert "kalibre edilmemis" not in caplog.text


def test_boot_warning_does_not_block(monkeypatch):
    """Mission'i BLOKLAMAZ: fonksiyon exception firlatmaz, sadece liste
    dondurur -- ucus kalkabilmeli."""
    from payload.backends.real_payload_backend import warn_if_uncalibrated

    assert isinstance(warn_if_uncalibrated(), list)


@pytest.mark.asyncio
async def test_pickup_fails_if_payload_lost_during_verification_climb(tmp_path):
    """PHASE 15: dogrulama iki noktada sorulur -- tirmanistan once VE sonra.
    Tirmanis sirasinda yuk duserse faz duser; bu, Phase 6 acceptance'inin
    "payload UAV'i izliyor mu" olcumunun mission karsiligidir."""
    class _DropsDuringClimb(MockPayloadManager):
        def __init__(self):
            super().__init__()
            self._checks = 0

        def is_still_secured(self):
            self._checks += 1
            return self._checks == 1        # ilk kontrol gecer, ikincisi dusER

    manager = _DropsDuringClimb()
    ok = await _pickup(_RectangleUntilPickedUp(), manager, tmp_path).run()

    assert ok is False
    assert manager._checks == 2, "tirmanis sonrasi kontrol yapilmadi"


@pytest.mark.asyncio
async def test_pickup_converts_query_gap_to_clean_failure(tmp_path):
    """Real yolun sorgu boslugu dogrulama adiminda da TEMIZ basarisizliga
    donusur, disari sizmaz."""
    manager = MockPayloadManager(raise_on="is_still_secured",
                                 exception=NotImplementedError("sensor yolu yok"))

    assert await _pickup(_RectangleUntilPickedUp(), manager, tmp_path).run() is False
