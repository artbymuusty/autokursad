"""PHASE 2: Behavioural Hook Model.

HookBehaviourModel "nasıl" yapıldığını bilmez, sadece "ne olduğunu" sorar --
her metodu, kendisine enjekte edilen PayloadBackend'in aynı isimli query
primitifine 1:1 delege eder. Gerçek implementasyon (Real: manyetik+fiziksel
temas sensörü/servo state; Gazebo: capture envelope + joint varlığı)
backend'e ait -- backend'ler henüz PHASE 0 skeleton olduğu için (bkz.
payload/backends/real_payload_backend.py, gazebo_payload_backend.py) bu
metodların çağrılması şu an NotImplementedError'a kadar zincirlenir. Bu
kasıtlı: PHASE 4/5'te backend'ler doldurulduğunda bu dosyada HİÇBİR
değişiklik gerekmeyecek.
"""
from payload.backends.payload_backend import PayloadBackend


class HookBehaviourModel:
    """Backend-agnostik davranışsal sorgu yüzeyi. PayloadManager, backend'in
    somut tipini hiç bilmeden bu sınıf üzerinden "şu an ne durumdayız?"
    sorusunu sorar."""

    def __init__(self, backend: PayloadBackend) -> None:
        self._backend = backend

    def is_deployed(self) -> bool:
        return self._backend.is_deployed()

    def is_in_capture_zone(self) -> bool:
        return self._backend.is_in_capture_zone()

    def has_captured(self) -> bool:
        return self._backend.has_captured()

    def is_grappled(self) -> bool:
        return self._backend.is_grappled()

    def is_secured(self) -> bool:
        return self._backend.is_secured()

    def has_released(self) -> bool:
        return self._backend.has_released()
