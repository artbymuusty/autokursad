"""PHASE 0 (Mimari Freeze): payload/ paketi.

Mission mantığının payload mekanizmasıyla (Real donanım: Servo2/Servo3/
Reel/Rope/Hook/Magnet; Gazebo: Joint + Payload Physics) konuştuğu TEK
abstraction katmanı. Üst seviye görev kodu, aşağıdaki gibi sadece
PayloadManager'ı import eder ve hangi backend'in altta çalıştığını hiçbir
zaman bilmez:

    from payload import PayloadManager, PayloadState, PayloadResult

Bu paket bu görevde (PHASE 0-3) mevcut gz_system/gz_payload_actuator.py,
core/mission/mission_v3_state.py::PayloadInterlock ve HookAttachSystem.cc
ile HİÇBİR şekilde bağlanmadı -- tamamen bağımsız, paralel bir iskelet.
"""
from payload.payload_manager import PayloadManager
from payload.payload_state import (
    IllegalPayloadTransitionError, NoRecoveryPathError, PayloadStateMachine,
    StateTransitionRecord,
)
from payload.payload_types import PayloadResult, PayloadState

__all__ = [
    "PayloadManager",
    "PayloadState",
    "PayloadResult",
    "PayloadStateMachine",
    "StateTransitionRecord",
    "IllegalPayloadTransitionError",
    "NoRecoveryPathError",
]
