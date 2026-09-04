"""
GOREV G / O3 -- YAPISAL ERISIM DISI korumasi.

Olcut FORMULU DEGIL OLCUMU kullanir:
    gereken_salim = ulasilan_salim + (-en_derin_insertion)
Ikisi de dogrudan olculur; HOOK_PAYOUT_CHAIN_OFFSET_M, irtifa ya da datum
varsayimi GIRMEZ. Bu yuzden koruma O5'in kok nedeninden ve O2'nin
sonucundan BAGIMSIZDIR -- bu dosyanin korudugu asil ozellik budur.

Ayirt edicilik olculdu (docs/gorevG-O5-tutma-irtifasi.md §3.3): 9 denemede
tek "devam" karari, kapiya giren TEK denemeye denk geldi.
"""
import pytest

from gz_system.gz_payload_actuator import (
    GzPayloadActuator, HOOK_WINCH_MAX_EXTENSION_M,
)

COLS = ["t_s", "tilt_deg", "lat_mm", "ins_mm", "winch_m", "span_m", "fold_deg"]


def _report(achieved_m, ins_mm_list):
    return {
        "winch_at_window_start": {"achieved_m": achieved_m},
        "seat_trace_cols": COLS,
        "seat_trace": [[0.1 * i, 0.3, 12.0, v, achieved_m, 0.183, [0, 0, 0, 0]]
                       for i, v in enumerate(ins_mm_list)],
    }


def test_olculen_o1a1_DEVAM_der():
    """Kapiya giren TEK deneme: 0.3285 + 4.6 mm -> 0.3239 m, sinir altinda."""
    need = GzPayloadActuator._reach_shortfall_m(_report(0.3285, [-50.0, -10.0, 4.6]))
    assert need == pytest.approx(0.3239, abs=1e-4)
    assert need <= HOOK_WINCH_MAX_EXTENSION_M


@pytest.mark.parametrize("tag,achieved,deepest,beklenen", [
    ("o1a/2", 0.3285, -95.3, 0.4238),
    ("o1b/1", 0.3287, -94.9, 0.4236),
    ("o1b/2", 0.3286, -124.2, 0.4528),
    ("o1d/1", 0.3285, -114.1, 0.4426),
])
def test_olculen_doyum_vakalari_DUR_der(tag, achieved, deepest, beklenen):
    need = GzPayloadActuator._reach_shortfall_m(_report(achieved, [-300.0, deepest]))
    assert need == pytest.approx(beklenen, abs=1e-4), tag
    assert need > HOOK_WINCH_MAX_EXTENSION_M, tag


def test_EN_DERIN_ornek_kullanilir_ortalama_degil():
    """Sarkac salinimi ortalamayi bozar; olcut 'en fazla ne kadar yaklasti'."""
    need = GzPayloadActuator._reach_shortfall_m(
        _report(0.30, [-400.0, -350.0, -20.0, -380.0]))
    assert need == pytest.approx(0.32, abs=1e-6)


def test_olcum_yoksa_koruma_da_yok():
    """Uydurulmus bir sinirla gorev dusurulmez."""
    assert GzPayloadActuator._reach_shortfall_m(None) is None
    assert GzPayloadActuator._reach_shortfall_m({}) is None
    assert GzPayloadActuator._reach_shortfall_m(
        {"winch_at_window_start": {}, "seat_trace_cols": COLS,
         "seat_trace": [[0, 0, 0, -50.0, 0, 0, 0]]}) is None
    assert GzPayloadActuator._reach_shortfall_m(
        {"winch_at_window_start": {"achieved_m": 0.3}, "seat_trace_cols": COLS,
         "seat_trace": []}) is None


def test_olcut_SABIT_ICERMEZ():
    """O2/O5'ten bagimsizligin testi: ayni girdi, sabitler degisse de ayni
    cikti. CHAIN_OFFSET ve irtifa fonksiyona hic girmiyor."""
    import gz_system.gz_payload_actuator as gz
    rapor = _report(0.3287, [-94.9])
    once = GzPayloadActuator._reach_shortfall_m(rapor)
    eski_chain = gz.HOOK_PAYOUT_CHAIN_OFFSET_M
    eski_deck = gz.HOOK_RECEIVER_DECK_HEIGHT_M
    try:
        gz.HOOK_PAYOUT_CHAIN_OFFSET_M = 0.245
        gz.HOOK_RECEIVER_DECK_HEIGHT_M = 0.500
        sonra = GzPayloadActuator._reach_shortfall_m(rapor)
    finally:
        gz.HOOK_PAYOUT_CHAIN_OFFSET_M = eski_chain
        gz.HOOK_RECEIVER_DECK_HEIGHT_M = eski_deck
    assert once == sonra
