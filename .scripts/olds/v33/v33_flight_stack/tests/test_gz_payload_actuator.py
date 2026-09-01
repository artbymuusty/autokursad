"""Gazebo payload actuator: detach topics, and CONFIRMED release (F2).

Rewritten for ADR-011 (release detaches a world-loaded body instead of
spawning one) and F2 (a release is not believed until the body is seen to
leave the vehicle). The failure these pin down is concrete: on the first
ADR-011 flight the servo fired, the log said RELEASED, and the payload was
still bolted on -- it let go seconds later during the climb-out and landed
4.9 m past the target.
"""
import asyncio

import pytest
from unittest.mock import AsyncMock, patch

from gz_system.gz_payload_actuator import (
    GzPayloadActuator,
    HOOK_ATTACH_TOPIC,
    HOOK_STATE_TOPIC,
    PAYLOAD_DETACH_TOPIC,
    VEHICLE_MODEL_NAME,
)


def _mock_proc(returncode: int, stderr: bytes = b""):
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate.return_value = (b"", stderr)
    return proc


class _FakeMonitor:
    """Scripted pose source. `drop_after` is how many payload reads stay
    attached before the body starts falling; read 1 is the pre-publish
    baseline, so 1 means "separates on the first poll after the servo" and
    None means it never separates at all."""

    def __init__(self, drop_after=1, known=True):
        self.drop_after = drop_after
        self.known = known
        self.reads = 0

    def get(self, name):
        if not self.known:
            return None
        if name == VEHICLE_MODEL_NAME:
            return (0.0, 0.0, 0.65)
        self.reads += 1
        attached_z = 0.47  # 0.18 m below the vehicle
        if self.drop_after is not None and self.reads > self.drop_after:
            return (0.0, 0.0, 0.03)
        return (0.0, 0.0, attached_z)

    def get_quat(self, name):
        return (0.0, 0.0, 0.0, 1.0)


def _actuator(monitor):
    return GzPayloadActuator("dummy_service", pose_monitor=monitor)


@pytest.mark.asyncio
async def test_release_at_mavi_altigen_detaches_the_red_payload():
    """The servo->colour mapping is a deliberate team assignment (RED
    payload on the MAVI hexagon) and must not drift."""
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec", return_value=_mock_proc(0)) as exec_mock:
        assert await actuator.release_payload_at_mavi_altigen() is True
    topics = [c.args for c in exec_mock.call_args_list]
    assert all(PAYLOAD_DETACH_TOPIC % "red" in args for args in topics)
    assert all("gz.msgs.Empty" in args for args in topics)


@pytest.mark.asyncio
async def test_release_at_kirmizi_ucgen_detaches_the_blue_payload():
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec", return_value=_mock_proc(0)) as exec_mock:
        assert await actuator.release_payload_at_kirmizi_ucgen() is True
    assert all(PAYLOAD_DETACH_TOPIC % "blue" in c.args for c in exec_mock.call_args_list)


@pytest.mark.asyncio
async def test_detach_is_published_more_than_once():
    """gz-transport is a slow joiner: a one-shot publisher can advertise and
    send before the plugin has finished subscribing, and the message is
    simply lost. A single publish is what made the first flight's detach
    arrive seconds late."""
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec", return_value=_mock_proc(0)) as exec_mock:
        await actuator.release_payload_at_mavi_altigen()
    assert exec_mock.call_count > 1


@pytest.mark.asyncio
async def test_release_reports_failure_when_the_payload_never_separates():
    """THE regression. The payload is visible and demonstrably still hanging
    off the vehicle, so the release must come back False -- the caller uses
    that to hold position instead of climbing away."""
    actuator = _actuator(_FakeMonitor(drop_after=None))
    with patch("asyncio.create_subprocess_exec", return_value=_mock_proc(0)):
        assert await actuator.release_payload_at_mavi_altigen() is False
    assert actuator.detach_latency("MAVI_ALTIGEN") is None


@pytest.mark.asyncio
async def test_confirmed_release_records_its_latency():
    actuator = _actuator(_FakeMonitor(drop_after=1))
    with patch("asyncio.create_subprocess_exec", return_value=_mock_proc(0)):
        assert await actuator.release_payload_at_kirmizi_ucgen() is True
    latency = actuator.detach_latency("KIRMIZI_UCGEN")
    assert latency is not None and latency >= 0.0


@pytest.mark.asyncio
async def test_missing_pose_data_is_unknown_not_failure():
    """A dead observer must not ground a flight. With no pose at all we
    cannot distinguish attached from separated, so we claim neither and let
    the mission proceed -- loudly unconfirmed, not falsely failed."""
    actuator = _actuator(_FakeMonitor(known=False))
    with patch("asyncio.create_subprocess_exec", return_value=_mock_proc(0)):
        assert await actuator.release_payload_at_mavi_altigen() is True
    assert actuator.detach_latency("MAVI_ALTIGEN") is None


@pytest.mark.asyncio
async def test_release_returns_false_when_gz_cli_missing():
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
        assert await actuator.release_payload_at_kirmizi_ucgen() is False


@pytest.mark.asyncio
async def test_release_returns_false_when_every_publish_fails():
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec",
               return_value=_mock_proc(1, b"gz: command not found")):
        assert await actuator.release_payload_at_mavi_altigen() is False


def test_landing_reference_carries_the_target_centre_and_rest_height():
    """F3: without a reference, "settled" could only ever mean "not below
    ground" -- which is how a 4.9 m miss passed."""
    actuator = _actuator(_FakeMonitor())
    assert actuator.landing_reference("MAVI_ALTIGEN")[:2] == (0.0, 15.0)
    assert actuator.landing_reference("KIRMIZI_UCGEN")[:2] == (0.0, 40.0)
    assert actuator.landing_reference("KIRMIZI_DIKDORTGEN") is None


def test_tilt_is_reported_so_edge_landings_are_visible():
    actuator = _actuator(_FakeMonitor())
    assert actuator.get_released_payload_tilt_deg("MAVI_ALTIGEN") == 0.0


# --- F3 attach-confirmation false-positive fix (2026-08-21) --------------
#
# Root cause, measured live in SITL: the OLD _await_attach() judged success
# by vehicle_z - payload_z alone. Gorev3PickupPhase already descends to
# ~0.3m before calling activate_pickup_mechanism(), so that delta sits
# inside V3_HOOK_ATTACH_CONFIRM_Z_TOLERANCE_M (1.0m) whether or not a real
# HookAttachSystem joint ever formed -- measured vehicle_z=0.854,
# payload_z=0.031, delta=0.823. The mission logged "Yük Alma Başarılı" and
# completed Görev 3 end to end while payload_red never moved. The fix reads
# HOOK_STATE_TOPIC (HookAttachSystem's own ground truth) via a scoped
# HookStateMonitor instead of trusting position.
#
# These fakes stand in for the two DIFFERENT subprocess shapes
# GzPayloadActuator now spawns: short-lived `gz topic -t ... -p ...`
# publishes (.communicate()) and the long-lived `gz topic -e -t
# HOOK_STATE_TOPIC` subscription HookStateMonitor reads line-by-line.

class _FakeStdout:
    """Feeds HookStateMonitor's readline() loop. An empty `lines` list means
    the topic never reports anything within the test's timeout -- exactly
    the real timeout scenario, without waiting out a real 15s clock."""

    def __init__(self, lines):
        self._lines = list(lines)

    async def readline(self):
        if self._lines:
            return self._lines.pop(0)
        await asyncio.sleep(3600)  # HookStateMonitor.stop() cancels this
        return b""


class _FakeStateProc:
    def __init__(self, lines):
        self.stdout = _FakeStdout(lines)

    def terminate(self):
        pass

    async def wait(self):
        return 0


def _exec_side_effect(state_lines):
    """Routes `gz topic -e -t HOOK_STATE_TOPIC` to the scripted state
    stream; every other `gz topic ...` publish (attach/detach/color-drop)
    gets the normal short-lived success mock."""
    async def _fake_exec(*args, **kwargs):
        if "-e" in args and HOOK_STATE_TOPIC in args:
            return _FakeStateProc(state_lines)
        return _mock_proc(0)
    return _fake_exec


@pytest.mark.asyncio
async def test_activate_pickup_mechanism_succeeds_when_hook_state_confirms():
    """SUCCESS case: HOOK_STATE_TOPIC genuinely reports attached."""
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec",
               side_effect=_exec_side_effect([b"data: true\n"])):
        assert await actuator.activate_pickup_mechanism() is True


@pytest.mark.asyncio
async def test_await_attach_fails_when_position_is_close_but_state_never_confirms():
    """THE regression, reproduced exactly: position already looks "attached"
    (the same close range Gorev3PickupPhase's 0.30m approach produces) but
    HOOK_STATE_TOPIC never reports true. Must return False, not be fooled by
    proximity alone."""
    close_monitor = _FakeMonitor(drop_after=None)  # payload stays at attached_z=0.47 forever
    actuator = _actuator(close_monitor)
    with patch("asyncio.create_subprocess_exec", side_effect=_exec_side_effect([])):
        result = await actuator._await_attach("red", timeout_s=0.3)
    assert result is False


@pytest.mark.asyncio
async def test_await_attach_succeeds_on_genuine_state_confirmation():
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec",
               side_effect=_exec_side_effect([b"data: true\n"])):
        assert await actuator._await_attach("red", timeout_s=5.0) is True


@pytest.mark.asyncio
async def test_await_attach_times_out_when_hook_state_stays_silent():
    """No message at all on HOOK_STATE_TOPIC within the window -> False,
    not a hang and not a false success."""
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec", side_effect=_exec_side_effect([])):
        assert await actuator._await_attach("red", timeout_s=0.3) is False


@pytest.mark.asyncio
async def test_await_attach_returns_false_when_monitor_cannot_start():
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
        assert await actuator._await_attach("red", timeout_s=0.3) is False


@pytest.mark.asyncio
async def test_activate_pickup_mechanism_publishes_the_correct_child_model():
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec",
               side_effect=_exec_side_effect([b"data: true\n"])) as exec_mock:
        await actuator.activate_pickup_mechanism()
    attach_calls = [c.args for c in exec_mock.call_args_list if HOOK_ATTACH_TOPIC in c.args]
    assert attach_calls, "no /hook/attach publish was made"
    assert any('data: "payload_red"' in args for args in attach_calls)


@pytest.mark.asyncio
async def test_activate_drop_mechanism_still_works_unchanged():
    """Not in scope for this fix -- activate_drop_mechanism's existing
    _at_rest_height best-effort confirmation is untouched."""
    actuator = _actuator(_FakeMonitor())
    with patch("asyncio.create_subprocess_exec", return_value=_mock_proc(0)):
        assert await actuator.activate_drop_mechanism() is True
