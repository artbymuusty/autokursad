"""PayloadInterlock sozlesmesi.

SPEC DEGISIKLIGI (2026-09-01): bu testler eskiden "payload 2, payload 1'den
once birakilamaz" kuralini sabitliyordu. O kural sirayi SEKLE bagliyordu ve
gozlenen sonucu, hangi hedef once tespit edilirse edilsin ILK birakmanin
HER ZAMAN Mavi Altigen'e gitmesiydi -- V33 spec madde 11'e aykiri.

Yeni sozlesme: sira TAMAMLANMA SIRASINDAN turur; korunan tek degismez
kosul ayni hedefe iki kez birakilamamasidir.
"""
import pytest
from core.mission.interlock import PayloadInterlock


def test_ucgen_once_birakilabilir():
    """V33 spec madde 11: Kirmizi Ucgen once tamamlanabilir."""
    i = PayloadInterlock()
    assert i.can_release("KIRMIZI_UCGEN") is True
    i.mark_released("KIRMIZI_UCGEN")
    assert i.release_order == ["KIRMIZI_UCGEN"]
    assert i.both_released() is False


def test_altigen_once_birakilabilir():
    i = PayloadInterlock()
    i.mark_released("MAVI_ALTIGEN")
    assert i.release_order == ["MAVI_ALTIGEN"]


@pytest.mark.parametrize("first,second", [
    ("MAVI_ALTIGEN", "KIRMIZI_UCGEN"),
    ("KIRMIZI_UCGEN", "MAVI_ALTIGEN"),
])
def test_iki_sira_da_gecerli(first, second):
    """Her iki tamamlanma sirasi da gecerli olmali."""
    i = PayloadInterlock()
    i.mark_released(first)
    i.mark_released(second)
    assert i.both_released() is True
    assert i.release_order == [first, second]
    assert i.payload_1_released is True     # sekil-bazli okuma korundu
    assert i.payload_2_released is True


def test_ayni_hedefe_iki_kez_birakilamaz():
    """Korunan tek degismez kosul."""
    i = PayloadInterlock()
    i.mark_released("MAVI_ALTIGEN")
    with pytest.raises(RuntimeError) as exc:
        i.mark_released("MAVI_ALTIGEN")
    assert "INTERLOCK IHLALI" in str(exc.value)


def test_terminal_birakma_ikincidir():
    i = PayloadInterlock()
    assert i.is_terminal_release("KIRMIZI_UCGEN") is False   # henuz birinci
    i.mark_released("MAVI_ALTIGEN")
    assert i.is_terminal_release("KIRMIZI_UCGEN") is True    # artik ikinci


def test_sekil_bazli_okumalar_sirayla_karismaz():
    i = PayloadInterlock()
    i.mark_released("KIRMIZI_UCGEN")
    assert i.payload_2_released is True
    assert i.payload_1_released is False    # altigen henuz birakilmadi
