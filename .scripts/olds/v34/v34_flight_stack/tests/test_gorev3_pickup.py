import math

import pytest

from mocks.mock_flight_backend import MockFlightBackend
from mocks.mock_camera_source import MockCameraSource
from mocks.mock_payload_actuator import MockPayloadActuator

from core.detection.types import Detection
from core.mission.gorev3_pickup import Gorev3PickupPhase
from core.mission.rectangle_alignment_strategy import RectangleAlignmentStrategy
from core.position_log.position_store import PositionStore
from core.config.parameters import GOREV3_TRANSIT_ALTITUDE_M
from core.mission.gorev3_pickup import HOOK_ALIGN_ALTITUDE_M


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


class _PickupTriggeringActuator(MockPayloadActuator):
    def __init__(self, detector: _RectangleUntilPickedUpDetector):
        super().__init__()
        self._detector = detector

    async def activate_pickup_mechanism(self, altitude_m=None,
                                        deck_height_m=None, on_retry=None) -> bool:
        result = await super().activate_pickup_mechanism()
        self._detector.picked_up = True  # THIRD MISSION SERVO succeeded -- shape leaves the ground
        return result


class _SyntheticPayloadCamera:
    """Renders the payload where the vehicle would actually see it.

    The pickup phase now closes a VISION loop, so a blank mock frame makes it
    (correctly) refuse to proceed. This double therefore renders a real,
    detectable payload whose pixel position follows the vehicle's NED
    position -- which turns these phase tests into genuine closed-loop tests
    of the shipped detector and the shipped controller, rather than tests of
    a stub.

    Geometry mirrors the nadir pinhole exactly, including the camera lever
    arm and the inward side-wall spill the detector exists to remove.
    """

    FOCAL = 539.94
    RES = (1280, 960)

    def __init__(self, flight, offset_ned=(0.06, -0.04)):
        self.flight = flight
        # The payload is LATCHED to wherever the phase actually descends,
        # plus a deliberate offset. The mission navigates to a recorded GPS
        # fix, so a payload pinned to NED (0,0) would simply be out of frame
        # -- which is a property of the double, not of the phase.
        self.offset_ned = offset_ned
        self.payload_ned = None

    async def start(self):
        return None

    async def stop(self):
        return None

    def get_resolution(self):
        return self.RES

    async def get_frame(self):
        import cv2
        import numpy as np
        from core.config.parameters import CAMERA_LEVER_ARM_BODY_M
        from core.mission.visual_alignment import camera_deck_depth_m
        from core.detection.receiver_detector import (
            DECK_HEIGHT_M, EXPECTED_ASPECT, PAYLOAD_LONG_M,
        )

        w, h = self.RES
        img = np.full((h, w, 3), 200, np.uint8)
        n, e, _d = self.flight._ned_pos
        _lat, _lon, alt = self.flight._global_pos
        depth = camera_deck_depth_m(alt)
        if depth <= 0.05:
            return img
        if self.payload_ned is None:
            if alt > 1.5:
                return img          # too high to have arrived yet
            self.payload_ned = (n + self.offset_ned[0], e + self.offset_ned[1])
        # Render in the BODY frame, honouring the vehicle's actual yaw. The
        # phase yaws to align with the payload's long edge, so a double that
        # assumed yaw 0 would rotate the measured error relative to the
        # commanded correction -- which makes the loop spiral outward instead
        # of converging, and looks exactly like a control-law bug.
        import math as _m
        lev_f, lev_r = CAMERA_LEVER_ARM_BODY_M
        d_n = self.payload_ned[0] - n
        d_e = self.payload_ned[1] - e
        yaw = _m.radians(getattr(self.flight, "_yaw_deg", 0.0) or 0.0)
        fwd = (d_n * _m.cos(yaw) + d_e * _m.sin(yaw)) - lev_f
        rgt = (-d_n * _m.sin(yaw) + d_e * _m.cos(yaw)) - lev_r
        m_per_px = depth / self.FOCAL
        u = w / 2.0 + rgt / m_per_px
        v = h / 2.0 - fwd / m_per_px
        long_px = PAYLOAD_LONG_M * self.FOCAL / depth
        short_px = long_px / EXPECTED_ASPECT
        s = depth / (depth + DECK_HEIGHT_M)
        top = cv2.boxPoints(((u, v), (long_px, short_px), 0.0))
        foot = np.array([[w / 2 + s * (x - w / 2), h / 2 + s * (y - h / 2)]
                         for x, y in top])
        hull = cv2.convexHull(np.vstack([top, foot]).astype(np.float32)).astype(np.int32)
        cv2.fillPoly(img, [hull], (36, 28, 191))
        cv2.fillPoly(img, [top.astype(np.int32)], (36, 28, 191))
        return img


class _RecordingCentering:
    """Records both navigation calls the phase makes.

    `go_to_and_center` was added when Görev 3 Faz 1 moved its alignment to a
    vision-friendly 1.2 m instead of retreating 30 cm (see the phase's own
    note). This double did not follow, so the phase tests failed with
    AttributeError -- a stale double, not a production regression."""

    def __init__(self, converges: bool = True, centers: bool = True):
        self.calls = []           # goto_global_position_and_wait
        self.center_calls = []    # go_to_and_center
        self._converges = converges
        self._centers = centers

    async def goto_global_position_and_wait(self, lat, lon, alt) -> bool:
        self.calls.append((lat, lon, alt))
        return self._converges

    async def go_to_and_center(self, shape_type: str, altitude_m: float = None,
                               alt_tolerance_m: float = None,
                               aim_offset_body_m=None) -> bool:
        self.center_calls.append((shape_type, altitude_m))
        return self._centers


def _build_phase(flight, camera, detector, actuator, store, centering=None):
    return Gorev3PickupPhase(flight, camera, detector, actuator, store, RectangleAlignmentStrategy(),
                             centering or _RecordingCentering())


@pytest.mark.asyncio
async def test_pickup_raises_without_recorded_mavi_altigen(tmp_path):
    flight = MockFlightBackend()
    camera = MockCameraSource()
    detector = _RectangleUntilPickedUpDetector()
    actuator = _PickupTriggeringActuator(detector)
    store = PositionStore(str(tmp_path / "positions.json"))
    phase = _build_phase(flight, camera, detector, actuator, store)

    with pytest.raises(RuntimeError):
        await phase.run()


@pytest.mark.asyncio
async def test_pickup_full_sequence_succeeds_and_confirms_shape_gone(tmp_path):
    flight = MockFlightBackend()
    camera = _SyntheticPayloadCamera(flight)
    detector = _RectangleUntilPickedUpDetector()
    actuator = _PickupTriggeringActuator(detector)
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("MAVI_ALTIGEN", 0.9, True, True, (41.0, 29.0, 15.0), "ilk")
    centering = _RecordingCentering()

    phase = _build_phase(flight, camera, detector, actuator, store, centering)
    result = await phase.run()

    assert result is True
    assert ('activate_pickup_mechanism', {}) in actuator.calls
    # Real navigation to the recorded Mavi Altıgen GPS position (BUG FIX,
    # continuous audit 2026-08-13) -- previously this never happened at all.
    assert centering.calls == [(41.0, 29.0, GOREV3_TRANSIT_ALTITUDE_M)]
    # Alignment happens at the vision-friendly altitude, not at the pickup
    # altitude: at 0.30 m the frame is only 0.71 x 0.53 m and the target
    # falls out of it (measured, mission17).
    assert centering.center_calls == [("KIRMIZI_DIKDORTGEN", HOOK_ALIGN_ALTITUDE_M)]
    hold_calls = [c for c in flight.calls if c[0] == 'goto_position_ned_and_hold']
    assert len(hold_calls) >= 3  # align, translate, descend (+ climb steps)


@pytest.mark.asyncio
async def test_pickup_fails_when_rectangle_never_found(tmp_path):
    flight = MockFlightBackend()
    camera = MockCameraSource()

    class _NeverFindsDetector:
        async def detect(self, frame):
            return []

    detector = _NeverFindsDetector()
    actuator = MockPayloadActuator()
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("MAVI_ALTIGEN", 0.9, True, True, (41.0, 29.0, 15.0), "ilk")

    phase = _build_phase(flight, camera, detector, actuator, store)
    result = await phase.run()

    assert result is False
    assert actuator.calls == []  # never reached the servo trigger


@pytest.mark.asyncio
async def test_pickup_aborts_when_the_real_hook_pose_is_unavailable(tmp_path):
    """Fail-safe for the pose the seating gate depends on.

    Görev 3 Faz 1 now closes the loop on the hook's REAL Gazebo pose. If that
    pose cannot be read there is no way to know whether the hook is in the
    receiver, so the phase must stop rather than fall back to the body-offset
    guess it was built to replace -- that guess is what let acceptance Case 7
    weld a payload from 1.97 m away.
    """
    flight = MockFlightBackend()
    camera = MockCameraSource()
    detector = _RectangleUntilPickedUpDetector()
    actuator = _PickupTriggeringActuator(detector)
    actuator.hook_to_receiver_offset_world = lambda color: None   # pose lost
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("MAVI_ALTIGEN", 0.9, True, True, (41.0, 29.0, 15.0), "ilk")

    phase = _build_phase(flight, camera, detector, actuator, store, _RecordingCentering())
    assert await phase.run() is False
    assert ('activate_pickup_mechanism', {}) not in actuator.calls


@pytest.mark.asyncio
async def test_pickup_closes_the_loop_on_the_seen_receiver(tmp_path):
    """The vehicle must be driven by what the CAMERA sees, not by a constant.

    The payload is rendered at a deliberate offset from wherever the phase
    descends. Nothing tells the phase that offset; the only way to remove it
    is to measure it in the image and fly it out. Convergence therefore proves
    the loop is closed on vision.
    """
    flight = MockFlightBackend()
    camera = _SyntheticPayloadCamera(flight, offset_ned=(0.09, -0.07))
    detector = _RectangleUntilPickedUpDetector()
    actuator = _PickupTriggeringActuator(detector)
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("MAVI_ALTIGEN", 0.9, True, True, (41.0, 29.0, 15.0), "ilk")

    phase = _build_phase(flight, camera, detector, actuator, store, _RecordingCentering())
    assert await phase.run() is True

    holds = [c for c in flight.calls if c[0] == "goto_position_ned_and_hold"]
    assert len(holds) >= 4
    # The vehicle ends up essentially on top of the latched payload, having
    # started a measurable distance from it.
    assert camera.payload_ned is not None
    final_n, final_e, _ = flight._ned_pos
    residual = math.hypot(camera.payload_ned[0] - final_n,
                          camera.payload_ned[1] - final_e)
    start_offset = math.hypot(*camera.offset_ned)
    assert residual < start_offset, "the loop did not reduce the offset it was given"


@pytest.mark.asyncio
async def test_pickup_refuses_safely_when_the_receiver_is_never_seen(tmp_path):
    """Vision loss must stop the phase, not fall back to flying blind.

    The seating gate would refuse the lock anyway, but paying out the winch
    and pressing an unaligned hook onto the payload is exactly the behaviour
    the visual stage exists to prevent.
    """
    flight = MockFlightBackend()
    camera = MockCameraSource()          # blank frames: nothing to see
    detector = _RectangleUntilPickedUpDetector()
    actuator = _PickupTriggeringActuator(detector)
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("MAVI_ALTIGEN", 0.9, True, True, (41.0, 29.0, 15.0), "ilk")

    phase = _build_phase(flight, camera, detector, actuator, store, _RecordingCentering())
    assert await phase.run() is False
    assert ("activate_pickup_mechanism", {}) not in actuator.calls, \
        "no pickup may be attempted without a visual lock on the receiver"
