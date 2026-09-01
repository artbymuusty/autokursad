"""PHASE 0 (Mimari Freeze): payload/ paketinin ortak veri tipleri.

Bu dosya, PayloadManager'ın public API'sinin ve PHASE 1 state machine'inin
üzerine kurulduğu paylaşılan sözlüğü tanımlar: hangi state'ler var
(PayloadState), ve bir komut çalıştırıldığında çağıran tarafa ne dönüyor
(PayloadResult). Backend-spesifik hiçbir şey burada YOKTUR -- Real ve
Gazebo backend'leri bu tipleri aynen paylaşır.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PayloadState(Enum):
    """Backend'den bağımsız payload yaşam döngüsü state'leri (PHASE 1).

    Mutlu yol sırası (V33 SERVO2_DOWN -> CATCH_PAYLOAD -> TIMEOUT_CHECK ->
    SERVO3_GRAPPLE -> SERVO2_REVERSE -> ... -> SERVO3_RELEASE ->
    SERVO2_REVERSE referans akışının karşılığı):

        IDLE -> DEPLOYING -> DEPLOYED -> SEARCHING -> CAPTURED ->
        GRAPPLING -> GRAPPLED -> RETRACTING -> SECURED -> TRANSPORTING ->
        RELEASING -> RELEASED -> RETRACTED

    RELEASED'ten ikinci bir dallanma var: stow() (V33 SERVO2_REVERSE,
    2./son kullanım) başarısız olursa RETRACTED yerine STOW_FAILED'a
    gidilir. Bu, payload'ın fiziksel olarak bırakılmış OLMASINA rağmen
    mekanizmanın toparlanamadığı bir durumu ayırt etmek için var --
    PayloadResult.success bu durumda hâlâ True olabilir (payload
    bırakıldı), ama get_state() ile STOW_FAILED görülebilir olur (bkz.
    payload_manager.py::release()).

    Legal geçiş grafiği payload_state.py::PayloadStateMachine._TRANSITIONS
    içinde tanımlıdır -- bu enum sadece isimleri taşır, hiçbir geçiş
    mantığı içermez.
    """
    IDLE = "IDLE"
    DEPLOYING = "DEPLOYING"
    DEPLOYED = "DEPLOYED"
    SEARCHING = "SEARCHING"
    CAPTURED = "CAPTURED"
    GRAPPLING = "GRAPPLING"
    GRAPPLED = "GRAPPLED"
    RETRACTING = "RETRACTING"
    SECURED = "SECURED"
    TRANSPORTING = "TRANSPORTING"
    RELEASING = "RELEASING"
    RELEASED = "RELEASED"
    RETRACTED = "RETRACTED"

    # Failure state'leri -- hepsi terminal (dışarı giden legal geçişi yok).
    DEPLOY_TIMEOUT = "DEPLOY_TIMEOUT"
    CAPTURE_TIMEOUT = "CAPTURE_TIMEOUT"
    GRAPPLE_TIMEOUT = "GRAPPLE_TIMEOUT"
    RETRACT_TIMEOUT = "RETRACT_TIMEOUT"
    RELEASE_TIMEOUT = "RELEASE_TIMEOUT"
    PAYLOAD_NOT_SECURED = "PAYLOAD_NOT_SECURED"
    STOW_FAILED = "STOW_FAILED"

    @property
    def is_failure(self) -> bool:
        return self in _FAILURE_STATES

    @property
    def is_terminal(self) -> bool:
        """Dışarı giden hiçbir legal geçişi olmayan state (basari: RETRACTED,
        basarisizlik: is_failure state'lerinin hepsi)."""
        return self is PayloadState.RETRACTED or self.is_failure


_FAILURE_STATES = frozenset({
    PayloadState.DEPLOY_TIMEOUT,
    PayloadState.CAPTURE_TIMEOUT,
    PayloadState.GRAPPLE_TIMEOUT,
    PayloadState.RETRACT_TIMEOUT,
    PayloadState.RELEASE_TIMEOUT,
    PayloadState.PAYLOAD_NOT_SECURED,
    PayloadState.STOW_FAILED,
})


@dataclass(frozen=True)
class PayloadResult:
    """PayloadManager'ın 4 public komutunun (catch_box_down/grapple/
    catch_box_up/release) döndürdüğü tek sonuç tipi.

    PHASE 13'te (bu görevin kapsamı dışında) kullanılacak
    `if not result.success: mission.fail(...)` deseninin önünü açar --
    burada sadece tip tanımlanır, failure-dispatch mantığı implement
    edilmez.
    """
    success: bool
    final_state: PayloadState
    error_reason: Optional[str]
    elapsed_time: float
