"""Direct coverage for goto_global_position_and_wait(), added during the
Görev 3 Faz 1 navigation root-cause investigation (2026-08-21).

Live SITL (3 fully-instrumented runs, 7 direct navigation calls) proved this
function itself converges correctly to within 0.2-0.3m of the true GPS
target every time -- the actual bug (an absolute-vs-relative mismatch in
goto_position_ned_and_hold(), see test_mavsdk_backend_base.py) lives one
level below it, in code this function does not call. These tests pin down
the behaviour that SITL run already demonstrated, as permanent regression
coverage: a stale, distant, or frozen "current position" must never be
accepted as arrival, and a genuine arrival must be.
"""
import pytest

from mocks.mock_flight_backend import MockFlightBackend
from core.interfaces.i_flight_backend import TelemetryStale
from core.navigation.centering_controller import CenteringController
from core.navigation.geo import gps_to_ned_delta, haversine_distance_m

TARGET_LAT, TARGET_LON, TARGET_ALT_M = 41.0010, 29.0010, 15.0
# ~1.4m north-east of the target -- inside GPS_POSITION_CONVERGENCE_TOLERANCE_M.
ARRIVED_LAT, ARRIVED_LON = 41.001009, 29.001009
# ~500m away -- unambiguously "not arrived" under any tolerance.
FAR_LAT, FAR_LON = 41.0055, 29.0055


class _GlobalNavFlight(MockFlightBackend):
    """goto_global_position_and_wait()'s convergence loop only reads
    get_global_position()/get_velocity_ned() (goto_position_ned() itself is
    a one-way command in real MAVSDK, not a feedback path) -- so this scripts
    those two directly instead of trying to simulate physics through
    MockFlightBackend's velocity integrator, which goto_position_ned() never
    drives."""

    def __init__(self, positions, velocities=None, stale_after=None):
        super().__init__()
        self._traj = list(positions)
        self._vel_traj = list(velocities) if velocities is not None else None
        self._stale_after = stale_after
        self._global_calls = 0

    async def get_global_position(self):
        self._global_calls += 1
        if self._stale_after is not None and self._global_calls > self._stale_after:
            raise TelemetryStale("position: simulated stale telemetry")
        idx = min(self._global_calls - 1, len(self._traj) - 1)
        self._global_pos = self._traj[idx]
        return self._global_pos

    async def get_velocity_ned(self):
        if self._vel_traj is None:
            return self._velocity_ned
        idx = min(self._global_calls - 1, len(self._vel_traj) - 1)
        return self._vel_traj[idx]


def _controller(flight):
    return CenteringController(flight, detection_feed=None, camera=None)


@pytest.mark.asyncio
async def test_stale_current_position_is_not_accepted_as_arrived():
    """A dead telemetry link must abort, never be read as a converged
    arrival just because the loop stopped iterating."""
    flight = _GlobalNavFlight([(ARRIVED_LAT, ARRIVED_LON, TARGET_ALT_M)], stale_after=0)
    controller = _controller(flight)

    result = await controller.goto_global_position_and_wait(
        TARGET_LAT, TARGET_LON, TARGET_ALT_M, timeout_s=2.0)

    assert result is False


@pytest.mark.asyncio
async def test_physically_far_position_does_not_return_success():
    """Sitting ~500m from the target for the whole budget must not
    converge, regardless of how long the loop runs."""
    flight = _GlobalNavFlight([(FAR_LAT, FAR_LON, TARGET_ALT_M)])
    controller = _controller(flight)

    result = await controller.goto_global_position_and_wait(
        TARGET_LAT, TARGET_LON, TARGET_ALT_M, timeout_s=0.3)

    assert result is False


@pytest.mark.asyncio
async def test_genuine_arrival_returns_success():
    """A position that is truly inside tolerance, with velocity also below
    the tolerance, must converge -- and the distance at that exact moment
    must genuinely be inside GPS_POSITION_CONVERGENCE_TOLERANCE_M (2.0m)."""
    flight = _GlobalNavFlight(
        [(ARRIVED_LAT, ARRIVED_LON, TARGET_ALT_M)],
        velocities=[(0.0, 0.0, 0.0)],
    )
    controller = _controller(flight)

    result = await controller.goto_global_position_and_wait(
        TARGET_LAT, TARGET_LON, TARGET_ALT_M, timeout_s=2.0)

    assert result is True
    true_distance_m = haversine_distance_m(ARRIVED_LAT, ARRIVED_LON, TARGET_LAT, TARGET_LON)
    assert true_distance_m < 2.0


@pytest.mark.asyncio
async def test_frozen_position_with_no_updates_times_out():
    """A feed that keeps reporting samples (so it never counts as stale)
    but at a value that never moves and never was close must fail on
    timeout, not hang or falsely succeed."""
    flight = _GlobalNavFlight([(FAR_LAT, FAR_LON, TARGET_ALT_M)])
    controller = _controller(flight)

    result = await controller.goto_global_position_and_wait(
        TARGET_LAT, TARGET_LON, TARGET_ALT_M, timeout_s=0.25)

    assert result is False
    assert flight._global_calls > 1  # actually polled repeatedly, did not just abort once


def test_gps_and_local_coordinate_math_agree_on_true_distance():
    """The function fixes its NED target by adding gps_to_ned_delta() to a
    single local-NED snapshot, then measures convergence with
    haversine_distance_m() on the raw lat/lon -- two different coordinate
    systems computed from the same two points. If they disagreed, a
    'converged' local-NED setpoint could sit at a genuinely different GPS
    distance than the convergence check believes. For displacements this
    small (~1.4m) the flat-earth delta's implied distance and the
    haversine distance must match to within a few centimetres."""
    delta_n, delta_e = gps_to_ned_delta(TARGET_LAT, TARGET_LON, ARRIVED_LAT, ARRIVED_LON)
    flat_distance_m = (delta_n ** 2 + delta_e ** 2) ** 0.5
    true_distance_m = haversine_distance_m(TARGET_LAT, TARGET_LON, ARRIVED_LAT, ARRIVED_LON)

    assert abs(flat_distance_m - true_distance_m) < 0.05
