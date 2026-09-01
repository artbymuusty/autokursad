import pytest

from mocks.mock_flight_backend import MockFlightBackend
from mocks.mock_camera_source import MockCameraSource
from mocks.mock_payload_manager import MockPayloadManager

from core.detection.types import Detection
from core.mission.gorev3_pickup import Gorev3PickupPhase
from core.mission.rectangle_alignment_strategy import RectangleAlignmentStrategy
from core.position_log.position_store import PositionStore
from core.config.parameters import GOREV3_TRANSIT_ALTITUDE_M


class _RectangleUntilPickedUpDetector:
    """Reports a fixed KIRMIZI_DIKDORTGEN (with rotation_deg) until
    `picked_up` flips True, then reports nothing -- simulates a successful
    physical pickup (the shape stops being visible on the ground)."""
    def __init__(self):
        self.picked_up = False

    async def detect(self, frame):
        if self.picked_up:
            return []
        return [Detection(shape_type="KIRMIZI_DIKDORTGEN", confidence=0.9,
                          center_px=(320, 240), bbox_px=(300, 220, 340, 260), rotation_deg=15.0)]


class _PickupTriggeringPayloadManager(MockPayloadManager):
    """PHASE 6.5: eski _PickupTriggeringActuator'in karsiligi.

    Sekil, artik tek bir servo cagrisinda degil, V33 dizisinin SON adimi
    (catch_box_up = SERVO2_REVERSE) tamamlaninca yerden kalkar -- payload
    fiziksel olarak ancak geri cekildiginde ayrilmis olur."""

    def __init__(self, detector: _RectangleUntilPickedUpDetector, **kw):
        super().__init__(**kw)
        self._detector = detector

    async def catch_box_up(self):
        result = await super().catch_box_up()
        if result.success:
            self._detector.picked_up = True
            self._still_secured = True
        return result


class _RecordingCentering:
    """PHASE 7: yeni yaklasma akisi go_to_and_center + (ofset varsa)
    descend_to_release kullaniyor -- eski retreat/advance dansi kalkti."""

    def __init__(self, converges: bool = True, centers: bool = True):
        self.calls = []
        self.center_calls = []
        self.descend_calls = []
        self._converges = converges
        self._centers = centers

    async def goto_global_position_and_wait(self, lat, lon, alt) -> bool:
        self.calls.append((lat, lon, alt))
        return self._converges

    async def go_to_and_center(self, shape_type, altitude_m=None, **kw) -> bool:
        self.center_calls.append((shape_type, altitude_m))
        return self._centers

    async def descend_to_release(self, shape_type, altitude_m, mount_body_m) -> float:
        self.descend_calls.append((shape_type, altitude_m, tuple(mount_body_m)))
        return altitude_m


def _build_phase(flight, camera, detector, payload_manager, store, centering=None):
    return Gorev3PickupPhase(flight, camera, detector, payload_manager, store, RectangleAlignmentStrategy(),
                             centering or _RecordingCentering())


@pytest.mark.asyncio
async def test_pickup_raises_without_recorded_mavi_altigen(tmp_path):
    flight = MockFlightBackend()
    camera = MockCameraSource()
    detector = _RectangleUntilPickedUpDetector()
    payload_manager = _PickupTriggeringPayloadManager(detector)
    store = PositionStore(str(tmp_path / "positions.json"))
    phase = _build_phase(flight, camera, detector, payload_manager, store)

    with pytest.raises(RuntimeError):
        await phase.run()


@pytest.mark.asyncio
async def test_pickup_full_sequence_succeeds_and_confirms_shape_gone(tmp_path):
    flight = MockFlightBackend()
    camera = MockCameraSource()
    detector = _RectangleUntilPickedUpDetector()
    payload_manager = _PickupTriggeringPayloadManager(detector)
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("MAVI_ALTIGEN", 0.9, True, True, (41.0, 29.0, 15.0), "ilk")
    centering = _RecordingCentering()

    phase = _build_phase(flight, camera, detector, payload_manager, store, centering)
    result = await phase.run()

    assert result is True
    assert [c[0] for c in payload_manager.calls] == [
        'catch_box_down', 'grapple', 'catch_box_up']  # V33 sirasi
    # Real navigation to the recorded Mavi Altıgen GPS position (BUG FIX,
    # continuous audit 2026-08-13) -- previously this never happened at all.
    assert centering.calls == [(41.0, 29.0, GOREV3_TRANSIT_ALTITUDE_M)]
    hold_calls = [c for c in flight.calls if c[0] == 'goto_position_ned_and_hold']
    assert len(hold_calls) >= 3  # align, retreat, advance (+ climb steps)


@pytest.mark.asyncio
async def test_pickup_fails_when_rectangle_never_found(tmp_path):
    flight = MockFlightBackend()
    camera = MockCameraSource()

    class _NeverFindsDetector:
        async def detect(self, frame):
            return []

    detector = _NeverFindsDetector()
    payload_manager = MockPayloadManager()
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("MAVI_ALTIGEN", 0.9, True, True, (41.0, 29.0, 15.0), "ilk")

    phase = _build_phase(flight, camera, detector, payload_manager, store)
    result = await phase.run()

    assert result is False
    assert payload_manager.calls == []  # never reached the servo trigger
