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
from core.mission.mission_v3_state import MissionV3State
from core.position_log.position_store import PositionStore


class _RecordingCentering:
    def __init__(self, converges: bool = True):
        self.calls = []
        self._converges = converges

    async def goto_global_position_and_wait(self, lat, lon, alt) -> bool:
        self.calls.append(('goto_global_position_and_wait', lat, lon, alt))
        return self._converges


class _RecordingReleaseService:
    def __init__(self):
        self.calls = []

    async def release_and_verify(self, shape_type: str) -> bool:
        self.calls.append(shape_type)
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
async def test_mission_v3_state_opt_in_marks_hexagon_done_not_double_fired(tmp_path):
    """F2: mission_v3_state verildiğinde interlock YİNE aynı şekilde True
    olur (tek yoldan, iki kez değil) VE completed_count/mission_order da
    güncellenir -- eski (mission_v3_state=None) davranış hiç bozulmaz."""
    store = PositionStore(str(tmp_path / "positions.json"))
    _record_both(store, "MAVI_ALTIGEN", "KIRMIZI_UCGEN")
    interlock = PayloadInterlock()
    v3_state = MissionV3State(interlock)
    centering = _RecordingCentering()
    release_service = _RecordingReleaseService()
    sequencer = PayloadMissionSequencer(flight=None, centering=centering, interlock=interlock,
                                         position_store=store, release_service=release_service,
                                         mission_v3_state=v3_state)

    await sequencer.execute_payload_mission_1()

    assert interlock.payload_1_released is True
    assert v3_state.completed_count == 1
    assert v3_state.hexagon_done is True
    assert "1st_mission" in v3_state.mission_order


@pytest.mark.asyncio
async def test_mission_v3_state_order_labels_correct_regardless_of_discovery_order(tmp_path):
    """Kırmızı Üçgen İLK keşfedilse bile (position_store kayıt sırası ters),
    payload sırası ve dolayısıyla 1st_mission/2nd_mission etiketleri hep
    Mavi Altıgen->Kırmızı Üçgen olur -- F0/F1'de karara bağlanan, gerçek
    yarışma kuralına dayanan deterministik sonuç."""
    store = PositionStore(str(tmp_path / "positions.json"))
    _record_both(store, first="KIRMIZI_UCGEN", second="MAVI_ALTIGEN")
    interlock = PayloadInterlock()
    v3_state = MissionV3State(interlock)
    centering = _RecordingCentering()
    release_service = _RecordingReleaseService()
    sequencer = PayloadMissionSequencer(flight=None, centering=centering, interlock=interlock,
                                         position_store=store, release_service=release_service,
                                         mission_v3_state=v3_state)

    await sequencer.execute_all()

    assert v3_state.completed_count == 2
    assert v3_state.mission_order["1st_mission"].shape == "MAVI_ALTIGEN"
    assert v3_state.mission_order["2nd_mission"].shape == "KIRMIZI_UCGEN"
    assert v3_state.rectangle_scan_enabled is True


@pytest.mark.asyncio
async def test_execute_payload_mission_2_no_longer_requires_payload_1_first(tmp_path):
    """YENIDEN YAZILDI (2026-08-24): eskiden bu test payload_2'nin
    payload_1'den once birakilamayacagini (RuntimeError) dogruluyordu.
    Sira kurali kaldirildi -- artik ucgen once islenebilir ve bu beklenen
    davranistir."""
    store = PositionStore(str(tmp_path / "positions.json"))
    _record_both(store, "MAVI_ALTIGEN", "KIRMIZI_UCGEN")
    interlock = PayloadInterlock()
    release_service = _RecordingReleaseService()
    sequencer = PayloadMissionSequencer(flight=None, centering=_RecordingCentering(),
                                         interlock=interlock, position_store=store,
                                         release_service=release_service)

    await sequencer.execute_payload_mission_2()          # artik firlatmiyor

    assert interlock.payload_2_released is True
    assert interlock.payload_1_released is False
    assert release_service.calls == ["KIRMIZI_UCGEN"]


@pytest.mark.asyncio
@pytest.mark.parametrize("order", [
    ["KIRMIZI_UCGEN", "MAVI_ALTIGEN"],
    ["MAVI_ALTIGEN", "KIRMIZI_UCGEN"],
])
async def test_execute_payload_mission_for_runs_either_order(tmp_path, order):
    """Yeni arayuz: sira CAGIRAN tarafindan belirlenir, sequencer sabit
    bir sira DAYATMAZ."""
    store = PositionStore(str(tmp_path / "positions.json"))
    _record_both(store, "MAVI_ALTIGEN", "KIRMIZI_UCGEN")
    interlock = PayloadInterlock()
    release_service = _RecordingReleaseService()
    sequencer = PayloadMissionSequencer(flight=None, centering=_RecordingCentering(),
                                         interlock=interlock, position_store=store,
                                         release_service=release_service)

    for shape in order:
        await sequencer.execute_payload_mission_for(shape)

    assert release_service.calls == order
    assert interlock.both_released() is True


@pytest.mark.asyncio
async def test_navigate_false_skips_the_return_flight(tmp_path):
    """Dinamik akista arac zaten hedefin ustunde kilitli -- kayitli GPS'e
    yeniden gitmeye gerek yok, geri-ucus atlanir."""
    store = PositionStore(str(tmp_path / "positions.json"))
    _record_both(store, "MAVI_ALTIGEN", "KIRMIZI_UCGEN")
    centering = _RecordingCentering()
    release_service = _RecordingReleaseService()
    sequencer = PayloadMissionSequencer(flight=None, centering=centering,
                                         interlock=PayloadInterlock(), position_store=store,
                                         release_service=release_service)

    await sequencer.execute_payload_mission_for("MAVI_ALTIGEN", navigate=False)

    assert centering.calls == [], "navigate=False iken geri-ucus yapildi"
    assert release_service.calls == ["MAVI_ALTIGEN"]



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
async def test_execute_all_is_now_a_compensation_path(tmp_path):
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
