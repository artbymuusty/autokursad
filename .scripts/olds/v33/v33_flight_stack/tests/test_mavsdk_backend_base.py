"""goto_position_ned_and_hold(): absolute-vs-relative root-cause fix
(2026-08-21).

Root cause, proven live in SITL during the Görev 3 Faz 1 navigation
investigation: this used to build PositionNedYaw(north_m, east_m, ...)
straight from its arguments -- an ABSOLUTE local-NED setpoint, identical
semantics to goto_position_ned(). Every real caller (Gorev3PickupPhase /
Gorev3FinishPhase) passes near-zero north_m/east_m (0, +/-0.3, +/-0.6)
describing a move relative to wherever the vehicle already is ("0.3m
geride", "0.6m ileri alma pozisyonuna"), never a real absolute target. With
the vehicle ~14.7m from the local-NED origin, goto_position_ned_and_hold(0,
0, -alt, yaw, 2.0) drove it straight back toward (north=0, east=0) instead
of holding in place -- matching the ~14.7-14.8m displacement measured in the
two un-instrumented failing runs. goto_global_position_and_wait() itself was
proven correct separately (see test_goto_global_position_and_wait.py) and is
not what these tests cover.
"""
import types

import pytest
from unittest.mock import AsyncMock

from mavsdk_common.mavsdk_backend_base import MavsdkBackendBase


def _backend(north_m=14.7, east_m=-2.0, down_m=-3.0):
    # real mavsdk.System().offboard is a property that raises until
    # System.connect() has run -- these tests never connect, so the fake
    # drone/offboard object is substituted wholesale rather than reaching
    # through the real property.
    backend = MavsdkBackendBase("dummy://connection")
    backend.drone = types.SimpleNamespace(
        offboard=types.SimpleNamespace(set_position_ned=AsyncMock()))
    sample = types.SimpleNamespace(
        position=types.SimpleNamespace(north_m=north_m, east_m=east_m, down_m=down_m))
    backend._position_velocity_ned.update(sample)
    return backend


def _sent_setpoints(backend):
    return [call.args[0] for call in backend.drone.offboard.set_position_ned.call_args_list]


@pytest.mark.asyncio
async def test_and_hold_offsets_from_current_position_not_world_origin():
    """THE regression, reproduced exactly: current position is ~14.7m from
    the local-NED origin (the measured SITL displacement), and the caller
    asks for a (0, 0) lateral move -- i.e. 'stay here'. The old absolute
    behaviour would send the vehicle to (0, 0)."""
    backend = _backend(north_m=14.7, east_m=-2.0, down_m=-3.0)

    await backend.goto_position_ned_and_hold(0.0, 0.0, -3.0, 90.0, duration_s=0.05)

    setpoints = _sent_setpoints(backend)
    assert setpoints, "no setpoint was sent"
    assert all(sp.north_m == pytest.approx(14.7) for sp in setpoints)
    assert all(sp.east_m == pytest.approx(-2.0) for sp in setpoints)


@pytest.mark.asyncio
async def test_and_hold_applies_a_genuine_relative_lateral_offset():
    """Gorev3PickupPhase's 'advance 0.6m' step: current position (10.0, 5.0)
    plus a (+0.6, -0.3) request must land at (10.6, 4.7), not at (0.6,
    -0.3)."""
    backend = _backend(north_m=10.0, east_m=5.0, down_m=-0.30)

    await backend.goto_position_ned_and_hold(0.6, -0.3, -0.30, 45.0, duration_s=0.05)

    setpoints = _sent_setpoints(backend)
    assert all(sp.north_m == pytest.approx(10.6) for sp in setpoints)
    assert all(sp.east_m == pytest.approx(4.7) for sp in setpoints)


@pytest.mark.asyncio
async def test_and_hold_keeps_down_and_yaw_absolute():
    """down_m/yaw_deg are real absolute targets in every caller (an actual
    altitude, an actual heading) -- only the lateral axes are relative."""
    backend = _backend(north_m=14.7, east_m=-2.0, down_m=-3.0)

    await backend.goto_position_ned_and_hold(0.0, 0.0, -1.23, 77.0, duration_s=0.05)

    setpoints = _sent_setpoints(backend)
    assert all(sp.down_m == pytest.approx(-1.23) for sp in setpoints)
    assert all(sp.yaw_deg == pytest.approx(77.0) for sp in setpoints)


@pytest.mark.asyncio
async def test_and_hold_streams_the_same_fixed_setpoint_repeatedly():
    """Still must stream (GAP FIX, 2026-08-13): a single setpoint gap
    >~500ms drops PX4 out of Offboard. The fix must not turn this back into
    a one-shot call, and must not re-sample position mid-hold (that would
    make the target chase the vehicle instead of holding it)."""
    backend = _backend(north_m=14.7, east_m=-2.0, down_m=-3.0)

    await backend.goto_position_ned_and_hold(0.0, 0.0, -3.0, 0.0, duration_s=0.35)

    setpoints = _sent_setpoints(backend)
    assert len(setpoints) >= 2
    assert len({(sp.north_m, sp.east_m) for sp in setpoints}) == 1


@pytest.mark.asyncio
async def test_and_hold_raises_on_stale_position_instead_of_silently_using_it():
    """No fresh position sample yet -- must not fabricate an offset base
    (which would silently reproduce the exact absolute-vs-relative bug this
    fix closes) or send anything at all; it must surface the same
    TelemetryStale contract every other cached getter uses."""
    from core.interfaces.i_flight_backend import TelemetryStale

    backend = MavsdkBackendBase("dummy://connection")
    backend.drone = types.SimpleNamespace(
        offboard=types.SimpleNamespace(set_position_ned=AsyncMock()))

    with pytest.raises(TelemetryStale):
        await backend.goto_position_ned_and_hold(0.0, 0.0, -3.0, 0.0, duration_s=0.05)
    backend.drone.offboard.set_position_ned.assert_not_called()
