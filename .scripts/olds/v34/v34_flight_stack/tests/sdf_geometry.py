"""Read the geometry the simulator actually loads, straight from the SDF.

WHY (2026-08-26): three geometry tests hard-coded the pre-3f606696 numbers
(camera 0.35 m forward, payload mounts +-0.28 m). Commit 3f606696 moved the
camera to +0.085 and remounted both payloads under the airframe at +-0.035,
but those constants lived only in the tests, so the tests kept passing
against a vehicle that no longer existed and started failing only when
parameters.py was corrected to match.

Deriving from the SDF removes the whole failure mode: if the model moves,
these helpers move with it, and a stale mission constant fails loudly
instead of a stale test failing spuriously.
"""
import math
import os
import re

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), *([os.pardir] * 5)))
GZ = os.path.join(REPO_ROOT, "Tools", "simulation", "gz")
VEHICLE_SDF = os.path.join(GZ, "models", "x500_mono_cam_down", "model.sdf")
WORLD_SDF = os.path.join(GZ, "worlds", "default.sdf")
LAUNCHER_SH = os.path.join(REPO_ROOT, "safe_sitl_launcher.sh")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def camera_body_offset_m():
    """(forward, right) of mono_cam relative to base_link, PX4 body frame.

    The SDF include pose is FLU (x forward, y left, z up); PX4's body frame
    is FRD, so `right` is the negated SDF y.
    """
    sdf = _read(VEHICLE_SDF)
    block = re.search(r"<include merge='true'>\s*<uri>model://mono_cam</uri>\s*"
                      r"<pose>([^<]+)</pose>", sdf)
    assert block, "mono_cam include pose not found in %s" % VEHICLE_SDF
    parts = [float(v) for v in block.group(1).split()]
    return (parts[0], -parts[1])


def vehicle_spawn_pose():
    """(x, y, yaw) the vehicle is spawned at, from safe_sitl_launcher.sh.

    PX4_GZ_MODEL_POSE is "x,y,z,roll,pitch,yaw"; ROMFS px4-rc.gzsim reads it
    and passes it to Gazebo's model spawn. The launcher is the single source
    of truth for the spawn, so this parses it rather than restating it.
    Missing variable or missing yaw field -> Gazebo's own default (origin,
    yaw 0), which is what actually happens in that case, not a guess.
    """
    m = re.search(r'PX4_GZ_MODEL_POSE\s*=\s*"([^"]+)"', _read(LAUNCHER_SH))
    if not m:
        return (0.0, 0.0, 0.0)
    parts = [float(v) for v in m.group(1).split(",")]
    x = parts[0] if len(parts) > 0 else 0.0
    y = parts[1] if len(parts) > 1 else 0.0
    yaw = parts[5] if len(parts) > 5 else 0.0
    return (x, y, yaw)


def payload_mount_offset_m(color):
    """(forward, right) of a payload model relative to the vehicle, PX4 body frame.

    Payloads are world-loaded and held by a DetachableJoint (ADR-011), so
    their mount arm is the difference between their world pose and the
    vehicle's spawn pose, rotated back out of the spawn yaw.

    CORRECTED 2026-08-30 (single-competition-area migration). This used to
    return the payload's ABSOLUTE world pose as if it were the mount arm,
    on the premise that the payloads "sit directly under the vehicle at the
    origin". That premise was an accident of the old spawn: PX4_GZ_MODEL_POSE
    was "25,0,0,0,0,0" and, before that, unset -- yaw 0 either way, so body Y
    happened to equal world Y, and the payloads' own X happened to be 0.
    Neither holds now: the vehicle spawns at (0, -25) with yaw = pi/2, and
    generate_competition_area.py writes the payload world poses by ROTATING
    the body-frame mount offsets by that yaw. Reading the world pose raw
    reported the payload 25 m to the vehicle's right and turned this helper --
    whose whole purpose is to make a stale mission constant fail loudly --
    into a guard that fires against the CORRECT value.

    Frames: the SDF pose is FLU (x forward, y left); PX4 body frame is FRD,
    so `right` is the negated body y.
    """
    sdf = _read(WORLD_SDF)
    block = re.search(r'<model name="payload_%s">\s*<pose>([^<]+)</pose>' % color, sdf)
    assert block, "payload_%s pose not found in %s" % (color, WORLD_SDF)
    parts = [float(v) for v in block.group(1).split()]

    sx, sy, yaw = vehicle_spawn_pose()
    dx, dy = parts[0] - sx, parts[1] - sy
    c, s = math.cos(yaw), math.sin(yaw)
    body_forward = dx * c + dy * s          # R_z(-yaw) . (dx, dy)
    body_left = -dx * s + dy * c
    return (body_forward, -body_left)
