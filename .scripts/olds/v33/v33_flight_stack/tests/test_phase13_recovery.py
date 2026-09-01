"""PHASE 13 testleri: retry/reset (kurtarma) tasarimi.

Kanitlananlar:
  1. HER failure state icin bir kurtarma karari VERILMIS (sessizce
     atlanan yok) ve hedefleri tasarim tablosuyla birebir.
  2. RETRACTED (basari terminali) kurtarilamaz.
  3. Kurtarma KAZA ESERI olamaz: _TRANSITIONS grafigi degismedi, failure
     state'ler normal transition_to() ile hala terminal.
  4. Kurtarma butcesi sinirli ve tukendiginde sessizce gecilmiyor.
  5. Kurtarma OTOMATIK DEGIL -- basarisiz bir komut kendiliginden tekrar
     denemiyor (aksi halde Phase 15'in olcecegi guvenilirlik orani
     bozulurdu).
"""
import asyncio

import pytest

from payload import PayloadManager, PayloadState, NoRecoveryPathError
from payload.payload_manager import MAX_RECOVERY_ATTEMPTS
from payload.payload_state import (
    IllegalPayloadTransitionError, PayloadStateMachine, _RECOVERY_TRANSITIONS,
)
from payload.backends.payload_backend import PayloadBackend

_FAILURE_STATES = [s for s in PayloadState if s.is_failure]

# Tasarim tablosunun testteki kopyasi (payload_state.py yorumu ile ayni).
_EXPECTED = {
    PayloadState.DEPLOY_TIMEOUT: PayloadState.IDLE,
    PayloadState.CAPTURE_TIMEOUT: PayloadState.DEPLOYED,
    PayloadState.GRAPPLE_TIMEOUT: PayloadState.CAPTURED,
    PayloadState.RETRACT_TIMEOUT: PayloadState.GRAPPLED,
    PayloadState.PAYLOAD_NOT_SECURED: PayloadState.IDLE,
    PayloadState.RELEASE_TIMEOUT: PayloadState.TRANSPORTING,
    PayloadState.STOW_FAILED: PayloadState.RELEASED,
}


class _Backend(PayloadBackend):
    """Her adimi kontrol edilebilir sahte backend."""

    def __init__(self, **ok):
        self.ok = {"deploy": True, "await_capture": True, "grapple": True,
                   "retract": True, "release": True, "stow": True}
        self.ok.update(ok)
        self.secured = ok.get("secured", True)
        self.calls = []

    async def _a(self, n):
        self.calls.append(n)
        return self.ok[n]

    def select_payload(self, target_shape: str) -> None:
        self.selected_payload = target_shape

    async def deploy(self): return await self._a("deploy")
    async def await_capture(self): return await self._a("await_capture")
    async def grapple(self): return await self._a("grapple")
    async def retract(self): return await self._a("retract")
    async def lower_for_release(self): return await self._a("lower_for_release")
    async def release(self): return await self._a("release")
    async def stow(self): return await self._a("stow")

    def is_deployed(self): return True
    def is_in_capture_zone(self): return True
    def has_captured(self): return True
    def is_grappled(self): return True
    def is_secured(self): return self.secured
    def has_released(self): return True


def _machine_at(state: PayloadState) -> PayloadStateMachine:
    """State machine'i istenen failure state'e MESRU yoldan goturur."""
    m = PayloadStateMachine()
    paths = {
        PayloadState.DEPLOY_TIMEOUT: [PayloadState.DEPLOYING],
        PayloadState.CAPTURE_TIMEOUT: [PayloadState.DEPLOYING, PayloadState.DEPLOYED,
                                       PayloadState.SEARCHING],
        PayloadState.GRAPPLE_TIMEOUT: [PayloadState.DEPLOYING, PayloadState.DEPLOYED,
                                       PayloadState.SEARCHING, PayloadState.CAPTURED,
                                       PayloadState.GRAPPLING],
        PayloadState.RETRACT_TIMEOUT: [PayloadState.DEPLOYING, PayloadState.DEPLOYED,
                                       PayloadState.SEARCHING, PayloadState.CAPTURED,
                                       PayloadState.GRAPPLING, PayloadState.GRAPPLED,
                                       PayloadState.RETRACTING],
        PayloadState.RELEASE_TIMEOUT: [PayloadState.DEPLOYING, PayloadState.DEPLOYED,
                                       PayloadState.SEARCHING, PayloadState.CAPTURED,
                                       PayloadState.GRAPPLING, PayloadState.GRAPPLED,
                                       PayloadState.RETRACTING, PayloadState.SECURED,
                                       PayloadState.TRANSPORTING, PayloadState.RELEASING],
        PayloadState.STOW_FAILED: [PayloadState.DEPLOYING, PayloadState.DEPLOYED,
                                   PayloadState.SEARCHING, PayloadState.CAPTURED,
                                   PayloadState.GRAPPLING, PayloadState.GRAPPLED,
                                   PayloadState.RETRACTING, PayloadState.SECURED,
                                   PayloadState.TRANSPORTING, PayloadState.RELEASING,
                                   PayloadState.RELEASED],
    }
    path = paths.get(state)
    if path is None:  # PAYLOAD_NOT_SECURED
        path = [PayloadState.DEPLOYING, PayloadState.DEPLOYED, PayloadState.SEARCHING,
                PayloadState.CAPTURED, PayloadState.GRAPPLING, PayloadState.GRAPPLED,
                PayloadState.RETRACTING]
    for step in path:
        m.transition_to(step)
    m.transition_to(state)
    return m


# ---------------------------------------------------------------------------
# 1-2. Kurtarma haritasi
# ---------------------------------------------------------------------------

def test_every_failure_state_has_an_explicit_recovery_decision():
    """Sessizce atlanan failure state OLMAMALI -- yeni bir failure state
    eklenirse bu test onu yakalar."""
    assert set(_RECOVERY_TRANSITIONS) == set(_FAILURE_STATES)


@pytest.mark.parametrize("failure,target", sorted(_EXPECTED.items(), key=lambda kv: kv[0].value))
def test_recovery_targets_match_the_design_table(failure, target):
    assert _RECOVERY_TRANSITIONS[failure] is target


@pytest.mark.parametrize("failure,target", sorted(_EXPECTED.items(), key=lambda kv: kv[0].value))
def test_recover_moves_to_the_designed_state(failure, target):
    m = _machine_at(failure)
    assert m.current_state is failure
    assert m.recover() is target
    assert m.current_state is target


def test_success_terminal_cannot_be_recovered():
    """RETRACTED bir BASARI terminalidir -- kurtarilacak bir sey yok."""
    m = PayloadStateMachine()
    for step in [PayloadState.DEPLOYING, PayloadState.DEPLOYED, PayloadState.SEARCHING,
                 PayloadState.CAPTURED, PayloadState.GRAPPLING, PayloadState.GRAPPLED,
                 PayloadState.RETRACTING, PayloadState.SECURED, PayloadState.TRANSPORTING,
                 PayloadState.RELEASING, PayloadState.RELEASED, PayloadState.RETRACTED]:
        m.transition_to(step)
    with pytest.raises(NoRecoveryPathError):
        m.recover()


def test_recovery_is_recorded_in_history():
    m = _machine_at(PayloadState.RETRACT_TIMEOUT)
    before = len(m.history)
    m.recover()
    assert len(m.history) == before + 1
    last = m.history[-1]
    assert last.previous_state is PayloadState.RETRACT_TIMEOUT
    assert last.new_state is PayloadState.GRAPPLED


# ---------------------------------------------------------------------------
# 3. Kurtarma kaza eseri olamaz
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("failure", _FAILURE_STATES)
def test_normal_transition_graph_unchanged_failure_states_still_terminal(failure):
    """KRITIK: kurtarma kenarlari _TRANSITIONS'a EKLENMEDI. Failure
    state'ler normal transition_to() ile hala terminal -- yoksa kurtarma
    herhangi bir cagriyla kaza eseri olabilirdi."""
    m = _machine_at(failure)
    assert failure.is_terminal, "is_terminal anlamini yitirmis"
    with pytest.raises(IllegalPayloadTransitionError):
        m.transition_to(_EXPECTED[failure])


# ---------------------------------------------------------------------------
# 4. Butce
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recovery_budget_is_bounded_and_refuses_when_spent():
    """Sinirsiz tekrar 10 dakikalik gorev butcesini sessizce tuketebilirdi."""
    manager = PayloadManager(_Backend(deploy=False))
    for i in range(MAX_RECOVERY_ATTEMPTS):
        result = await manager.catch_box_down()
        assert result.success is False
        assert manager.can_recover() is True
        manager.recover()
        assert manager.recovery_attempts == i + 1

    result = await manager.catch_box_down()
    assert result.success is False
    assert manager.can_recover() is False, "butce tukendi ama kurtarilabilir gorunuyor"
    with pytest.raises(NoRecoveryPathError):
        manager.recover()


def test_can_recover_is_false_in_healthy_states():
    manager = PayloadManager(_Backend())
    assert manager.get_state() is PayloadState.IDLE
    assert manager.can_recover() is False


@pytest.mark.asyncio
async def test_recovered_state_allows_the_step_to_be_retried():
    """Kurtarma sonrasi cagiran ilgili komutu YENIDEN calistirabilmeli --
    kurtarmanin tek amaci bu."""
    backend = _Backend(retract=False)
    manager = PayloadManager(backend)
    await manager.catch_box_down()
    await manager.grapple()
    assert (await manager.catch_box_up()).success is False
    assert manager.get_state() is PayloadState.RETRACT_TIMEOUT

    assert manager.recover() is PayloadState.GRAPPLED
    backend.ok["retract"] = True          # ariza gecici imis
    result = await manager.catch_box_up()

    assert result.success is True
    assert manager.get_state() is PayloadState.TRANSPORTING


# ---------------------------------------------------------------------------
# 5. Otomatik DEGIL
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_failed_command_does_not_retry_itself():
    """KASITLI: gorunmez bir tekrar, Phase 15'in olcmesi gereken
    guvenilirlik oranini bozardi (KNOWN_ISSUES §5). Basarisiz komut
    backend'i TEK KEZ cagirmali."""
    backend = _Backend(deploy=False)
    manager = PayloadManager(backend)

    await manager.catch_box_down()

    assert backend.calls == ["deploy"], f"komut kendiliginden tekrarlandi: {backend.calls}"
    assert manager.recovery_attempts == 0, "kurtarma kendiliginden yapildi"
