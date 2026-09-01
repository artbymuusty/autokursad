import pytest

from mocks.mock_flight_backend import MockFlightBackend

from core.mission.gorev3_transport import Gorev3TransportPhase
from core.position_log.position_store import PositionStore
from core.config.parameters import GOREV3_TRANSIT_ALTITUDE_M, GOREV3_TRANSIT_SPEED_M_S
from payload import PayloadState


class _CarryingPayloadManager:
    """PHASE 11: tasima fazi artik payload durumunu dogruluyor. Varsayilan:
    yuk alinmis (TRANSPORTING) ve hala guvencede."""

    def __init__(self, state=PayloadState.TRANSPORTING, still_secured=True, raises=None):
        self._state = state
        self._still_secured = still_secured
        self._raises = raises

    def get_state(self):
        return self._state

    def is_still_secured(self) -> bool:
        if self._raises is not None:
            raise self._raises
        return self._still_secured


class _RecordingCentering:
    def __init__(self, converges: bool = True):
        self.calls = []
        self._converges = converges

    async def goto_global_position_and_wait(self, lat, lon, alt) -> bool:
        self.calls.append((lat, lon, alt))
        return self._converges


@pytest.mark.asyncio
async def test_transport_raises_without_recorded_kirmizi_ucgen(tmp_path):
    flight = MockFlightBackend()
    store = PositionStore(str(tmp_path / "positions.json"))
    centering = _RecordingCentering()
    phase = Gorev3TransportPhase(flight, store, centering, _CarryingPayloadManager())

    with pytest.raises(RuntimeError):
        await phase.run()


@pytest.mark.asyncio
async def test_transport_navigates_to_recorded_kirmizi_ucgen_position(tmp_path):
    """BUG FIX (continuous audit, 2026-08-13): this phase used to hold
    north=0/east=0 -- never actually navigating to the recorded position at
    all. Now it must actually go there."""
    flight = MockFlightBackend()
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("KIRMIZI_UCGEN", 0.9, True, True, (41.5, 29.5, 15.0), "ilk")
    centering = _RecordingCentering()

    phase = Gorev3TransportPhase(flight, store, centering, _CarryingPayloadManager())
    await phase.run()

    assert centering.calls == [(41.5, 29.5, GOREV3_TRANSIT_ALTITUDE_M)]


@pytest.mark.asyncio
async def test_transport_still_completes_when_navigation_times_out(tmp_path):
    flight = MockFlightBackend()
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("KIRMIZI_UCGEN", 0.9, True, True, (41.5, 29.5, 15.0), "ilk")
    centering = _RecordingCentering(converges=False)

    phase = Gorev3TransportPhase(flight, store, centering, _CarryingPayloadManager())
    assert await phase.run() is True  # must not raise

    assert len(centering.calls) == 1


def test_transit_speed_is_explicitly_configured_not_none():
    # Operator revision (2026-08-13): "2 m/s seyir hızı" -- explicitly
    # authorized, must not silently regress back to an unfilled TODO.
    assert GOREV3_TRANSIT_SPEED_M_S == 2.0


# ---------------------------------------------------------------------------
# PHASE 11: Transport Verification
# ---------------------------------------------------------------------------

def _store_with_target(tmp_path):
    store = PositionStore(str(tmp_path / "positions.json"))
    store.try_save("KIRMIZI_UCGEN", 0.9, True, True, (41.5, 29.5, 15.0), "ilk")
    return store


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [
    PayloadState.IDLE, PayloadState.CAPTURED, PayloadState.GRAPPLED,
    PayloadState.DEPLOY_TIMEOUT, PayloadState.PAYLOAD_NOT_SECURED,
])
async def test_transport_refuses_when_payload_was_never_secured(tmp_path, state):
    """PHASE 11: eskiden bu faz payload durumuna HIC bakmiyordu -- alma
    basarisiz olsa bile bos kancayla hedefe ucardi. Artik onkosul var."""
    centering = _RecordingCentering()
    phase = Gorev3TransportPhase(MockFlightBackend(), _store_with_target(tmp_path),
                                 centering, _CarryingPayloadManager(state=state))

    assert await phase.run() is False
    assert centering.calls == [], "yuk alinmamisken transit'e cikildi"


@pytest.mark.asyncio
async def test_transport_fails_when_payload_lost_in_transit(tmp_path):
    """Asil PHASE 11 katkisi: get_state() HAFIZADIR, payload ucus sirasinda
    dusse bile TRANSPORTING der. is_still_secured() backend'e sorar ve
    kaybi yakalar -- bos kancayla birakma adimina gecilmez."""
    centering = _RecordingCentering()
    phase = Gorev3TransportPhase(
        MockFlightBackend(), _store_with_target(tmp_path), centering,
        _CarryingPayloadManager(still_secured=False))

    assert await phase.run() is False
    assert len(centering.calls) == 1, "transit yine de denenmis olmali"


@pytest.mark.asyncio
async def test_transport_state_alone_is_not_enough(tmp_path):
    """Iki kontrolun AYRI oldugunun kaniti: state TRANSPORTING olsa bile
    fiziksel dogrulama gecmezse faz duser."""
    manager = _CarryingPayloadManager(state=PayloadState.TRANSPORTING,
                                      still_secured=False)
    phase = Gorev3TransportPhase(MockFlightBackend(), _store_with_target(tmp_path),
                                 _RecordingCentering(), manager)

    assert manager.get_state() is PayloadState.TRANSPORTING
    assert await phase.run() is False


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [NotImplementedError("sensor yok"), RuntimeError("kalibrasyon")])
async def test_transport_converts_query_gap_to_clean_failure(tmp_path, exc):
    """Real yolun sorgu boslugu (is_secured -> NotImplementedError) TEMIZ
    bir faz basarisizligina donusur, disari sizmaz."""
    from payload.errors import PayloadCalibrationError
    raised = PayloadCalibrationError("FLEX TBD") if isinstance(exc, RuntimeError) and not isinstance(exc, NotImplementedError) else exc
    phase = Gorev3TransportPhase(
        MockFlightBackend(), _store_with_target(tmp_path), _RecordingCentering(),
        _CarryingPayloadManager(raises=raised))

    assert await phase.run() is False


@pytest.mark.asyncio
async def test_transport_succeeds_when_payload_still_secured(tmp_path):
    """Mutlu yol: onkosul gecti, transit yapildi, yuk hala guvencede."""
    phase = Gorev3TransportPhase(MockFlightBackend(), _store_with_target(tmp_path),
                                 _RecordingCentering(), _CarryingPayloadManager())

    assert await phase.run() is True
