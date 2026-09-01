import math

import pytest

from mocks.mock_flight_backend import MockFlightBackend
from mocks.mock_payload_actuator import MockPayloadActuator

from core.detection.detection_feed import DetectionFeed
from core.detection.types import Detection
from core.mission.gorev3_redrop import Gorev3RedropPhase
from core.position_log.position_store import PositionStore
from core.config.parameters import GOREV3_DESCENT_ALTITUDE_M


class _RecordingCentering:
    """The phase now aligns the CARRIED LOAD after centring the aircraft, so
    it needs the detection feed the real CenteringController exposes. Passing
    flight=None and no feed was fine while the phase only called
    go_to_and_center; it is a stale double now."""

    def __init__(self, converges: bool = True, detection_feed=None):
        self.calls = []
        self._converges = converges
        self.detection_feed = detection_feed or DetectionFeed(stale_after_s=3600.0)

    async def go_to_and_center(self, shape_type: str, altitude_m: float,
                               alt_tolerance_m: float = None, aim_offset_body_m=None) -> bool:
        self.calls.append(('go_to_and_center', shape_type, altitude_m))
        return self._converges


def _feed_with_target(u=640.0, v=480.0):
    """A detection feed holding a KIRMIZI_UCGEN at a chosen pixel."""
    feed = DetectionFeed(stale_after_s=3600.0)
    feed.publish([Detection(shape_type="KIRMIZI_UCGEN", confidence=0.9,
                            center_px=(u, v),
                            bbox_px=(u - 60, v - 50, u + 60, v + 50))])
    return feed


def _phase(tmp_path, actuator=None, centering=None, flight=None, save=True):
    store = PositionStore(str(tmp_path / "positions.json"))
    if save:
        store.try_save("KIRMIZI_UCGEN", 0.9, True, True, (41.0, 29.0, 15.0), "ilk")
    return Gorev3RedropPhase(flight=flight or MockFlightBackend(),
                             actuator=actuator or MockPayloadActuator(),
                             position_store=store,
                             centering=centering or _RecordingCentering())


@pytest.mark.asyncio
async def test_redrop_raises_without_recorded_kirmizi_ucgen(tmp_path):
    actuator = MockPayloadActuator()
    store = PositionStore(str(tmp_path / "positions.json"))
    centering = _RecordingCentering()
    phase = Gorev3RedropPhase(flight=MockFlightBackend(), actuator=actuator,
                              position_store=store, centering=centering)

    with pytest.raises(RuntimeError):
        await phase.run()


@pytest.mark.asyncio
async def test_redrop_centers_at_descent_altitude_then_triggers_grab_servo(tmp_path):
    actuator = MockPayloadActuator()
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("KIRMIZI_UCGEN", 0.9, True, True, (41.0, 29.0, 15.0), "ilk")
    centering = _RecordingCentering(detection_feed=_feed_with_target())

    phase = Gorev3RedropPhase(flight=MockFlightBackend(), actuator=actuator,
                              position_store=store, centering=centering)
    result = await phase.run()

    assert result is True
    # Centring now happens where the marker is FULLY VISIBLE, not at the
    # release altitude: the 1 m triangle is 121% of the frame width at 0.30 m,
    # so a detection there is a clipped fragment whose centroid is not the
    # triangle's centre. The descent to the release altitude happens after.
    from core.mission.gorev3_redrop import GOREV3_PLACE_ALIGN_ALTITUDE_M
    assert centering.calls == [
        ('go_to_and_center', 'KIRMIZI_UCGEN', GOREV3_PLACE_ALIGN_ALTITUDE_M)]
    assert GOREV3_PLACE_ALIGN_ALTITUDE_M > GOREV3_DESCENT_ALTITUDE_M
    holds = [c for c in phase.flight.calls if c[0] == 'goto_position_ned_and_hold']
    assert any(abs(c[1]['down_m'] + GOREV3_DESCENT_ALTITUDE_M) < 1e-6 for c in holds), \
        "it must still descend to the release altitude before dropping"
    assert ('activate_drop_mechanism', {}) in actuator.calls


@pytest.mark.asyncio
async def test_redrop_still_drops_when_final_centering_does_not_converge(tmp_path):
    """Best-effort: a failed final re-centering must not abort the drop."""
    actuator = MockPayloadActuator()
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("KIRMIZI_UCGEN", 0.9, True, True, (41.0, 29.0, 15.0), "ilk")
    centering = _RecordingCentering(converges=False, detection_feed=_feed_with_target())

    phase = Gorev3RedropPhase(flight=MockFlightBackend(), actuator=actuator,
                              position_store=store, centering=centering)
    result = await phase.run()

    assert result is True
    assert ('activate_drop_mechanism', {}) in actuator.calls
