"""The pickup gate must read the REAL hook pose and refuse to lock unseated.

Companion to test_hook_seating.py: that file tests the geometry predicate in
isolation, this one tests that GzPayloadActuator actually wires it up --
that it composes hook_body_link's world pose from the live Gazebo stream,
that hook motion relative to the airframe changes the answer (which a fixed
body offset could not), and that /hook/attach is never published unless the
seating gate passed.
"""
import asyncio
import math

import pytest

from core.mission.hook_seating import (
    HOOK_NOSE_OFFSET_M, RECEIVER_DECK_OFFSET_M, SeatState,
)
from gz_system.gz_pose_monitor import GzPoseMonitor
from gz_system.gz_payload_actuator import GzPayloadActuator, HOOK_LINK_NAME

VEH = "x500_mono_cam_down_0"
LEVEL = (0.0, 0.0, 0.0, 1.0)


def monitor_with(veh_pos, hook_link_pos, payload_pos, veh_quat=LEVEL, age=0.0):
    """A GzPoseMonitor primed exactly the way the live stream primes it:
    model poses in world, link poses relative to their model."""
    import time
    m = GzPoseMonitor("default")
    stamp = time.time() - age
    for name, pos, quat in ((VEH, veh_pos, veh_quat),
                            (HOOK_LINK_NAME, hook_link_pos, LEVEL),
                            ("payload_red", payload_pos, LEVEL)):
        m._poses[name] = pos
        m._quats[name] = quat
        m._stamps[name] = stamp
    return m


def actuator_with(monitor):
    return GzPayloadActuator("svc", "default", pose_monitor=monitor)


def hook_link_z_for(insertion_m, payload_z, veh_z):
    """hook_body_link z IN THE MODEL FRAME giving the wanted insertion."""
    world_z = payload_z + RECEIVER_DECK_OFFSET_M - HOOK_NOSE_OFFSET_M - insertion_m
    return world_z - veh_z


# ------------------------------------------------------------ pose source --

def test_hook_world_pose_is_composed_from_model_and_link_poses():
    m = monitor_with(veh_pos=(5.0, 7.0, 2.0),
                     hook_link_pos=(-0.090, 0.0, -0.133),
                     payload_pos=(5.0, 7.0, 0.035))
    act = actuator_with(m)
    pose = act.get_hook_world_pose()
    assert pose is not None
    pos, quat, age = pose
    assert pos == pytest.approx((4.910, 7.0, 1.867), abs=1e-6)
    assert age < 0.5


def test_missing_hook_link_yields_no_pose_so_pickup_can_fail_safe():
    m = monitor_with((0, 0, 2.0), (-0.09, 0, -0.133), (0, 0, 0.035))
    del m._poses[HOOK_LINK_NAME]
    act = actuator_with(m)
    assert act.get_hook_world_pose() is None
    assert act.seating_geometry("red") is None


def test_rope_displaced_hook_changes_geometry_a_body_offset_could_not():
    """REGRESSION for the removed fixed x = -0.090 assumption.

    The vehicle pose is held IDENTICAL in both samples; only the hook's
    model-frame pose moves, exactly as it does when the rope swings. A gate
    that derived the hook from the airframe would return the same answer
    twice. Measured swing displacement in flight reached 19.86 cm.
    """
    veh = (0.0, 0.0, 0.30)
    payload = (0.0, 0.0, 0.035)
    z_link = hook_link_z_for(0.001, payload[2], veh[2])

    plumb = actuator_with(monitor_with(veh, (0.0, 0.0, z_link), payload))
    swung = actuator_with(monitor_with(veh, (0.150, 0.0, z_link), payload))

    g_plumb = plumb.seating_geometry("red")
    g_swung = swung.seating_geometry("red")
    assert g_plumb.lateral_m == pytest.approx(0.0, abs=1e-6)
    assert g_swung.lateral_m == pytest.approx(0.150, abs=1e-6)
    # and the swung hook must not be seatable at that displacement
    assert any("lateral" in f for f in g_swung.failures())
    # the correction vector points back at the receiver axis
    d_east, d_north = swung.hook_to_receiver_offset_world("red")
    assert d_east == pytest.approx(-0.150, abs=1e-6)
    assert d_north == pytest.approx(0.0, abs=1e-6)


def test_hook_pose_follows_vehicle_yaw_without_any_hardcoded_offset():
    """With the vehicle yawed 90 deg, a hook at model (-0.090, 0) must appear
    at world (0, -0.090) -- composed, not assumed."""
    q90 = (0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4))
    m = monitor_with((0.0, 0.0, 1.0), (-0.090, 0.0, 0.0), (0.0, 0.0, 0.035),
                     veh_quat=q90)
    pos, _q, _age = actuator_with(m).get_hook_world_pose()
    assert pos == pytest.approx((0.0, -0.090, 1.0), abs=1e-6)


# ------------------------------------------------------------- the gate ----

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.mark.asyncio
async def test_seating_gate_accepts_a_genuinely_seated_hook():
    veh = (0.0, 0.0, 0.30)
    payload = (0.0, 0.0, 0.035)
    m = monitor_with(veh, (0.0, 0.0, hook_link_z_for(0.001, payload[2], veh[2])), payload)
    act = actuator_with(m)
    assert await act._await_seating("red", 3.0) is True
    assert act.hook_seat_state() is SeatState.SEATED


@pytest.mark.asyncio
async def test_seating_gate_refuses_the_case7_geometry():
    """Hook 1.97 m above the receiver, well aligned horizontally."""
    veh = (0.0, 0.0, 2.0)
    payload = (0.0242, 0.0, 0.035)
    m = monitor_with(veh, (0.0, 0.0, hook_link_z_for(-1.970, payload[2], veh[2])), payload)
    act = actuator_with(m)
    assert await act._await_seating("red", 1.5) is False
    assert act.hook_seat_state() is SeatState.APPROACHING


@pytest.mark.asyncio
async def test_seating_gate_refuses_a_stale_pose():
    veh = (0.0, 0.0, 0.30)
    payload = (0.0, 0.0, 0.035)
    m = monitor_with(veh, (0.0, 0.0, hook_link_z_for(0.001, payload[2], veh[2])),
                     payload, age=2.0)
    act = actuator_with(m)
    assert await act._await_seating("red", 1.5) is False


@pytest.mark.asyncio
async def test_pickup_never_publishes_attach_when_seating_fails():
    """The end-to-end safety property: no seating -> no /hook/attach -> no
    fixed joint -> no false LOCKED."""
    veh = (0.0, 0.0, 2.0)
    payload = (0.0, 0.0, 0.035)
    m = monitor_with(veh, (0.0, 0.0, hook_link_z_for(-1.970, payload[2], veh[2])), payload)
    act = actuator_with(m)

    published = []

    async def fake_pub(topic, msgtype, payload_str):
        published.append(topic)
        return True

    act._gz_pub = fake_pub
    import gz_system.gz_payload_actuator as A
    old_timeout, old_attempts = A.HOOK_CONTACT_TIMEOUT_S, A.HOOK_PICKUP_ATTEMPTS
    A.HOOK_CONTACT_TIMEOUT_S, A.HOOK_PICKUP_ATTEMPTS = 0.6, 2
    try:
        assert await act.activate_pickup_mechanism() is False
    finally:
        A.HOOK_CONTACT_TIMEOUT_S, A.HOOK_PICKUP_ATTEMPTS = old_timeout, old_attempts

    assert A.HOOK_ATTACH_TOPIC not in published, published
    assert act.is_hook_attached() is False
    assert act.hook_seat_state() is SeatState.APPROACHING
    # the winch was still driven -- refusing to lock is not refusing to try
    assert A.HOOK_WINCH_TOPIC in published
