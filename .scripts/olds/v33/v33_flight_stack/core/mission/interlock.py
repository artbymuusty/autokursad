"""İki payload bırakma görevinin muhasebesi.

TARİHÇE -- SIRA KURALI KALDIRILDI (2026-08-24, operatör kararı):
Bu sınıf başlangıçta "Görev 2 Rapor Bölüm 11.1'deki EN KRİTİK kural"ı
uyguluyordu: Kırmızı Üçgen'in yükü, Mavi Altıgen'inki bırakılmadan
KESİNLİKLE bırakılamaz. Proje sahibi 2026-08-24'te bu kuralın artık
geçerli olmadığını / yanlış anlaşıldığını bildirdi ve V33 spec'inin
md.6/11'de tarif ettiği DİNAMİK davranışa geçildi: hangi şekil önce
tespit edilip kilitlenirse onun yükü önce bırakılır.

Bu yüzden mark_payload_2_released() artık RuntimeError FIRLATMAZ ve
can_release_payload_2() her zaman True döner (geriye dönük uyumluluk
için imza korundu, bkz. kendi docstring'i).

KORUNAN: iki payload'ın bırakılıp bırakılmadığının MUHASEBESİ. Görev 3'ün
ön koşulu (gorev3_precondition.py) ve dashboard event'leri buna bağlı.
Değişen yalnızca SIRA ZORUNLULUĞU."""
from core.telemetry.event_bus import NULL_PUBLISHER, EventPublisher
from core.telemetry.events import Category, Event, Severity


class PayloadInterlock:
    def __init__(self, publisher: EventPublisher = NULL_PUBLISHER):
        self._payload_1_released: bool = False   # Mavi Altıgen
        self._payload_2_released: bool = False   # Kırmızı Üçgen
        self.publisher = publisher

    def mark_payload_1_released(self) -> None:
        """Mavi Altıgen'e yük bırakıldığında çağrılır. Artık ikinci de
        olabilir -- "payload_1" adı Mavi Altıgen'i tanımlar, SIRAYI
        değil (2026-08-24 sonrası)."""
        self._payload_1_released = True
        self.publisher.publish(Event(
            code="PAYLOAD_1_RELEASED", subsystem="PayloadInterlock", category=Category.PAYLOAD,
            message="payload 1 (MAVI_ALTIGEN) released",
            data={"payload_1_released": True, "payload_2_released": self._payload_2_released},
        ))

    def can_release_payload_2(self) -> bool:
        """ARTIK HER ZAMAN True (2026-08-24: sıra kuralı kaldırıldı).

        İmza ve isim KASITLI olarak korundu: çağıranları ve testleri tek
        seferde kırmamak için. Yeni kodun buna dayanmasına gerek yok --
        bırakma sırası artık tespit sırasını takip eder."""
        return True

    def mark_payload_2_released(self) -> None:
        """Kırmızı Üçgen'e yük bırakıldığında çağrılır. ÖNKOŞUL YOK
        (2026-08-24): sıra kuralı kaldırıldı, bu ilk de olabilir."""
        # 2026-08-24: burada eskiden payload_1_released False ise
        # INTERLOCK_VIOLATION_BLOCKED yayinlanip RuntimeError firlatiliyordu.
        # Sira kurali kaldirildigi icin bu guard SILINDI -- Kirmizi Ucgen
        # once tespit edilirse yuku once birakilir ve bu artik bir ihlal
        # DEGIL, beklenen davranistir.
        self._payload_2_released = True
        self.publisher.publish(Event(
            code="PAYLOAD_2_RELEASED", subsystem="PayloadInterlock", category=Category.PAYLOAD,
            message="payload 2 (KIRMIZI_UCGEN) released",
            data={"payload_1_released": True, "payload_2_released": True},
        ))

    def both_released(self) -> bool:
        return self._payload_1_released and self._payload_2_released

    @property
    def payload_1_released(self) -> bool:
        return self._payload_1_released

    @property
    def payload_2_released(self) -> bool:
        return self._payload_2_released
