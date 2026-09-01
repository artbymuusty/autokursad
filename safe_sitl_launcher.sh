#!/bin/bash
# safe_sitl_launcher.sh
# Deterministic PX4 SITL + Gazebo Orchestration Wrapper
# Enforces the safety invariants defined in the orchestration contract.

echo "==========================================================="
echo "[ORCHESTRATOR] Initializing pre-flight state validation..."
echo "==========================================================="

# ---------------------------------------------------------
# 1. ENVIRONMENT NEUTRALITY
# ---------------------------------------------------------
echo "[ORCHESTRATOR] 1/6 Scrubbing environment variables..."
unset PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION
unset PYTHONPATH

# GZ_IP pins gz-transport's discovery/advertise address. process_manager.py,
# camera_service.py and unpause/verify_gazebo_ready() all force GZ_IP=127.0.0.1
# for every Python-side tool that talks to Gazebo -- but this launcher (the
# side that actually starts PX4+Gazebo) never set it, leaving it to whatever
# gz-transport auto-selects on this host. On a machine with more than one
# active network interface that can put the simulator and the Python tooling
# on different discovery paths, so gz_bridge/camera_service never see each
# other's topics even though both are genuinely running. Pin it here too so
# every process in the chain agrees.
#
# GZ_PARTITION matters for the same reason and was the actual macOS blocker:
# gz-transport's DEFAULT partition is "<hostname>:<username>", and this Mac's
# hostname is DHCP/reverse-DNS derived, so it changes with the network. The
# sim and anything launched later ended up in different partitions and never
# discovered each other. Both values now come from one shared file used by the
# sim, mission and camera launchers alike.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)/.scripts/olds/v32/v32_flight_stack/gz_system/gz_env.sh"
echo "[ORCHESTRATOR] gz-transport env: GZ_PARTITION=$GZ_PARTITION GZ_IP=$GZ_IP"

# ---------------------------------------------------------
# 2. PRE-LAUNCH STATE PURGE (Process-level enforcement)
# ---------------------------------------------------------
echo "[ORCHESTRATOR] 2/6 Terminating existing/orphaned Gazebo and PX4 processes..."

# Kill any orphaned PX4 SITL processes to ensure no conflicting sessions
# ADR-010 R3: ANCHORED patterns. These used to be `pkill -9 -f "px4"`,
# which matches ANY process whose full command line merely mentions px4 --
# including unrelated shells, editors, and tooling. That is not
# hypothetical: it kills the caller's own helper shells, and the
# verify-idle gate below (same unanchored pattern) then reports FATAL and
# exits WITHOUT starting the simulator, which is the most likely reason
# several "relaunch" attempts on 2026-08-17 left no PX4 running and no
# ULog on disk at all. Anchoring to the real binary path and the real
# `gz sim` invocation matches the processes we actually mean.
pkill -9 -f "px4_sitl_default/bin/px4$" 2>/dev/null
pkill -9 -f "bin/px4$" 2>/dev/null

# Kill any Gazebo server processes or zombie transport listeners
#
# BUG FIX: these patterns used to say "gz-sim" (with a hyphen). The actual
# running process is "gz" (the CLI dispatcher) invoked with "sim" as a
# subcommand -- its real /proc/<pid>/cmdline is "gz sim --verbose=1 -r -s
# <world>.sdf" (a space, not a hyphen), so `pkill -9 -f "gz-sim"` has never
# matched it. Confirmed directly: a gz-sim server PID survived multiple
# consecutive runs of this script, each one printing "Pre-launch invariants
# met" while that same already-running (and, in one investigation, already
# crashed/toppled) world and vehicle model kept being reused underneath every
# supposedly-fresh PX4 relaunch. "gz sim" (space) matches the real dispatcher
# invocation; "gz sim -g" (the GUI client) matches the same pattern too.
pkill -9 -f "gz-transport-topic" 2>/dev/null
pkill -9 -f "gz sim" 2>/dev/null
pkill -9 -f "ruby-mri" 2>/dev/null

# Give OS a moment to reap processes
sleep 2

# ---------------------------------------------------------
# 3. VERIFY IDLE STATE
# ---------------------------------------------------------
echo "[ORCHESTRATOR] 3/6 Verifying process null state..."

# ADR-010 R3: anchored for the same reason as the pkill patterns above --
# an unanchored "px4" here made the gate trip on any shell that merely
# mentioned px4, aborting the launch before it began.
_ORPHANS="$(pgrep -f 'bin/px4$'; pgrep -f 'gz sim'; pgrep -f 'gz-transport-topic')"
if [ -n "$_ORPHANS" ]; then
    echo "[ORCHESTRATOR] FATAL: Failed to clear orphaned simulation processes."
    echo "[ORCHESTRATOR] Manual intervention required. Processes still alive:"
    echo "$_ORPHANS" | while read -r _p; do ps -p "$_p" -o pid,args= 2>/dev/null; done
    exit 1
fi

echo "  -> [OK] Pre-launch invariants met. System is in a clean idle state."

# ---------------------------------------------------------
# 4. CONTROLLED SITL BOOTSTRAP
# ---------------------------------------------------------
echo "[ORCHESTRATOR] 4/6 Bootstrapping PX4 SITL natively..."
echo "==========================================================="

# Navigate to the PX4 root directory (assuming script is in root or .scripts)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
if [[ "$SCRIPT_DIR" == *".scripts"* ]]; then
    cd "$SCRIPT_DIR/../.." || exit 1
else
    cd "$SCRIPT_DIR" || exit 1
fi

# ---------------------------------------------------------
# 4a. COMPETITION AREA LAYOUT (regenerated on every launch)
# ---------------------------------------------------------
# Placed AFTER the purge (steps 2-3) and BEFORE make: never rewrite
# default.sdf while a running simulator still has it open.
#
# The script needs only the standard library (argparse/datetime/math/
# random/re/pathlib), so the `unset PYTHONPATH` at step 1 and the fact
# that no venv is resolved until step 6 are both irrelevant -- plain
# python3 is enough.
#
# It rewrites exactly two things: the four shape <include>s between the
# KURSAD_COMPETITION_AREA markers, and the payload_red/payload_blue
# poses (pinned to PX4_GZ_MODEL_POSE below). Everything else in the world
# file is untouched, and it takes its own timestamped backup first.
#
# HARD FAIL on error: flying an unknown or stale layout is worse than not
# flying. If layout generation fails, no simulator starts.
# The path is RELATIVE on purpose: both branches of the if/fi above leave
# the working directory at the PX4 repo root, whereas $SCRIPT_DIR points at
# .scripts when this launcher is invoked from there.
#
# ORDER: this runs BEFORE `export PX4_GZ_MODEL_POSE` below, and that is
# fine -- the generator parses the pose out of THIS FILE with a regex, it
# does not read the environment variable. So the pose it pins the payloads
# to is always the one written below, whichever order the shell runs in.
echo "[ORCHESTRATOR] 4a/6 Generating competition area layout..."
if ! python3 Tools/simulation/gz/worlds/generate_competition_area.py; then
    echo "[ORCHESTRATOR] FATAL: could not generate the competition area layout."
    echo "[ORCHESTRATOR] SITL not started (an unknown layout is not flyable)."
    exit 1
fi

# VEHICLE SPAWN POSE (2026-08-30, single competition area).
# ROMFS/px4fmu_common/init.d-posix/px4-rc.gzsim reads this var (comma-
# separated x,y,z,roll,pitch,yaw) at line 115-121 and passes it to Gazebo's
# model spawn if set; unset (still Gazebo's own fallback) means origin,
# yaw 0.
#
# X=0  -- centred on the competition area's X centreline (the area spans
#         X in [-15, +15]; see Tools/simulation/gz/worlds/generate_competition_area.py).
# Y=-25 -- 25 m OUTSIDE the area's south end (the area spans Y in [0, 100]),
#         i.e. facing the course from beyond it. LEADIN is 20 m, so the
#         first route waypoint sits at (0, -20) and the vehicle flies 5 m
#         north into the lead-in; the whole route is then monotonically
#         north. The previous spawn (25, 0) sat level with the area and
#         made the route double back south first.
# yaw=pi/2 -- Gazebo's world frame is ENU, so yaw 0 faces EAST. pi/2 turns
#         the vehicle to face NORTH (+Y), i.e. at the course. Nadir camera,
#         so this only sets the initial heading; PX4 yaws to the route in
#         AUTO mission anyway.
#         WRITTEN AT FULL DOUBLE PRECISION on purpose. The payload mount
#         offsets are BODY-frame, so generate_competition_area.py rotates
#         them by this yaw to get world coordinates, and
#         tests/sdf_geometry.py rotates them back to recover the body arm
#         and compares it to PAYLOAD_MOUNT_OFFSET_BODY_M within 1e-9. A
#         truncated 1.5707963 leaves cos(yaw) = 2.7e-8 instead of 6.1e-17,
#         which shows up as a ~9.4e-10 phantom forward offset -- inside the
#         tolerance, but only barely. Full precision removes the question.
#
# NOTE: the two payload models in default.sdf are pinned to THIS pose by
# generate_competition_area.py (step 4a above), not by hand. Their
# DetachableJoint binds them to the vehicle at world load, so a spawn that
# drifts away from them turns the joint into a tether staked to the ground:
# measured 2026-08-30, the vehicle climbed to 4.90 m, was pulled back down
# in 2.7 s, then sat on the ground in MISSION mode for 483 s. Change the
# pose here and only here; the generator follows it.
export PX4_GZ_MODEL_POSE="0,-25,0,0,0,1.5707963267948966"

echo "[ORCHESTRATOR] 5/6 Handing control to PX4 (make px4_sitl gz_x500_mono_cam_down)..."
# NOTE: this runs in the FOREGROUND for the entire simulator session, so 5/6
# is the last counter on screen until PX4 exits. Step 6/6 prints only after
# shutdown; that is expected, not a hang.

# Pass control to PX4
# PX4 will now correctly detect a clean topology and launch exactly
# one unified PX4 + Gazebo simulation authority.
# NOTE: payload release is done by two DetachableJoint plugins in
# Tools/simulation/gz/models/x500_mono_cam_down/model.sdf:59-71 (ADR-011,
# which replaced the older PayloadDropSystem plugin). The vehicle model to
# spawn is x500_mono_cam_down, NOT x500_mono_cam_down_payload.
# CORRECTION (2026-08-30): an earlier version of this note claimed the
# "_payload" model directory "no longer exists". It does still exist
# (Tools/simulation/gz/models/x500_mono_cam_down_payload/, with a model.sdf).
# What does not exist is an airframe for it -- ROMFS ships only
# 4014_gz_x500_mono_cam_down -- so it has no make target and must not be
# used here.
make px4_sitl gz_x500_mono_cam_down

# ---------------------------------------------------------
# 5. POST-LAUNCH: CLEAR A STUCK LAND MODE  (ADR-010 R3)
# ---------------------------------------------------------
# After a mission lands, PX4 stays in flight_mode=LAND even once disarmed
# and ON_GROUND, and refuses to arm from there (is_armable False while
# every individual pre-arm check passes). Three runs on 2026-08-17 died on
# this, each after ~3 minutes of futile waiting; commanding HOLD clears it
# in about 2 seconds. This lives here, in the launcher/hygiene layer,
# deliberately: it is a rig-reset concern, not mission logic, and the
# mission must never quietly re-arm a vehicle an operator left in LAND.
_HYGIENE="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)/.scripts/olds/v32/clear_land_mode.py"
if [ -f "$_HYGIENE" ]; then
    echo "[ORCHESTRATOR] 6/6 Clearing any stuck LAND mode before arming..."
    source "$(dirname "${BASH_SOURCE[0]}")/.scripts/olds/v32/resolve_python.sh" 2>/dev/null
    "${PYTHON_BIN:-python3}" "$_HYGIENE" || true
fi
