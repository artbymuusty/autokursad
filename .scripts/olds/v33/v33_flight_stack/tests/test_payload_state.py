"""PHASE 1 unit test iskeleti: PayloadStateMachine.

Gerçek fizik/backend YOK -- sadece geçiş mantığı test ediliyor. Real ve
Gazebo backend'leri (PHASE 4/5) ne zaman gelirse gelsin, bu state machine
ikisinin de aynı state sırasını üretmeye zorlanacağı ortak zemin (PHASE 15
parity testinin önkoşulu).
"""
import pytest

from payload.payload_state import (
    IllegalPayloadTransitionError,
    PayloadStateMachine,
)
from payload.payload_types import PayloadState

HAPPY_PATH = [
    PayloadState.DEPLOYING,
    PayloadState.DEPLOYED,
    PayloadState.SEARCHING,
    PayloadState.CAPTURED,
    PayloadState.GRAPPLING,
    PayloadState.GRAPPLED,
    PayloadState.RETRACTING,
    PayloadState.SECURED,
    PayloadState.TRANSPORTING,
    PayloadState.RELEASING,
    PayloadState.RELEASED,
    PayloadState.RETRACTED,
]

ALL_FAILURE_STATES = [
    PayloadState.DEPLOY_TIMEOUT,
    PayloadState.CAPTURE_TIMEOUT,
    PayloadState.GRAPPLE_TIMEOUT,
    PayloadState.RETRACT_TIMEOUT,
    PayloadState.STOW_FAILED,
    PayloadState.RELEASE_TIMEOUT,
    PayloadState.PAYLOAD_NOT_SECURED,
]


def test_initial_state_is_idle():
    machine = PayloadStateMachine()
    assert machine.current_state is PayloadState.IDLE
    assert machine.history == []


def test_legal_transition_succeeds():
    machine = PayloadStateMachine()
    machine.transition_to(PayloadState.DEPLOYING)
    assert machine.current_state is PayloadState.DEPLOYING


def test_illegal_transition_raises_and_does_not_mutate_state():
    """Geçersiz bir geçiş sessizce yutulmamalı VE state'i bozmamalı."""
    machine = PayloadStateMachine()
    with pytest.raises(IllegalPayloadTransitionError):
        machine.transition_to(PayloadState.GRAPPLING)  # IDLE'dan direkt GRAPPLING illegal
    assert machine.current_state is PayloadState.IDLE
    assert machine.history == []


def test_full_happy_path_sequence_is_legal():
    """Mutlu yolun TAMAMI, V33 referans akışının karşılığı olarak, baştan
    sona hiçbir exception fırlatmadan yürümeli."""
    machine = PayloadStateMachine()
    for state in HAPPY_PATH:
        machine.transition_to(state)
    assert machine.current_state is PayloadState.RETRACTED
    assert [record.new_state for record in machine.history] == HAPPY_PATH


def test_released_can_branch_into_stow_failed_instead_of_retracted():
    """RELEASED bir başarı kilometre taşı ama ikinci bir dallanma noktası:
    stow() başarısız olursa RETRACTED yerine STOW_FAILED'a gidilir (payload
    zaten bırakıldı, sadece mekanizma toparlanamadı -- bkz.
    payload_manager.py::release() 2026-08-22 kararı)."""
    machine = PayloadStateMachine()
    for state in HAPPY_PATH:
        machine.transition_to(state)
        if state is PayloadState.RELEASED:
            break
    machine.transition_to(PayloadState.STOW_FAILED)
    assert machine.current_state is PayloadState.STOW_FAILED


@pytest.mark.parametrize("in_progress_state,failure_state", [
    (PayloadState.DEPLOYING, PayloadState.DEPLOY_TIMEOUT),
    (PayloadState.SEARCHING, PayloadState.CAPTURE_TIMEOUT),
    (PayloadState.GRAPPLING, PayloadState.GRAPPLE_TIMEOUT),
    (PayloadState.RETRACTING, PayloadState.RETRACT_TIMEOUT),
    (PayloadState.RETRACTING, PayloadState.PAYLOAD_NOT_SECURED),
    (PayloadState.RELEASING, PayloadState.RELEASE_TIMEOUT),
])
def test_in_progress_state_can_fail_into_its_failure_state(in_progress_state, failure_state):
    machine = PayloadStateMachine()
    # in_progress_state'e kadar mutlu yoldan ilerle.
    for state in HAPPY_PATH:
        machine.transition_to(state)
        if state is in_progress_state:
            break
    machine.transition_to(failure_state)
    assert machine.current_state is failure_state


@pytest.mark.parametrize("terminal_state", ALL_FAILURE_STATES + [PayloadState.RETRACTED])
def test_terminal_states_have_no_legal_outgoing_transition(terminal_state):
    """Hem başarı hem başarısızlık terminal state'lerinden HİÇBİR yere
    otomatik geçiş yok -- bir retry/reset akışı ayrı bir tasarım kararı."""
    machine = PayloadStateMachine()
    machine._current_state = terminal_state  # testte doğrudan state enjekte etmek meşru: sadece grafı sınıyoruz.
    for candidate in PayloadState:
        with pytest.raises(IllegalPayloadTransitionError):
            machine.transition_to(candidate)


def test_history_records_previous_state_and_timestamp_in_order():
    machine = PayloadStateMachine()
    machine.transition_to(PayloadState.DEPLOYING)
    machine.transition_to(PayloadState.DEPLOYED)

    assert len(machine.history) == 2
    first, second = machine.history
    assert first.previous_state is PayloadState.IDLE
    assert first.new_state is PayloadState.DEPLOYING
    assert second.previous_state is PayloadState.DEPLOYING
    assert second.new_state is PayloadState.DEPLOYED
    assert first.timestamp <= second.timestamp


def test_history_is_a_defensive_copy():
    """Çağıran history() listesini mutasyona uğratsa bile machine'in iç
    tarihçesi bozulmamalı."""
    machine = PayloadStateMachine()
    machine.transition_to(PayloadState.DEPLOYING)
    machine.history.clear()
    assert len(machine.history) == 1
