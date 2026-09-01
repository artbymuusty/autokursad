"""The closed-loop visual alignment controller.

Built from callables so the whole control law is testable without a simulator,
a camera or PX4. What is pinned here is the safety behaviour, because this
module commands aircraft motion:

  * it never moves on a single frame
  * it never moves while blind
  * it never moves further than its travel budget
  * it converges without hunting
  * it reports failure instead of silently giving up

and, most importantly, it NEVER authorises a lock. That stays with
core/mission/hook_seating.py.
"""
import asyncio
import math

import numpy as np
import pytest

from core.mission.visual_alignment import (
    ALIGN_DWELL_S, ALIGN_MAX_LOST_FRAMES, ALIGN_MAX_STEP_M, ALIGN_MAX_TRAVEL_M,
    ALIGN_MIN_CONFIDENCE, ALIGN_MIN_STREAK, ALIGN_TOLERANCE_M,
    VisualHookAligner, body_to_ned, camera_deck_depth_m,
    depth_from_detection, receiver_offset_body_m,
)
from core.detection.receiver_detector import ReceiverDetection


FOCAL = 539.94


def _det(u=640.0, v=480.0, conf=0.9, depth=None):
    """A detection whose RADIUS is consistent with its depth.

    The controller now solves depth from radius_px rather than from altitude
    telemetry, so a fake with a fixed radius would silently impose a fixed
    depth and break the metric conversion. radius = focal * mouth_r / depth.
    """
    from core.detection.receiver_detector import RECEIVER_MOUTH_R_M
    d = depth if depth is not None else camera_deck_depth_m(0.45)
    return ReceiverDetection(u=u, v=v, radius_px=FOCAL * RECEIVER_MOUTH_R_M / d,
                             angle_deg=0.0, confidence=conf,
                             method="top_face_deshadow")


class Rig:
    """A one-axis plant: the vehicle moves, the receiver stays put."""

    def __init__(self, start_err=(0.10, 0.0), hook=(0.0, 0.0), conf=0.9,
                 blind_after=None, drift=0.0):
        self.n, self.e = 0.0, 0.0
        self.err_n, self.err_e = start_err          # receiver - hook, in NED
        self.hook = hook
        self.conf = conf
        self.blind_after = blind_after
        self.drift = drift
        self.commands = []
        self.frames = 0

    async def get_frame(self):
        self.frames += 1
        if self.blind_after is not None and self.frames > self.blind_after:
            return None
        return np.zeros((960, 1280, 3), np.uint8)

    async def get_alt_m(self):
        return 0.45

    async def get_yaw_deg(self):
        return 0.0

    async def get_position_ned(self):
        return (self.n, self.e, -0.45)

    def get_hook_ned_offset(self):
        return self.hook

    async def goto(self, n, e, alt, yaw):
        self.commands.append((n, e))
        moved_n, moved_e = n - self.n, e - self.e
        self.n, self.e = n, e
        # the plant: moving the vehicle by d reduces the error by d
        self.err_n -= moved_n - self.drift
        self.err_e -= moved_e

    def aligner(self):
        # The detector is stubbed: this file tests the CONTROL LAW, and the
        # detector has its own measured benchmark in test_receiver_detector.py.
        def fake_detect(frame, color, deck_depth_m=None, principal_point=None):
            if self.conf is None:
                return None
            from core.config.parameters import CAMERA_LEVER_ARM_BODY_M
            lev_f, lev_r = CAMERA_LEVER_ARM_BODY_M
            intr_f = FOCAL
            depth = camera_deck_depth_m(0.45)
            # The camera sits lev_f forward of the body origin, and
            # receiver_offset_body_m adds that back. Render the pixel the real
            # camera would produce, i.e. with the lever arm removed, so the
            # round trip is exercised rather than bypassed.
            want_fwd = self.err_n + self.hook[0]
            want_rgt = self.err_e + self.hook[1]
            dy = -(want_fwd - lev_f) * intr_f / depth
            dx = (want_rgt - lev_r) * intr_f / depth
            return _det(640.0 + dx, 480.0 + dy, self.conf, depth=depth)
        return VisualHookAligner(
            get_frame=self.get_frame, get_alt_m=self.get_alt_m,
            get_yaw_deg=self.get_yaw_deg, get_position_ned=self.get_position_ned,
            get_hook_ned_offset=self.get_hook_ned_offset, goto_ned_and_hold=self.goto,
            color="red", detector=fake_detect)


# --------------------------------------------------------------- geometry --

def test_camera_depth_accounts_for_the_mount_being_below_base_link():
    """Measured live off dynamic_pose/info: camera_link sits at model z=+0.050,
    i.e. 0.19 m BELOW base_link -- the opposite of the natural assumption."""
    assert camera_deck_depth_m(0.45) == pytest.approx(0.45 + 0.050 - 0.070)


def test_body_to_ned_rotates_the_way_the_flight_stack_does():
    assert body_to_ned(1.0, 0.0, 0.0) == pytest.approx((1.0, 0.0))
    assert body_to_ned(1.0, 0.0, 90.0) == pytest.approx((0.0, 1.0), abs=1e-9)
    assert body_to_ned(0.0, 1.0, 90.0) == pytest.approx((-1.0, 0.0), abs=1e-9)


def test_pixel_offsets_map_to_body_axes_with_the_validated_signs():
    """Image +y is body AFT and image +x is body RIGHT. This convention is
    taken verbatim from CenteringController._freeze_target_estimate; getting it
    wrong makes the loop diverge rather than converge."""
    depth = 0.43
    below = receiver_offset_body_m(_det(v=480.0 + 100, depth=depth), depth, 1280, 960)
    right = receiver_offset_body_m(_det(u=640.0 + 100, depth=depth), depth, 1280, 960)
    centre = receiver_offset_body_m(_det(depth=depth), depth, 1280, 960)
    assert below[0] < centre[0], "target below centre must be AFT of centre"
    assert right[1] > centre[1], "target right of centre must be RIGHT of centre"


# ---------------------------------------------------------- convergence ----

@pytest.mark.asyncio
async def test_converges_from_a_realistic_offset():
    rig = Rig(start_err=(0.10, -0.06))
    res = await rig.aligner().align(0.45, 0.0, timeout_s=20)
    assert res.converged, res.reason
    assert res.final_error_m <= ALIGN_TOLERANCE_M
    assert res.travel_m <= ALIGN_MAX_TRAVEL_M


@pytest.mark.asyncio
async def test_does_not_move_before_a_detection_streak():
    """One frame is not a measurement. Nothing may be commanded until the
    detector has agreed with itself ALIGN_MIN_STREAK times."""
    rig = Rig(start_err=(0.10, 0.0), blind_after=ALIGN_MIN_STREAK - 1)
    await rig.aligner().align(0.45, 0.0, timeout_s=3)
    assert rig.commands == []


@pytest.mark.asyncio
async def test_never_commands_while_blind():
    """Holding still is the only safe action when the measurement is gone."""
    rig = Rig(start_err=(0.20, 0.0), blind_after=0)
    res = await rig.aligner().align(0.45, 0.0, timeout_s=5)
    assert not res.converged
    assert res.reason == "receiver_lost"
    assert rig.commands == []
    assert res.lost_frames >= ALIGN_MAX_LOST_FRAMES


@pytest.mark.asyncio
async def test_low_confidence_detections_are_ignored_entirely():
    rig = Rig(start_err=(0.15, 0.0), conf=ALIGN_MIN_CONFIDENCE - 0.05)
    res = await rig.aligner().align(0.45, 0.0, timeout_s=4)
    assert not res.converged
    assert rig.commands == []


@pytest.mark.asyncio
async def test_single_step_is_clamped_so_it_cannot_outrun_the_rope():
    """The hook is a pendulum with a measured 0.831 s period. A large jump
    converts position error into swing instead of removing it."""
    rig = Rig(start_err=(1.0, 0.0))
    await rig.aligner().align(0.45, 0.0, timeout_s=3)
    assert rig.commands, "expected at least one command"
    first_n, first_e = rig.commands[0]
    assert math.hypot(first_n, first_e) <= ALIGN_MAX_STEP_M + 1e-6


@pytest.mark.asyncio
async def test_gives_up_on_the_travel_budget_rather_than_chasing_forever():
    """A mis-detection that keeps receding must stop the loop, not walk the
    aircraft across the field."""
    rig = Rig(start_err=(5.0, 0.0), drift=ALIGN_MAX_STEP_M)   # error never shrinks
    res = await rig.aligner().align(0.45, 0.0, timeout_s=30)
    assert not res.converged
    assert res.reason == "travel_budget_exhausted"
    assert res.travel_m <= ALIGN_MAX_TRAVEL_M + ALIGN_MAX_STEP_M


@pytest.mark.asyncio
async def test_reports_timeout_instead_of_hanging(monkeypatch):
    """Isolate the deadline from the travel budget.

    The budget is raised for this test only, because a plant that never
    responds burns the real 0.60 m budget in milliseconds -- that is the
    travel-budget failure mode, which has its own test above. What is under
    test here is that the loop has a DEADLINE at all and reports it."""
    import core.mission.visual_alignment as va
    monkeypatch.setattr(va, "ALIGN_MAX_TRAVEL_M", 1e6)

    rig = Rig(start_err=(0.015, 0.0), drift=0.0)

    async def frozen(n, e, alt, yaw):      # commands accepted, plant ignores them
        rig.commands.append((n, e))
    rig.goto = frozen
    res = await rig.aligner().align(0.45, 0.0, timeout_s=2)
    assert not res.converged
    assert res.reason == "timeout"
    assert rig.commands, "it should have kept trying until the deadline"


@pytest.mark.asyncio
async def test_convergence_requires_a_dwell_not_a_single_good_sample():
    """Momentary agreement is not alignment; the rope swings through centre."""
    rig = Rig(start_err=(0.002, 0.0))       # already inside tolerance
    res = await rig.aligner().align(0.45, 0.0, timeout_s=10)
    assert res.converged
    span = res.samples[-1]["t"] - res.samples[0]["t"]
    assert span >= ALIGN_DWELL_S * 0.8, f"converged after only {span:.2f}s"


@pytest.mark.asyncio
async def test_error_is_measured_against_the_hook_not_the_airframe():
    """THE point of the module. With the hook displaced from the airframe by
    the rope, aligning the VEHICLE on the receiver would leave the hook off by
    exactly that displacement."""
    hook = (0.05, -0.03)                     # rope-displaced hook
    rig = Rig(start_err=(0.0, 0.0), hook=hook)   # hook ALREADY on the receiver
    res = await rig.aligner().align(0.45, 0.0, timeout_s=6)
    assert res.converged
    # nothing should have been commanded: the hook is already there, even
    # though the airframe is not
    assert rig.commands == [] or all(
        math.hypot(n - 0.0, e - 0.0) < 1e-6 for n, e in rig.commands)


# ------------------------------------------------------ depth from image --

def test_depth_is_solved_from_the_image_not_from_telemetry():
    """The metric conversion scales with depth, so a depth error scales the
    whole answer. Measured live: PX4's reported altitude gave a 52.3 mm
    estimate where the truth was 22.6 mm -- about 10%, which is the hover
    error between the reported altitude and the true camera height.

    The mouth's true size is known from the CAD, so the detector's own radius
    gives the depth from the same pixels the centre came from."""
    from core.detection.receiver_detector import RECEIVER_MOUTH_R_M
    for want in (0.28, 0.43, 0.88, 1.30):
        d = _det(depth=want)
        got = depth_from_detection(d, FOCAL)
        assert got == pytest.approx(want, rel=1e-6), want


def test_implausible_radius_yields_no_depth_so_the_caller_can_fall_back():
    bad = ReceiverDetection(u=640.0, v=480.0, radius_px=0.4, angle_deg=0.0,
                            confidence=0.9, method="x")
    assert depth_from_detection(bad, FOCAL) is None
    huge = ReceiverDetection(u=640.0, v=480.0, radius_px=1e6, angle_deg=0.0,
                             confidence=0.9, method="x")
    assert depth_from_detection(huge, FOCAL) is None
    assert depth_from_detection(None, FOCAL) is None


def test_image_depth_is_independent_of_reported_altitude():
    """A hover error in the altitude telemetry must not move the answer."""
    d = _det(depth=0.88)
    assert depth_from_detection(d, FOCAL) == pytest.approx(0.88, rel=1e-6)
    # telemetry would have said something else entirely
    assert camera_deck_depth_m(0.70) != pytest.approx(0.88, rel=0.02)
