"""Seating gate: the geometry that decides whether the hook may be locked.

These tests exist because of two defects the 2026-08-26 acceptance test
found in the previous gate (XY distance <= 5 cm -> weld):

  * hook position was INFERRED from the vehicle body pose plus a fixed
    x = -0.090 offset, which a rope-hung hook does not obey;
  * there was no vertical term at all, so Case 7 welded and hoisted a
    payload from 1.97 m above it.

Every threshold asserted here is derived from the exported CAD in
core/mission/hook_seating.py, so a change to the meshes that invalidates a
threshold shows up as a failure here rather than as a false pickup in flight.
"""
import math

import pytest

from core.mission.hook_seating import (
    HOOK_NOSE_OFFSET_M,
    HOOK_POSE_MAX_AGE_S,
    RECEIVER_DECK_OFFSET_M,
    RECEIVER_MOUTH_RADIUS_M,
    SEAT_DWELL_S,
    SEAT_MAX_LATERAL_M,
    SEAT_MAX_REL_SPEED_MPS,
    SEAT_MAX_TILT_RAD,
    SEAT_MIN_INSERTION_M,
    SeatState,
    SeatingEvaluator,
    compute_seating_geometry,
)

LEVEL = (0.0, 0.0, 0.0, 1.0)
PAYLOAD_AT = (2.0, 3.0, 0.035)          # a payload resting on the ground

# Hook link origin height that puts the nose exactly `insertion` below the
# receiver deck plane, both bodies level.
#   insertion = (z_p + DECK) - (z_h + NOSE)   with NOSE negative
def hook_z_for(insertion_m, payload_z=PAYLOAD_AT[2]):
    return payload_z + RECEIVER_DECK_OFFSET_M - HOOK_NOSE_OFFSET_M - insertion_m


def geom(lateral_m=0.0, insertion_m=0.0, tilt_rad=0.0,
         rel_speed=0.0, age=0.0, payload=PAYLOAD_AT):
    hook = (payload[0] + lateral_m, payload[1], hook_z_for(insertion_m, payload[2]))
    hq = (math.sin(tilt_rad / 2.0), 0.0, 0.0, math.cos(tilt_rad / 2.0))
    return compute_seating_geometry(hook, hq, payload, LEVEL,
                                    rel_speed_mps=rel_speed, pose_age_s=age)


def dwell_to_seated(g, evaluator=None, step=0.05, total=None):
    """Feed one geometry repeatedly across the dwell window."""
    ev = evaluator or SeatingEvaluator()
    total = SEAT_DWELL_S + step if total is None else total
    t = 0.0
    state = ev.update(g, t)
    while t < total:
        t += step
        state = ev.update(g, t)
    return state, ev


# --------------------------------------------------------------- geometry --

def test_geometry_matches_the_measured_seated_pickup():
    """A real locked pickup measured hook_z - payload_z = 0.0988 m; the CAD
    stack-up says that is the nose resting ~0.85 mm into the deck plane."""
    payload_z = 0.035
    g = compute_seating_geometry(
        (0.0, 0.0, payload_z + 0.0988), LEVEL,
        (0.0, 0.0, payload_z), LEVEL, rel_speed_mps=0.0, pose_age_s=0.0)
    assert g.insertion_m == pytest.approx(0.00085, abs=1e-4)
    assert g.lateral_m == pytest.approx(0.0, abs=1e-9)
    assert g.is_seatable()


def test_lateral_is_measured_perpendicular_to_a_tilted_receiver_axis():
    """A pitched payload must not be scored with a naive XY/Z split."""
    ang = math.radians(30.0)
    pq = (0.0, math.sin(ang / 2), 0.0, math.cos(ang / 2))   # pitch about +Y
    payload = (0.0, 0.0, 0.5)
    axis = (math.sin(ang), 0.0, math.cos(ang))
    deck = tuple(payload[i] + axis[i] * RECEIVER_DECK_OFFSET_M for i in range(3))
    # place the nose exactly on the axis, 5 mm below the deck
    nose = tuple(deck[i] - axis[i] * 0.005 for i in range(3))
    hook = tuple(nose[i] - (math.sin(ang), 0.0, math.cos(ang))[i] * HOOK_NOSE_OFFSET_M
                 for i in range(3))
    hq = (0.0, math.sin(ang / 2), 0.0, math.cos(ang / 2))
    g = compute_seating_geometry(hook, hq, payload, pq, rel_speed_mps=0.0, pose_age_s=0.0)
    assert g.lateral_m == pytest.approx(0.0, abs=1e-6)
    assert g.insertion_m == pytest.approx(0.005, abs=1e-6)
    assert g.tilt_rad == pytest.approx(0.0, abs=1e-6)


# --------------------------------------------------------------- positive --

def test_valid_seated_geometry_reaches_seated_after_dwell():
    state, ev = dwell_to_seated(geom(lateral_m=0.004, insertion_m=0.001))
    assert state is SeatState.SEATED
    assert ev.last_failures == []


def test_dwell_completion_is_what_authorises_attach():
    """Before the dwell elapses the state must be CAPTURE_CANDIDATE, not
    SEATED -- 'near the receiver' and 'seated' are different answers."""
    g = geom(lateral_m=0.002, insertion_m=0.002)
    ev = SeatingEvaluator()
    assert ev.update(g, 0.0) is SeatState.CAPTURE_CANDIDATE
    assert ev.update(g, SEAT_DWELL_S * 0.5) is SeatState.CAPTURE_CANDIDATE
    assert ev.update(g, SEAT_DWELL_S) is SeatState.SEATED


def test_seatable_at_the_full_bore_mouth_radius():
    """The lateral limit is the receiver counterbore mouth, so a hook exactly
    on that radius is still the last seatable pose."""
    g = geom(lateral_m=RECEIVER_MOUTH_RADIUS_M - 1e-6, insertion_m=0.001)
    assert g.is_seatable(), g.failures()


# --------------------------------------------------------------- negative --

def test_case7_regression_hook_1970mm_above_receiver_must_never_seat():
    """MANDATORY REGRESSION -- acceptance Case 7, 2026-08-26.

    Horizontal alignment was good (24.2 mm) but the hook hung 1.97 m ABOVE
    the receiver. The old XY-only gate reported capture, published
    /hook/attach, welded the payload while it sat on the ground and hoisted
    it; measured post-lock hook<->payload distance was 1.68 m.

    This must now be rejected on the axial term, and no amount of dwell may
    ever turn it into SEATED.
    """
    g = geom(lateral_m=0.0242, insertion_m=-1.970)
    assert not g.is_seatable()
    assert any("too_high" in f for f in g.failures()), g.failures()
    state, _ = dwell_to_seated(g, total=10.0)
    assert state is SeatState.APPROACHING


def test_hook_below_the_valid_seat_must_not_seat():
    """Nose driven past the CAD insertion limit (payload lifted off it, or
    the hook under the payload) is not a seat either."""
    g = geom(lateral_m=0.0, insertion_m=0.20)
    assert not g.is_seatable()
    assert any("too_deep" in f for f in g.failures()), g.failures()


def test_lateral_outside_the_bore_mouth_must_not_seat():
    g = geom(lateral_m=SEAT_MAX_LATERAL_M + 0.001, insertion_m=0.0)
    assert not g.is_seatable()
    assert any("lateral" in f for f in g.failures()), g.failures()


def test_excessive_relative_speed_must_not_seat():
    """A hook swinging through the receiver at speed is a pass-through, not
    a capture."""
    g = geom(lateral_m=0.002, insertion_m=0.001,
             rel_speed=SEAT_MAX_REL_SPEED_MPS + 0.01)
    assert not g.is_seatable()
    assert any("rel_speed" in f for f in g.failures()), g.failures()


def test_excessive_tilt_must_not_seat():
    g = geom(lateral_m=0.0, insertion_m=0.001, tilt_rad=SEAT_MAX_TILT_RAD + 0.05)
    assert not g.is_seatable()
    assert any("tilt" in f for f in g.failures()), g.failures()


def test_valid_geometry_shorter_than_the_dwell_must_not_seat():
    """The swing-through case: geometry is momentarily perfect, then gone.
    A single good sample must never be enough."""
    good = geom(lateral_m=0.001, insertion_m=0.001)
    bad = geom(lateral_m=0.20, insertion_m=0.001)
    ev = SeatingEvaluator()
    t = 0.0
    for _ in range(4):                      # ~0.20 s of valid geometry
        assert ev.update(good, t) is SeatState.CAPTURE_CANDIDATE
        t += 0.05
    assert ev.update(bad, t) is SeatState.APPROACHING       # dwell broken
    t += 0.05
    # even resuming perfect geometry restarts the clock
    assert ev.update(good, t) is SeatState.CAPTURE_CANDIDATE


def test_stale_hook_pose_must_not_seat():
    g = geom(lateral_m=0.0, insertion_m=0.0, age=HOOK_POSE_MAX_AGE_S + 0.1)
    assert not g.is_seatable()
    assert any("stale_pose" in f for f in g.failures()), g.failures()
    state, _ = dwell_to_seated(g, total=5.0)
    assert state is SeatState.APPROACHING


def test_missing_hook_pose_breaks_the_dwell_and_never_seats():
    """Absence of evidence must not become evidence of seating."""
    good = geom(lateral_m=0.001, insertion_m=0.001)
    ev = SeatingEvaluator()
    ev.update(good, 0.0)
    ev.update(good, 0.1)
    assert ev.update(None, 0.15) is SeatState.APPROACHING
    assert ev.last_failures == ["no_pose"]
    # the clock restarted, so the old partial dwell cannot carry over
    assert ev.update(good, 0.2) is SeatState.CAPTURE_CANDIDATE
