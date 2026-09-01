"""PayloadInterlock testleri.

YENİDEN YAZILDI (2026-08-24): bu dosya eskiden "payload_2, payload_1'den
önce bırakılamaz" SIRA kuralını doğruluyordu. Proje sahibi o kuralın
geçerli olmadığını bildirdi ve dinamik sıraya geçildi (V33 spec md.6/11).
Testler SİLİNMEDİ -- yeni davranışı doğrulayacak şekilde yeniden yazıldı:
sıra artık serbest, ama MUHASEBE (both_released, ayrı bayraklar) aynı
titizlikle korunuyor.
"""
import pytest

from core.mission.interlock import PayloadInterlock


def test_triangle_payload_can_release_first():
    """DAVRANIŞ DEĞİŞİKLİĞİ: eskiden RuntimeError'dı. Kırmızı Üçgen önce
    tespit edilirse yükü önce bırakılabilmeli."""
    interlock = PayloadInterlock()
    interlock.mark_payload_2_released()          # artık fırlatmıyor
    assert interlock.payload_2_released is True
    assert interlock.payload_1_released is False
    assert interlock.both_released() is False


def test_hexagon_payload_can_release_first():
    """Simetrik: eski sıra da hâlâ geçerli bir sıradır."""
    interlock = PayloadInterlock()
    interlock.mark_payload_1_released()
    assert interlock.payload_1_released is True
    assert interlock.both_released() is False


@pytest.mark.parametrize("order", [("1", "2"), ("2", "1")])
def test_both_released_only_after_both_orders(order):
    """MUHASEBE KORUNDU: hangi sırayla olursa olsun both_released() ancak
    İKİSİ de bırakılınca True. Görev 3'ün ön koşulu buna bağlı."""
    interlock = PayloadInterlock()
    for step in order:
        getattr(interlock, f"mark_payload_{step}_released")()
        assert interlock.payload_1_released or interlock.payload_2_released
    assert interlock.both_released() is True


def test_can_release_payload_2_no_longer_gates():
    """İmza geriye dönük uyumluluk için korundu ama artık kapı DEĞİL --
    her zaman True. Yeni kod buna dayanmamalı."""
    interlock = PayloadInterlock()
    assert interlock.can_release_payload_2() is True
    interlock.mark_payload_1_released()
    assert interlock.can_release_payload_2() is True


def test_no_interlock_violation_event_is_published():
    """Sıra ihlali diye bir şey kalmadı -- üçgen önce bırakmak artık
    beklenen davranış, CRITICAL event üretMEMELİ."""
    class _Collector:
        def __init__(self):
            self.events = []

        def publish(self, event):
            self.events.append(event)

    collector = _Collector()
    interlock = PayloadInterlock(publisher=collector)
    interlock.mark_payload_2_released()

    assert not any(e.code == "INTERLOCK_VIOLATION_BLOCKED" for e in collector.events)
    assert any(e.code == "PAYLOAD_2_RELEASED" for e in collector.events)
