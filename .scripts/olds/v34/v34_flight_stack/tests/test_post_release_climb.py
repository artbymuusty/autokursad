"""
Post-release climb-back altitude (2026-08-26).

release_and_verify() used to hard-code its climb-back to MISSION_ALTITUDE_M
(15.0 m). That is correct after payload 1 -- the route resume and the search
for the SECOND target both run at MISSION_ALTITUDE_M, so the climb is
consumed. After payload 2 nothing consumes it: Görev 2 ends, master_fsm hands
straight to Görev 3, and Görev 3's very first command is
GOREV3_TRANSIT_ALTITUDE_M = 1.5 m, issued ~0.11 s after the climb finishes.

Measured across three real missions: payload-2 release at 0.435 / 0.473 /
0.477 m, climb to a peak of 14.69 / 14.71 / 14.75 m taking 8.9 / 9.0 / 9.1 s,
then an immediate descent to 1.5 m -- ~13.2 m up and ~13.2 m down, ~9 s,
entirely wasted.

These tests pin the asymmetry (first release unchanged, terminal release
lowered) and the clearance budget that makes the lower altitude safe.
"""
import pytest

from mocks.mock_payload_actuator import MockPayloadActuator
from mocks.mock_camera_source import MockCameraSource

from core.detection.detection_feed import DetectionFeed
from core.mission.payload_release import PayloadReleaseService
from core.mission.gorev2_fsm import PayloadMissionSequencer
from core.mission.interlock import PayloadInterlock
from core.position_log.position_store import PositionStore
from core.config.parameters import (
    MISSION_ALTITUDE_M, GOREV3_TRANSIT_ALTITUDE_M,
    GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M, PAYLOAD_APPROACH_ALTITUDES_M,
)

# --- Measured geometry the 1.5 m clearance budget is derived from ---------
# The winch is RETRACTED throughout Görev 2 -- set_winch(EXTEND) is only
# called in Görev 3's activate_pickup_mechanism -- so 0.198 m is the real
# case and 0.198 + 0.35 is the "winch stuck fully out" worst case.
HOOK_TIP_BELOW_BASE_LINK_RETRACTED_M = 0.198
WINCH_FULL_EXTENSION_M = 0.35
DROPPED_PAYLOAD_DECK_TOP_M = 0.070
MIN_REQUIRED_CLEARANCE_M = 0.5


class _RecordingCentering:
    """Records the exact sequence/arguments of centering calls
    PayloadReleaseService makes, without re-exercising CenteringController's
    own convergence physics (already covered by test_centering_controller.py).

    Same shape as the double in test_payload_release.py; duplicated rather
    than shared so neither file constrains the other."""
    def __init__(self):
        self.calls: list = []

    async def go_to_and_center(self, shape_type: str, altitude_m: float,
                               alt_tolerance_m: float = None, aim_offset_body_m=None) -> bool:
        self.calls.append(('go_to_and_center', shape_type, altitude_m))
        return True

    async def descend_to_release(self, shape_type: str, altitude_m: float, mount_body_m):
        self.calls.append(('descend_to_release', shape_type, altitude_m))
        return altitude_m

    async def nudge_forward(self, distance_m: float) -> None:
        self.calls.append(('nudge_forward', distance_m))

    async def climb_to_altitude(self, altitude_m: float) -> bool:
        self.calls.append(('climb_to_altitude', altitude_m))
        return True

    async def goto_waypoint(self, lat, lon, alt) -> bool:
        """PayloadMissionSequencer'in KULLANDIGI metot (2026-09-02'den beri):
        _navigate_to_recorded artik Climb-then-Cruise yolundan geciyor.
        Ikisinin sozlesmesi ayni oldugu icin double her ikisini de tanir --
        goto_global_position_and_wait hala Gorev 3 ve donus bacaginda."""
        self.calls.append(('goto_waypoint', lat, lon, alt))
        return True

    async def goto_global_position_and_wait(self, lat, lon, alt) -> bool:
        self.calls.append(('goto_global_position_and_wait', lat, lon, alt))
        return True


class _RecordingReleaseService:
    """Captures what PayloadMissionSequencer asks for per payload -- the
    point of these tests is WHICH climb-back altitude each path requests."""
    def __init__(self):
        self.calls: list = []

    async def release_and_verify(self, shape_type: str, *,
                                 climb_back_alt_m: float = MISSION_ALTITUDE_M) -> bool:
        self.calls.append((shape_type, climb_back_alt_m))
        return True


def _feed() -> DetectionFeed:
    """Empty feed = "verification marker never seen" (best-effort, does not
    gate flow). stale_after_s is widened because this feed is published once,
    whereas the real one is republished every frame by the orchestrator's
    detection loop and never goes stale mid-release."""
    feed = DetectionFeed(stale_after_s=3600.0)
    feed.publish([])
    return feed


def _sequencer(tmp_path, release_service, centering):
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("MAVI_ALTIGEN", 0.9, True, True, (41.0, 29.0, 15.0), "ilk")
    store.try_save("KIRMIZI_UCGEN", 0.9, True, True, (41.1, 29.1, 15.0), "ikinci")
    return PayloadMissionSequencer(
        flight=None, centering=centering, interlock=PayloadInterlock(),
        position_store=store, release_service=release_service)


# --- The asymmetry: first release unchanged, terminal release lowered -----

@pytest.mark.asyncio
async def test_first_release_still_climbs_back_to_mission_altitude(tmp_path):
    """Payload 1's climb is genuinely consumed: the route resume and the
    search for the second target both run at MISSION_ALTITUDE_M. It must NOT
    be lowered."""
    release_service = _RecordingReleaseService()
    sequencer = _sequencer(tmp_path, release_service, _RecordingCentering())

    await sequencer.execute_payload_mission_1()

    assert release_service.calls == [("MAVI_ALTIGEN", MISSION_ALTITUDE_M)]


@pytest.mark.asyncio
async def test_final_release_climbs_back_to_the_lower_constant(tmp_path):
    """Payload 2 is TERMINAL for Görev 2 -- nothing downstream consumes a
    15 m climb, so it must ask for GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M."""
    release_service = _RecordingReleaseService()
    sequencer = _sequencer(tmp_path, release_service, _RecordingCentering())

    await sequencer.execute_all()

    assert release_service.calls == [
        ("MAVI_ALTIGEN", MISSION_ALTITUDE_M),
        ("KIRMIZI_UCGEN", GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M),
    ]
    assert GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M < MISSION_ALTITUDE_M


@pytest.mark.asyncio
async def test_release_service_default_is_still_mission_altitude():
    """The default must stay MISSION_ALTITUDE_M: every caller that does not
    know it is the terminal drop keeps the search-resume behaviour."""
    service = PayloadReleaseService(MockPayloadActuator(), _feed(), MockCameraSource(),
                                    _RecordingCentering(), flight=None)
    centering = service.centering

    await service.release_and_verify("MAVI_ALTIGEN")

    assert centering.calls[-1] == ('climb_to_altitude', MISSION_ALTITUDE_M)


@pytest.mark.asyncio
async def test_release_service_honours_an_explicit_lower_climb_back():
    """The kwarg reaches climb_to_altitude verbatim, and changes NOTHING
    else about the drop: the staged approach and the servo are untouched."""
    actuator = MockPayloadActuator()
    centering = _RecordingCentering()
    service = PayloadReleaseService(actuator, _feed(), MockCameraSource(),
                                    centering, flight=None)

    await service.release_and_verify(
        "KIRMIZI_UCGEN", climb_back_alt_m=GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M)

    assert centering.calls[-1] == ('climb_to_altitude',
                                   GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M)
    descent_calls = [c for c in centering.calls if c[0] == 'go_to_and_center']
    assert [c[2] for c in descent_calls] == PAYLOAD_APPROACH_ALTITUDES_M
    assert ('release_payload_at_kirmizi_ucgen', {}) in actuator.calls


# --- Why 1.5 m is the right floor ----------------------------------------

def test_new_altitude_is_not_below_what_gorev3_immediately_commands():
    """Görev 3's first command is GOREV3_TRANSIT_ALTITUDE_M. Climbing back
    BELOW it would just turn the wasted climb into a wasted climb in the
    other direction."""
    assert GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M >= GOREV3_TRANSIT_ALTITUDE_M


def test_hook_clears_the_dropped_payload_even_with_the_winch_fully_extended():
    """Clearance budget. The winch is retracted throughout Görev 2, but the
    altitude must survive the winch being stuck fully out."""
    hook_drop_m = HOOK_TIP_BELOW_BASE_LINK_RETRACTED_M + WINCH_FULL_EXTENSION_M
    hook_tip_alt_m = GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M - hook_drop_m
    clearance_m = hook_tip_alt_m - DROPPED_PAYLOAD_DECK_TOP_M

    assert clearance_m >= MIN_REQUIRED_CLEARANCE_M, (
        f"hook tip at {hook_tip_alt_m:.3f} m leaves only {clearance_m:.3f} m "
        f"over the dropped payload deck top ({DROPPED_PAYLOAD_DECK_TOP_M} m)")


def test_the_reduction_recovers_most_of_the_wasted_climb():
    """The whole point is the saving. Against the measured release altitude
    the new constant must remove at least half of the excess climb."""
    release_alt_m = max(0.435, 0.473, 0.477)  # measured, worst (highest) case
    excess_climb_m = MISSION_ALTITUDE_M - release_alt_m
    reduction_m = MISSION_ALTITUDE_M - GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M

    assert reduction_m >= 0.5 * excess_climb_m, (
        f"only {reduction_m:.2f} m of the {excess_climb_m:.2f} m excess climb "
        "was recovered")
