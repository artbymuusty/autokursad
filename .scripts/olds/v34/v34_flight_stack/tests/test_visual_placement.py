"""Placing a carried payload on a visually-detected destination.

The existing redrop centred the AIRCRAFT on the target with vision. The load
does not hang under the aircraft -- the lock welds it to the hook at body
(-0.090, 0) plus rope swing -- so a perfectly centred aircraft still drops
about 9 cm off. Görev 2's measured drop scatter of 13-34 cm was dominated by
exactly this term, which is why shrinking the mount arm from 0.28 m to
0.035 m shrank the error with it.

These tests pin the correction and, more importantly, the refusals: this
module commands aircraft motion just before a release.
"""
import asyncio
import math

import pytest

from core.detection.types import Detection
from core.mission.visual_alignment import CAMERA_Z_ABOVE_MODEL_ORIGIN_M
from core.mission.visual_placement import (
    MARKER_HEIGHT_M, PLACE_MAX_CORRECTIONS, PLACE_MAX_STEP_M, PLACE_TOLERANCE_M,
    VisualPlacementAligner, carried_payload_ned_offset, marker_offset_body_m,
)

RES = (1280, 960)
FOCAL = 539.94


def _det(u=640.0, v=480.0, conf=0.9):
    return Detection(shape_type="KIRMIZI_UCGEN", confidence=conf,
                     center_px=(u, v), bbox_px=(u - 60, v - 50, u + 60, v + 50))


class Rig:
    """One-axis plant: the aircraft moves, the ground target does not."""

    def __init__(self, dest_ned=(0.20, -0.10), carried=(-0.090, 0.0),
                 alt=0.30, seen=True, speed=0.0):
        self.n = self.e = 0.0
        self.dest = dest_ned
        self.carried = carried
        self.alt = alt
        self.seen = seen
        self.speed = speed
        self.commands = []

    def get_detection(self):
        if not self.seen:
            return None
        # Render the destination where the camera would actually see it,
        # including the lever arm the production code corrects for.
        from core.config.parameters import CAMERA_LEVER_ARM_BODY_M
        lev_f, lev_r = CAMERA_LEVER_ARM_BODY_M
        depth = self.alt + CAMERA_Z_ABOVE_MODEL_ORIGIN_M - MARKER_HEIGHT_M
        fwd = (self.dest[0] - self.n) - lev_f
        rgt = (self.dest[1] - self.e) - lev_r
        m_per_px = depth / FOCAL
        return _det(640.0 + rgt / m_per_px, 480.0 - fwd / m_per_px)

    async def get_alt_m(self):
        return self.alt

    async def get_yaw_deg(self):
        return 0.0

    async def get_position_ned(self):
        return (self.n, self.e, -self.alt)

    def get_carried_offset(self):
        return self.carried

    def get_rel_speed(self):
        return self.speed

    async def goto(self, n, e, alt, yaw):
        self.commands.append((n, e))
        self.n, self.e = n, e

    def aligner(self):
        return VisualPlacementAligner(
            get_detection=self.get_detection, get_alt_m=self.get_alt_m,
            get_yaw_deg=self.get_yaw_deg, get_position_ned=self.get_position_ned,
            get_carried_offset=self.get_carried_offset,
            goto_ned_and_hold=self.goto, get_rel_speed=self.get_rel_speed,
            resolution=RES)


# ---------------------------------------------------------------- geometry --

def test_a_target_at_frame_centre_is_at_the_camera_lever_arm():
    """With the marker under the optical axis it is not under the BODY
    origin: the camera sits 0.085 m forward of it."""
    from core.config.parameters import CAMERA_LEVER_ARM_BODY_M
    fwd, rgt = marker_offset_body_m((640, 480), 0.30, *RES)
    assert (fwd, rgt) == pytest.approx(CAMERA_LEVER_ARM_BODY_M)


def test_markers_are_measured_against_the_ground_not_the_payload_deck():
    """The arena shapes are painted on the ground (z=0.003); the receiver is
    0.070 m up on a deck. Using the wrong plane scales the whole answer."""
    assert MARKER_HEIGHT_M < 0.01
    near = marker_offset_body_m((740, 480), 0.30, *RES)
    far = marker_offset_body_m((740, 480), 1.20, *RES)
    assert abs(far[1]) > abs(near[1]), "same pixel, higher up, means further in metres"


def test_pixel_offsets_use_the_stack_wide_sign_convention():
    centre = marker_offset_body_m((640, 480), 0.30, *RES)
    below = marker_offset_body_m((640, 580), 0.30, *RES)
    right = marker_offset_body_m((740, 480), 0.30, *RES)
    assert below[0] < centre[0], "target below centre is AFT"
    assert right[1] > centre[1], "target right of centre is RIGHT"


def test_no_altitude_means_no_measurement():
    assert marker_offset_body_m((640, 480), None, *RES) is None
    assert marker_offset_body_m((640, 480), 0.0, *RES) is None


# --------------------------------------------------------- carried payload --

def test_carried_load_position_comes_from_the_hook():
    """The lock welds the payload to the hook, so there is no second pose to
    estimate -- and no reason to prefer a worse one."""
    class _Act:
        def hook_nose_ned_offset_m(self):
            return (-0.09, 0.01)
    assert carried_payload_ned_offset(_Act()) == (-0.09, 0.01)


def test_an_actuator_without_a_hook_pose_yields_none():
    class _Bare:
        pass
    assert carried_payload_ned_offset(_Bare()) is None


def test_a_raising_actuator_yields_none_rather_than_propagating():
    class _Boom:
        def hook_nose_ned_offset_m(self):
            raise RuntimeError("no pose")
    assert carried_payload_ned_offset(_Boom()) is None


# ----------------------------------------------------------------- control --

@pytest.mark.asyncio
async def test_aligns_the_carried_load_not_the_airframe():
    """THE point. The load hangs 0.09 m behind the body origin, so putting the
    AIRCRAFT over the target leaves the load 0.09 m short."""
    rig = Rig(dest_ned=(0.20, -0.10), carried=(-0.090, 0.0))
    res = await rig.aligner().align(0.30, 0.0)
    assert res.aligned, res.reason
    load_n = rig.n + rig.carried[0]
    load_e = rig.e + rig.carried[1]
    load_err = math.hypot(load_n - rig.dest[0], load_e - rig.dest[1])
    airframe_err = math.hypot(rig.n - rig.dest[0], rig.e - rig.dest[1])
    assert load_err <= PLACE_TOLERANCE_M, load_err
    # The AIRFRAME is deliberately left off-target, by about the hook offset:
    # that displacement is the whole point, and a controller that centred the
    # aircraft instead would show the reverse.
    assert airframe_err > load_err, (airframe_err, load_err)
    assert airframe_err == pytest.approx(abs(rig.carried[0]), abs=0.06)


@pytest.mark.asyncio
async def test_already_placed_load_is_not_nudged():
    rig = Rig(dest_ned=(0.0, 0.0), carried=(0.0, 0.0))
    res = await rig.aligner().align(0.30, 0.0)
    assert res.aligned
    assert rig.commands == []


@pytest.mark.asyncio
async def test_refuses_when_the_destination_is_never_seen():
    rig = Rig(seen=False)
    res = await rig.aligner().align(0.30, 0.0, timeout_s=1.5)
    assert not res.aligned
    assert res.reason == "destination_not_seen"
    assert rig.commands == []


@pytest.mark.asyncio
async def test_refuses_when_the_carried_load_pose_is_unknown():
    """Dropping on a guess is exactly the behaviour this replaces."""
    rig = Rig()
    rig.get_carried_offset = lambda: None
    res = await rig.aligner().align(0.30, 0.0, timeout_s=1.5)
    assert not res.aligned
    assert rig.commands == []


@pytest.mark.asyncio
async def test_does_not_move_before_a_detection_streak():
    class _Flaky(Rig):
        def __init__(self):
            super().__init__()
            self.n_calls = 0

        def get_detection(self):
            self.n_calls += 1
            return super().get_detection() if self.n_calls == 1 else None
    rig = _Flaky()
    await rig.aligner().align(0.30, 0.0, timeout_s=1.5)
    assert rig.commands == []


@pytest.mark.asyncio
async def test_a_single_step_is_clamped():
    """0.25 m out: far enough that an unclamped step would exceed the limit,
    close enough that the marker is still fully inside the frame -- a target
    off the edge is now rejected as clipped, which is a different test."""
    rig = Rig(dest_ned=(0.25, 0.0), carried=(0.0, 0.0))
    await rig.aligner().align(0.30, 0.0, timeout_s=3)
    assert rig.commands
    n, e = rig.commands[0]
    assert math.hypot(n, e) <= PLACE_MAX_STEP_M + 1e-6


@pytest.mark.asyncio
async def test_correction_budget_is_bounded():
    """A destination that keeps receding must stop the loop, not walk the
    aircraft across the field just before a release."""
    rig = Rig(dest_ned=(50.0, 0.0), carried=(0.0, 0.0))
    res = await rig.aligner().align(0.30, 0.0, timeout_s=30)
    assert not res.aligned
    assert res.corrections <= PLACE_MAX_CORRECTIONS


# ------------------------------------------------------- clipped markers --

def test_a_marker_touching_the_frame_edge_is_rejected():
    """THE regression. The Kirmizi Ucgen is 1 m on a side and the frame at the
    0.30 m release altitude is 0.83 m wide -- 121% of it. The centroid of a
    clipped shape is not the centroid of the shape: measured on the
    2026-08-27 mission, the aligner reported 44.4 mm against such a fragment
    and the payload landed 89.7 cm from the true centre."""
    clipped = Detection(shape_type="KIRMIZI_UCGEN", confidence=0.9,
                        center_px=(640, 480), bbox_px=(0, 100, 900, 700))
    assert VisualPlacementAligner._is_clipped(clipped, 1280, 960)
    inside = Detection(shape_type="KIRMIZI_UCGEN", confidence=0.9,
                       center_px=(640, 480), bbox_px=(300, 300, 900, 700))
    assert not VisualPlacementAligner._is_clipped(inside, 1280, 960)


@pytest.mark.asyncio
async def test_a_clipped_marker_produces_no_command():
    """Refusing costs a retry; trusting a fragment steers the aircraft."""
    rig = Rig(dest_ned=(0.20, 0.0))
    real = rig.get_detection

    def clipped():
        d = real()
        return Detection(shape_type=d.shape_type, confidence=d.confidence,
                         center_px=d.center_px, bbox_px=(0, 0, 1280, 960))
    rig.get_detection = clipped
    res = await rig.aligner().align(0.30, 0.0, timeout_s=1.5)
    assert not res.aligned
    assert res.reason == "destination_not_seen"
    assert rig.commands == []


@pytest.mark.asyncio
async def test_the_measured_target_position_is_reported_for_later_use():
    """The marker does not move, so a good measurement taken where the camera
    can see it properly is usable lower down, where it cannot."""
    rig = Rig(dest_ned=(0.15, -0.05), carried=(-0.09, 0.0))
    res = await rig.aligner().align(0.30, 0.0)
    assert res.target_ned is not None
    assert res.target_ned == pytest.approx(rig.dest, abs=0.02)


@pytest.mark.asyncio
async def test_settle_onto_ned_drives_the_load_not_the_airframe():
    from core.mission.visual_placement import settle_onto_ned
    state = {"n": 0.0, "e": 0.0}
    carried = (-0.09, 0.0)
    cmds = []

    async def get_pos():
        return (state["n"], state["e"], -0.30)

    async def goto(n, e, alt, yaw):
        cmds.append((n, e))
        state["n"], state["e"] = n, e

    res = await settle_onto_ned((0.30, 0.10), get_pos, lambda: carried, goto,
                                0.30, 0.0, get_rel_speed=lambda: 0.0)
    assert res is not None and res <= PLACE_TOLERANCE_M
    load = (state["n"] + carried[0], state["e"] + carried[1])
    assert math.hypot(load[0] - 0.30, load[1] - 0.10) <= PLACE_TOLERANCE_M


@pytest.mark.asyncio
async def test_settle_refuses_without_a_load_pose():
    from core.mission.visual_placement import settle_onto_ned
    cmds = []

    async def get_pos():
        return (0.0, 0.0, -0.30)

    async def goto(n, e, alt, yaw):
        cmds.append((n, e))

    assert await settle_onto_ned((1.0, 0.0), get_pos, lambda: None, goto,
                                 0.30, 0.0) is None
    assert cmds == []
