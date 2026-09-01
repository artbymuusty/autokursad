"""
Görev 2 Rapor (operatör revizyonu, 2026-08-13, "Mission Lifecycle" yeniden
yapılandırması): PayloadMissionSequencer, eski Gorev2DurumMachine'in
(DURUM-1..4, tespit sırasına göre dallanan) yerini alır. Payload sırası
artık HER ZAMAN sabittir: Payload Mission 1 = Mavi Altıgen (RED), Payload
Mission 2 = Kırmızı Üçgen (BLUE) -- tespit sırası hiçbir etkiye sahip
değildir (spec: "Discovery order does not matter").
"""
import pytest

from core.mission.gorev2_fsm import PayloadMissionSequencer
from core.mission.interlock import PayloadInterlock
from core.position_log.position_store import PositionStore


class _RecordingCentering:
    def __init__(self, converges: bool = True):
        self.calls = []
        self._converges = converges

    async def goto_global_position_and_wait(self, lat, lon, alt) -> bool:
        self.calls.append(('goto_global_position_and_wait', lat, lon, alt))
        return self._converges


class _RecordingReleaseService:
    """Records the shape AND the post-release climb-back altitude.

    The altitude argument was added when the FINAL drop stopped climbing to
    MISSION_ALTITUDE_M: after payload 2 nothing consumes that climb, because
    Görev 3's first command is GOREV3_TRANSIT_ALTITUDE_M. This double kept
    the one-argument signature and so rejected the new keyword outright --
    a stale double, not a production regression.
    """

    def __init__(self):
        self.calls = []
        self.climb_alts = []

    async def release_and_verify(self, shape_type: str,
                                 climb_back_alt_m: float = None) -> bool:
        self.calls.append(shape_type)
        self.climb_alts.append(climb_back_alt_m)
        return True


def _record_both(store: PositionStore, first: str, second: str) -> None:
    """Records both required targets, `first` before `second` -- used to
    prove PayloadMissionSequencer ignores detection order."""
    store.try_save(first, 0.9, True, True, (41.0, 29.0, 15.0), "ilk")
    store.try_save(second, 0.9, True, True, (41.1, 29.1, 15.0), "ikinci")


@pytest.mark.asyncio
async def test_execute_payload_mission_1_navigates_then_releases_and_marks_interlock(tmp_path):
    store = PositionStore(str(tmp_path / "positions.json"))
    _record_both(store, "MAVI_ALTIGEN", "KIRMIZI_UCGEN")
    interlock = PayloadInterlock()
    centering = _RecordingCentering()
    release_service = _RecordingReleaseService()
    sequencer = PayloadMissionSequencer(flight=None, centering=centering, interlock=interlock,
                                         position_store=store, release_service=release_service)

    result = await sequencer.execute_payload_mission_1()

    assert result is True
    assert release_service.calls == ["MAVI_ALTIGEN"]
    assert interlock.payload_1_released is True
    assert store.get("MAVI_ALTIGEN").payload_released is True
    assert len(centering.calls) == 1


@pytest.mark.asyncio
async def test_execute_payload_mission_2_requires_payload_1_first(tmp_path):
    store = PositionStore(str(tmp_path / "positions.json"))
    _record_both(store, "MAVI_ALTIGEN", "KIRMIZI_UCGEN")
    interlock = PayloadInterlock()  # payload 1 never released
    centering = _RecordingCentering()
    release_service = _RecordingReleaseService()
    sequencer = PayloadMissionSequencer(flight=None, centering=centering, interlock=interlock,
                                         position_store=store, release_service=release_service)

    with pytest.raises(RuntimeError, match="INTERLOCK"):
        await sequencer.execute_payload_mission_2()


@pytest.mark.asyncio
async def test_execute_all_raises_if_both_targets_not_recorded(tmp_path):
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("MAVI_ALTIGEN", 0.9, True, True, (41.0, 29.0, 15.0), "ilk")  # only one recorded
    interlock = PayloadInterlock()
    centering = _RecordingCentering()
    release_service = _RecordingReleaseService()
    sequencer = PayloadMissionSequencer(flight=None, centering=centering, interlock=interlock,
                                         position_store=store, release_service=release_service)

    with pytest.raises(RuntimeError):
        await sequencer.execute_all()

    assert release_service.calls == []


@pytest.mark.asyncio
async def test_execute_all_runs_fixed_order_regardless_of_detection_order(tmp_path):
    """Spec requirement: 'Discovery order does not matter' -- even when
    KIRMIZI_UCGEN was detected FIRST and MAVI_ALTIGEN SECOND, Payload
    Mission 1 must still be Mavi Altıgen (RED) and Payload Mission 2 must
    still be Kırmızı Üçgen (BLUE)."""
    store = PositionStore(str(tmp_path / "positions.json"))
    _record_both(store, first="KIRMIZI_UCGEN", second="MAVI_ALTIGEN")
    interlock = PayloadInterlock()
    centering = _RecordingCentering()
    release_service = _RecordingReleaseService()
    sequencer = PayloadMissionSequencer(flight=None, centering=centering, interlock=interlock,
                                         position_store=store, release_service=release_service)

    await sequencer.execute_all()

    assert release_service.calls == ["MAVI_ALTIGEN", "KIRMIZI_UCGEN"]
    # The first drop keeps the search-resume altitude; the FINAL drop must
    # not, because nothing after it flies that high (Görev 3 opens at
    # GOREV3_TRANSIT_ALTITUDE_M). Asserting the pair keeps the two paths from
    # silently converging again.
    from core.config.parameters import (
        MISSION_ALTITUDE_M, GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M,
    )
    first_alt, final_alt = release_service.climb_alts
    assert first_alt in (None, MISSION_ALTITUDE_M), first_alt
    assert final_alt == GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M, final_alt
    assert final_alt < MISSION_ALTITUDE_M
    assert interlock.both_released() is True


@pytest.mark.asyncio
async def test_navigation_timeout_does_not_abort_the_payload_mission(tmp_path):
    """Best-effort: a failed GPS-navigation convergence must not prevent
    the release attempt (matches the rest of this codebase's best-effort
    philosophy for non-critical failures)."""
    store = PositionStore(str(tmp_path / "positions.json"))
    _record_both(store, "MAVI_ALTIGEN", "KIRMIZI_UCGEN")
    interlock = PayloadInterlock()
    centering = _RecordingCentering(converges=False)
    release_service = _RecordingReleaseService()
    sequencer = PayloadMissionSequencer(flight=None, centering=centering, interlock=interlock,
                                         position_store=store, release_service=release_service)

    result = await sequencer.execute_payload_mission_1()

    assert result is True
    assert release_service.calls == ["MAVI_ALTIGEN"]
