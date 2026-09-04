"""
GOREV G / O1 -- extend_winch_for() artik GERI CEKME uretmez.

KUSUR (docs/gorevG-FAIL3-vinc-analiz.md): ayni fonksiyon iki yerden IKI
FARKLI irtifa argumaniyla cagriliyordu --
    gorev3_pickup.py:924      GOREV3_DESCENT_ALTITUDE_M = 0.30  -> salim 0.330 m
    aktuator, her denemede    _pick_alt = 0.094-0.161           -> salim 0.124-0.191 m
Ikincisi kucuk oldugu icin vinci 113-186 mm GERI CEKIYORDU ve insertion
TAM O KADAR bozuluyordu (r1/r3b'de 1.00 oranla birebir).

Iki katman korunuyor:
  1. gorev katmani artik salim referansi olarak NOMINAL degeri veriyor,
  2. aktuator, ne verilirse verilsin, ulasilmis salimin altina inmiyor.
"""
import pytest

from gz_system.gz_payload_actuator import (
    GzPayloadActuator, hook_payout_m,
    HOOK_WINCH_RETRACT_M, HOOK_RECEIVER_DECK_HEIGHT_M,
)
from core.config.parameters import GOREV3_DESCENT_ALTITUDE_M


class _FakeWinchActuator(GzPayloadActuator):
    """Gercek extend_winch_for'u kosturur; yalnizca gz yayinini ve poz
    okumasini yerine koyar -- yani test edilen sey KARAR MANTIGI."""
    def __init__(self, achieved_m):
        self._achieved = achieved_m
        self.sent = []

    def winch_state(self):
        return {"achieved_m": self._achieved}

    async def set_winch(self, extension_m):
        self.sent.append(round(extension_m, 6))
        self._achieved = extension_m
        return True


def test_formul_nominal_irtifada_beklenen_salimi_verir():
    """0.30 m nominal -> 0.330 m. Olculen 0.094-0.161 ise 0.124-0.191 verirdi."""
    assert hook_payout_m(GOREV3_DESCENT_ALTITUDE_M) == pytest.approx(0.330, abs=1e-9)
    for olculen in (0.094, 0.161):
        assert hook_payout_m(olculen) < 0.20


@pytest.mark.asyncio
async def test_kucuk_hesap_GERI_CEKME_uretmez():
    """Kusurun ta kendisi: 0.330 m kuruluyken 0.191 m istenirse vinc
    0.330'da KALMALI, 0.191'e cekilmemeli."""
    act = _FakeWinchActuator(achieved_m=0.330)
    ok = await act.extend_winch_for(0.161, HOOK_RECEIVER_DECK_HEIGHT_M)
    assert ok is True
    assert act.sent == [], f"vinc geri cekildi: {act.sent}"
    assert act._last_payout_m == pytest.approx(0.330)
    assert act._last_payout_blocked_retract_m == pytest.approx(0.330 - 0.191, abs=1e-6)


@pytest.mark.asyncio
async def test_buyuk_hesap_NORMAL_uygulanir():
    """Koruma yalnizca KUCULMEYI engeller; buyume aynen gecer."""
    act = _FakeWinchActuator(achieved_m=0.10)
    await act.extend_winch_for(GOREV3_DESCENT_ALTITUDE_M, HOOK_RECEIVER_DECK_HEIGHT_M)
    assert act.sent == [pytest.approx(0.330)]
    assert act._last_payout_blocked_retract_m is None


@pytest.mark.asyncio
async def test_ACIK_geri_cekme_yolu_ETKILENMEZ():
    """Denemeler arasi geri cekme set_winch(RETRACT) kullaniyor; koruma
    o yolu kapatmamali, yoksa yeniden hizalama rejimi bozulur."""
    act = _FakeWinchActuator(achieved_m=0.330)
    await act.set_winch(HOOK_WINCH_RETRACT_M)
    assert act.sent == [pytest.approx(0.0)]
    assert act._achieved == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_geri_cekme_sonrasi_yeniden_salim_calisir():
    """Koruma 'bir kez uzadi, bir daha kisalamaz' DEMEK DEGIL."""
    act = _FakeWinchActuator(achieved_m=0.330)
    await act.set_winch(HOOK_WINCH_RETRACT_M)
    act.sent.clear()
    await act.extend_winch_for(GOREV3_DESCENT_ALTITUDE_M, HOOK_RECEIVER_DECK_HEIGHT_M)
    assert act.sent == [pytest.approx(0.330)]


@pytest.mark.asyncio
async def test_poz_okunamazsa_davranis_ESKISI_gibi():
    """Olcum yoksa koruma da yok -- uydurulmus bir sinirla is yapilmaz."""
    class _NoPose(_FakeWinchActuator):
        def winch_state(self):
            return None
    act = _NoPose(achieved_m=0.330)
    await act.extend_winch_for(0.161, HOOK_RECEIVER_DECK_HEIGHT_M)
    assert act.sent == [pytest.approx(0.191)]
