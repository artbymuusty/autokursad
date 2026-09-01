"""PHASE 6.5: PayloadManager yerine gecen sahte.

Gorev3 fazlari artik IPayloadActuator yerine payload/PayloadManager
cagiriyor (supersede karari). Bu mock, mission-katmani testlerinin gercek
bir backend/gz baglantisi olmadan o yolu surmesini saglar.

Kayit formati mocks/mock_payload_actuator.py ile ayni desende
(('metod_adi', {}) ciftleri) tutuldu -- eski testlerin iddia bicimi
degismeden tasinabilsin diye.
"""
from typing import List, Tuple

from payload.payload_types import PayloadResult, PayloadState

_SUCCESS_STATES = {
    "catch_box_down": PayloadState.CAPTURED,
    "grapple": PayloadState.GRAPPLED,
    "catch_box_up": PayloadState.TRANSPORTING,
    "release": PayloadState.RETRACTED,
}
_FAILURE_STATES = {
    "catch_box_down": PayloadState.CAPTURE_TIMEOUT,
    "grapple": PayloadState.GRAPPLE_TIMEOUT,
    "catch_box_up": PayloadState.RETRACT_TIMEOUT,
    "release": PayloadState.RELEASE_TIMEOUT,
}


class MockPayloadManager:
    """`fail_on`: bu metodda PayloadResult(success=False) doner.
    `raise_on`: bu metodda verilen exception'i yukseltir (Real yolun
    kalibre edilmemis/sensorsuz davranisini taklit etmek icin)."""

    def __init__(self, fail_on: str = None, raise_on: str = None, exception=None,
                 still_secured: bool = True):
        self.calls: List[Tuple[str, dict]] = []
        self._fail_on = fail_on
        self._raise_on = raise_on
        self._exception = exception or NotImplementedError("sahte backend bosluğu")
        self._state = PayloadState.IDLE
        self._still_secured = still_secured
        self.selected_payload = None

    def select_payload(self, target_shape: str) -> None:
        """2026-08-24 dinamik hedef: Gorev 3 hangi payload'i alacagini
        calisma zamaninda secer. Test bunu kaydeder ki dogru hedefin
        secildigi dogrulanabilsin."""
        self.selected_payload = target_shape

    def get_state(self) -> PayloadState:
        return self._state

    def is_still_secured(self) -> bool:
        """PHASE 15: alma dogrulamasi artik fiziksel. raise_on
        'is_still_secured' verilirse Real yolun sorgu boslugunu taklit eder."""
        if self._raise_on == "is_still_secured":
            raise self._exception
        return self._still_secured

    async def _step(self, name: str) -> PayloadResult:
        self.calls.append((name, {}))
        if self._raise_on == name:
            raise self._exception
        if self._fail_on == name:
            self._state = _FAILURE_STATES[name]
            return PayloadResult(success=False, final_state=self._state,
                                 error_reason=f"{name} sahte basarisizlik", elapsed_time=0.0)
        self._state = _SUCCESS_STATES[name]
        return PayloadResult(success=True, final_state=self._state,
                             error_reason=None, elapsed_time=0.0)

    async def catch_box_down(self) -> PayloadResult:
        return await self._step("catch_box_down")

    async def grapple(self) -> PayloadResult:
        return await self._step("grapple")

    async def catch_box_up(self) -> PayloadResult:
        return await self._step("catch_box_up")

    async def release(self) -> PayloadResult:
        return await self._step("release")
