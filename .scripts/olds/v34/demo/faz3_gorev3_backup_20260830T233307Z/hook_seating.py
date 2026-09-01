"""Physical seating validation for the KURSAD40 V4 payload hook.

WHY THIS MODULE EXISTS (acceptance test, 2026-08-26)
----------------------------------------------------
The pickup gate used to be one line in gz_payload_actuator.py:

    if hypot(hook_xy - payload_xy) <= 0.05:  -> publish /hook/attach

with `hook_xy` INFERRED from the vehicle body pose plus a fixed
x = -0.090 offset. Two independent defects, both measured:

  * The hook hangs on a four-segment rope, so it is NOT at a fixed body
    offset. Measured error of the inferred position against the real
    Gazebo pose: mean 0.86 cm, p95 2.76 cm, max 8.23 cm during the pickup
    window and 19.86 cm during transport -- against a 5 cm gate.

  * There was no vertical term at all. Acceptance Case 7 held the hook
    2.42 cm laterally from the receiver but 1.97 m ABOVE it; the old gate
    reported capture, welded the payload to the hook while the payload sat
    on the ground, and hoisted it. Measured post-lock hook<->payload
    distance: 1.68 m.

This module replaces that with a geometric predicate evaluated on the REAL
hook pose, in the RECEIVER's own frame, held for a dwell time.

WHAT IS AND IS NOT SIMULATED
----------------------------
Simulated here: the geometry of hook-vs-receiver, from the exported CAD.
NOT simulated anywhere in this build: magnetic force, funnel contact, servo
travel, cam/follower mechanics. The receiver bore has NO collision geometry
in the world SDF, so the hook cannot physically enter it -- it rests on the
payload's box collision top. This module is therefore an APPROXIMATION: it
answers "would this pose seat, per the CAD?" rather than observing a
physical insertion. The final lock remains a runtime Gazebo fixed joint
(HookAttachSystem); see gz_payload_actuator.activate_pickup_mechanism.

GEOMETRY, MEASURED FROM THE EXPORTED MESHES (not from comments)
---------------------------------------------------------------
Tools/simulation/gz/models/kursad_payload/meshes/payload_body.stl, radius
profile about the part axis (CAD frame, mm; link frame = CAD + 8.0 mm):

    CAD z   r_min   feature                       link z
    +27.00  23.98   deck top face                 +35.00
    +16.50  23.25   counterbore mouth  O46.50     +24.50
    +12.75  14.50   lead-in chamfer end O29.00    +20.75
    + 9.00  11.00   through hole       O22.00     +17.00
      0.00   6.50   magnet seat        O13.00     + 8.00
    - 2.20   6.20   target disc pocket O12.40     + 5.80

Tools/simulation/gz/models/kursad_hook/meshes/core_lower.stl (hook_body_link
frame, mm) -- the insertion nose:

    z -64.65  nose bottom face, r_max 10.43
    z -64.42 .. -51.82   r_max grows 11.25 -> 13.00  (the O26 nose)
    z -47.85 and above   r_max 22.50                 (the O45 shell)

So the nose is O26 over its first 13 mm and the shell above it is O45,
against a O46.50 counterbore 10.5 mm deep. Every threshold below is derived
from those numbers.
"""
import math
from enum import Enum
from typing import NamedTuple, Optional

# --------------------------------------------------------------------------
# GEOMETRY CONSTANTS -- straight off the meshes above. Metres.
# --------------------------------------------------------------------------

# hook_body_link origin -> nose bottom face. core_lower.stl z minimum.
HOOK_NOSE_OFFSET_M: float = -0.06465
# Largest radius of the insertion nose (the part that must enter the bore).
HOOK_NOSE_RADIUS_M: float = 0.01300
# payload link origin -> deck top face. CAD +27.00 mm + 8.00 mm link offset.
RECEIVER_DECK_OFFSET_M: float = 0.03500
# Counterbore mouth radius, CAD z +16.50.
RECEIVER_MOUTH_RADIUS_M: float = 0.02325
# Depth of the counterbore: deck top (+27.00) down to the chamfer end
# (+12.75). This is the axial length over which the bore can hold the nose.
RECEIVER_BORE_DEPTH_M: float = 0.01425
# Nose travel available before the O26 nose meets the O22 through-hole:
# deck top (+27.00) down to the through hole (+9.00).
RECEIVER_MAX_INSERTION_M: float = 0.01800

# --------------------------------------------------------------------------
# SEATING THRESHOLDS -- each one derived, none chosen to make a run pass.
# --------------------------------------------------------------------------

# LATERAL. For the receiver to capture the hook at all, the nose AXIS must
# be inside the counterbore mouth: outside it the nose lands on the flat
# deck and no amount of lowering, magnet pull or chamfer will draw it in.
# That boundary is exactly the mouth radius.
#   Note the stricter number this deliberately does NOT use: for the O26
#   nose to be FULLY inside the O46.50 bore you need
#   23.25 - 13.00 = 10.25 mm. That distinction is real on hardware but is
#   not physically simulated here (the bore has no collision), so gating on
#   it would assert precision this build cannot observe. The mouth radius is
#   the honest, CAD-anchored boundary.
SEAT_MAX_LATERAL_M: float = RECEIVER_MOUTH_RADIUS_M          # 0.02325

# AXIAL. Insertion depth is measured DOWN the receiver axis from the deck
# top face to the hook nose bottom face:
#     depth > 0  nose is below the deck plane (inside the bore)
#     depth = 0  nose exactly on the deck plane
#     depth < 0  nose is above the deck -- not seated
# The receiver bore has no collision in this build, so a real pickup rests
# the nose on the deck at depth ~= 0 (measured +0.85 mm, solver compliance).
# The lower bound is a tolerance band around that, small enough that it can
# never be satisfied by a hook hovering above the payload; the upper bound
# is the CAD travel limit plus the same tolerance.
SEAT_TOLERANCE_M: float = 0.004
SEAT_MIN_INSERTION_M: float = -SEAT_TOLERANCE_M              # -0.004
SEAT_MAX_INSERTION_M: float = RECEIVER_MAX_INSERTION_M + SEAT_TOLERANCE_M   # 0.022

# TILT. The receiver is rotationally symmetric about its axis, so yaw is
# meaningless here; what matters is the angle between the hook axis and the
# receiver axis. The jam limit is set by the chamfer: the O26 nose must pass
# a bore that has narrowed to O29 (r 14.50) 3.75 mm below the mouth, i.e.
#     atan((14.50 - 13.00) / 3.75) = 21.8 deg.
# 15 deg keeps a clear margin inside that. A plumb-hanging hook measures
# 0.005-0.9 deg, so this is never the binding constraint in practice.
SEAT_MAX_TILT_RAD: float = math.radians(15.0)

# DWELL. Derived from the MEASURED rope dynamics, not chosen: the pendulum
# period is 0.831 s (acceptance test, 6 m lateral step). A hook swinging
# with amplitude A spends only
#     (T / pi) * asin(w / A)
# of each half-cycle inside a window of half-width w. For w = 23.25 mm and a
# 50 mm swing amplitude that is 0.128 s; for a 30 mm amplitude, 0.235 s.
# Requiring 0.30 s therefore cannot be satisfied by a hook merely swinging
# through the envelope -- it has to be resting in it.
SEAT_DWELL_S: float = 0.30

# RELATIVE SPEED. Bound so the hook cannot traverse the bore's engagement
# depth within one dwell window -- i.e. a fast pass-through can never look
# seated: 0.01425 m / 0.30 s = 0.0475 m/s. Rounded to 0.05 m/s, which also
# absorbs the differentiation noise of a 48 Hz pose stream. A hook resting
# on the deck measures ~0.
SEAT_MAX_REL_SPEED_MPS: float = 0.05

# POSE FRESHNESS. The Gazebo pose stream runs at ~48 Hz. 0.5 s is ~24 missed
# frames -- long enough not to trip on scheduler jitter, short enough that a
# dead stream cannot be mistaken for a valid geometry sample. A stale pose
# must FAIL the gate, never pass it.
HOOK_POSE_MAX_AGE_S: float = 0.5


class SeatState(Enum):
    """Where the hook is in the capture sequence.

    APPROACHING and CAPTURE_CANDIDATE are both "not seated" -- they are kept
    distinct because the difference between 'near the receiver' and 'seated'
    is precisely what the old gate could not express.
    """
    APPROACHING = "APPROACHING"              # geometry does not satisfy seating
    CAPTURE_CANDIDATE = "CAPTURE_CANDIDATE"  # geometry valid, dwell not yet met
    SEATED = "SEATED"                        # valid continuously for SEAT_DWELL_S
    LOCKING = "LOCKING"                      # /hook/attach sent, awaiting /hook/state
    LOCKED = "LOCKED"                        # lock confirmed by the plugin


class SeatingGeometry(NamedTuple):
    """Hook pose expressed in the receiver's own frame."""
    lateral_m: float          # perpendicular distance to the receiver axis
    insertion_m: float        # depth below the deck plane, along the axis
    tilt_rad: float           # hook axis vs receiver axis
    rel_speed_mps: float      # |d(hook - payload)/dt|
    pose_age_s: float

    def failures(self) -> list:
        """Every threshold this geometry violates. Empty == seatable."""
        bad = []
        if self.pose_age_s > HOOK_POSE_MAX_AGE_S:
            bad.append(f"stale_pose({self.pose_age_s:.2f}s>{HOOK_POSE_MAX_AGE_S}s)")
        if self.lateral_m > SEAT_MAX_LATERAL_M:
            bad.append(f"lateral({self.lateral_m*1000:.1f}mm>{SEAT_MAX_LATERAL_M*1000:.1f}mm)")
        if self.insertion_m < SEAT_MIN_INSERTION_M:
            bad.append(f"too_high({self.insertion_m*1000:+.1f}mm<{SEAT_MIN_INSERTION_M*1000:+.1f}mm)")
        if self.insertion_m > SEAT_MAX_INSERTION_M:
            bad.append(f"too_deep({self.insertion_m*1000:+.1f}mm>{SEAT_MAX_INSERTION_M*1000:+.1f}mm)")
        if self.tilt_rad > SEAT_MAX_TILT_RAD:
            bad.append(f"tilt({math.degrees(self.tilt_rad):.1f}deg>"
                       f"{math.degrees(SEAT_MAX_TILT_RAD):.1f}deg)")
        if self.rel_speed_mps > SEAT_MAX_REL_SPEED_MPS:
            bad.append(f"rel_speed({self.rel_speed_mps:.3f}>{SEAT_MAX_REL_SPEED_MPS}m/s)")
        return bad

    def is_seatable(self) -> bool:
        return not self.failures()

    def describe(self) -> str:
        return (f"lat={self.lateral_m*1000:6.1f}mm ins={self.insertion_m*1000:+7.1f}mm "
                f"tilt={math.degrees(self.tilt_rad):5.1f}deg "
                f"v={self.rel_speed_mps:5.3f}m/s age={self.pose_age_s:.2f}s")


def _rotate(q, v):
    """Rotate vector v by quaternion q = (x, y, z, w)."""
    x, y, z, w = q
    vx, vy, vz = v
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx))


def compute_seating_geometry(hook_pos, hook_quat, payload_pos, payload_quat,
                             rel_speed_mps: float, pose_age_s: float) -> SeatingGeometry:
    """Express the hook's pose in the receiver frame.

    hook_pos/hook_quat  : WORLD pose of hook_body_link (NOT a body-offset estimate)
    payload_pos/..._quat: WORLD pose of the payload link (receiver axis = its +Z)

    The receiver is a bore about the payload's local +Z through its origin,
    opening at the deck top face. 'lateral' is measured perpendicular to that
    axis and 'insertion' along it, because that is the axis the bore actually
    constrains -- a plain XY/Z split would be wrong the moment the payload is
    not level.
    """
    axis = _rotate(payload_quat, (0.0, 0.0, 1.0))
    deck = tuple(payload_pos[i] + axis[i] * RECEIVER_DECK_OFFSET_M for i in range(3))
    nose_off = _rotate(hook_quat, (0.0, 0.0, HOOK_NOSE_OFFSET_M))
    nose = tuple(hook_pos[i] + nose_off[i] for i in range(3))

    v = tuple(nose[i] - deck[i] for i in range(3))
    along = sum(v[i] * axis[i] for i in range(3))          # <0 => below the deck
    perp = tuple(v[i] - along * axis[i] for i in range(3))
    lateral = math.sqrt(sum(c * c for c in perp))

    hook_axis = _rotate(hook_quat, (0.0, 0.0, 1.0))
    dot = max(-1.0, min(1.0, sum(hook_axis[i] * axis[i] for i in range(3))))

    return SeatingGeometry(lateral_m=lateral,
                           insertion_m=-along,
                           tilt_rad=math.acos(dot),
                           rel_speed_mps=rel_speed_mps,
                           pose_age_s=pose_age_s)


class SeatingEvaluator:
    """Tracks the dwell requirement across successive geometry samples.

    Deliberately dependency-free (no clock, no Gazebo): the caller supplies
    `now`, so the whole gate is unit-testable without a simulator.
    """

    def __init__(self, dwell_s: float = SEAT_DWELL_S):
        self.dwell_s = dwell_s
        self._valid_since: Optional[float] = None
        self.state = SeatState.APPROACHING
        self.last: Optional[SeatingGeometry] = None
        self.last_failures: list = []

    def reset(self) -> None:
        self._valid_since = None
        self.state = SeatState.APPROACHING
        self.last = None
        self.last_failures = []

    def dwell_elapsed(self, now: float) -> float:
        if self._valid_since is None:
            return 0.0
        return now - self._valid_since

    def update(self, geom: Optional[SeatingGeometry], now: float) -> SeatState:
        """Feed one sample; returns the resulting state.

        A missing geometry (no hook pose at all) is treated exactly like a
        failed one: it breaks the dwell. Absence of evidence must never be
        evidence of seating.
        """
        self.last = geom
        if geom is None:
            self.last_failures = ["no_pose"]
            self._valid_since = None
            self.state = SeatState.APPROACHING
            return self.state

        self.last_failures = geom.failures()
        if self.last_failures:
            self._valid_since = None
            self.state = SeatState.APPROACHING
            return self.state

        if self._valid_since is None:
            self._valid_since = now
        if (now - self._valid_since) >= self.dwell_s:
            self.state = SeatState.SEATED
        else:
            self.state = SeatState.CAPTURE_CANDIDATE
        return self.state
