"""PHASE 0 (Mimari Freeze): soyut backend interface'i.

PayloadBackend, Real (real_payload_backend.py, PHASE 4) ve Gazebo
(gazebo_payload_backend.py, PHASE 5) tarafından implement edilecek tek
sözleşmedir. PayloadManager ve HookBehaviourModel SADECE bu interface'i
görür -- hangi somut backend'in bağlı olduğunu hiçbir zaman bilmezler
(dependency injection, bkz. payload_manager.py).

İki metod ailesi var:
  * Action primitifleri (async, I/O yapar): deploy/await_capture/grapple/
    retract/lower_for_release/release/stow -- V33 SERVO2/SERVO3 komutlarının backend-noturl
    karşılığı. HİÇBİRİ timeout_s parametresi ALMAZ -- zaman aşımı
    yönetimi kasıtlı olarak burada değil, PayloadManager'da
    (asyncio.wait_for + payload_config.py'deki FLEX sabitleri ile)
    merkezileştirilmiştir. Backend sadece "işlem bitince True/False dön"
    sözleşmesini tutar; ne kadar sürdüğünü sınırlamak çağıranın işi.
  * Query primitifleri (sync, anlık/cache'lenmiş durum okur): is_deployed/
    is_in_capture_zone/has_captured/is_grappled/is_secured/has_released --
    PHASE 2'deki HookBehaviourModel bunları 1:1 sarmalar.

Bu dosyada hiçbir gerçek implementasyon YOKTUR -- sadece imza + sözleşme.
"""
from abc import ABC, abstractmethod


class PayloadBackend(ABC):
    """Real ve Gazebo backend'lerinin ortak sözleşmesi. Üst seviye görev
    mantığı (PayloadManager) bu ABC'nin somut alt sınıfını hiçbir zaman
    isim/tip olarak bilmez -- constructor'da enjekte edilir."""

    # -- Yapilandirma (sync: I/O YOK, yalnizca hedef secimi) --------------

    @abstractmethod
    def select_payload(self, target_shape: str) -> None:
        """Sonraki komutların HANGİ payload üzerinde çalışacağını seçer.

        Parametre MISSION SEVİYESİ şekil adıdır ("MAVI_ALTIGEN" /
        "KIRMIZI_UCGEN") -- backend'e özgü bir model/kanal adı DEĞİL.
        Bu kasıtlı: üst katman backend detayı taşımaz (bkz. payload/
        paketinin bağımsızlık kuralı); çeviri backend'in kendi işidir.

        NEDEN VAR (2026-08-24): Görev 2'de bırakma sırası artık tespit
        sırasını takip ediyor, dolayısıyla Görev 3'ün alacağı payload
        derleme zamanında bilinmiyor -- 1st_mission Mavi Altıgen de
        Kırmızı Üçgen de olabilir. Hedef çalışma zamanında seçilmeli.

        Side-effect'siz sayılır: hiçbir RPC/servis çağrısı YAPMAZ, yalnızca
        sonraki komutların yöneleceği hedefi değiştirir. Davranış
        sözleşmesini (4 komut + get_state) DEĞİŞTİRMEZ."""
        raise NotImplementedError

    # -- Action primitifleri (async: gerçek donanım/sim I/O yapar) --------

    @abstractmethod
    async def deploy(self) -> bool:
        """Kancayı indir (V33: SERVO2_DOWN). Başarılıysa True."""
        raise NotImplementedError

    @abstractmethod
    async def await_capture(self) -> bool:
        """Payload'ın yakalanmasını bekler (V33: CATCH_PAYLOAD +
        TIMEOUT_CHECK). Yakalanırsa True. Zaman aşımı burada DEĞİL,
        PayloadManager'ın asyncio.wait_for sarmalayıcısında yönetilir."""
        raise NotImplementedError

    @abstractmethod
    async def grapple(self) -> bool:
        """Kavrama mekanizmasını aktive et (V33: SERVO3_GRAPPLE)."""
        raise NotImplementedError

    @abstractmethod
    async def retract(self) -> bool:
        """Kancayı payload ile birlikte geri çek (V33: SERVO2_REVERSE,
        1. kullanım)."""
        raise NotImplementedError

    @abstractmethod
    async def lower_for_release(self) -> bool:
        """Teslimat irtifasinda yuku asagi indir (V33: SERVO2_DOWN, 2. kullanim).

        V33 spesifikasyonu md.17/20 birakma dizisini uc adim olarak tanimlar:
        "45cm'de Servo2 yuku asagi indirir, Servo3 yuku birakir, Servo2 ters
        yonde calisip bos kutu/ip mekanizmasini yukari ceker."

        NEDEN deploy() DEGIL de AYRI BIR METOD (kasitli):
        Real tarafta ayni fiziksel komuttur (Servo2'yi DOWN degerine sur) ve
        ayni FLEX'leri paylasir -- tipki retract() ve stow()'un FLEX-18'i
        paylasmasi gibi. AMA Gazebo tarafta deploy() /hook/attach yayinlar;
        onu teslimat aninda yeniden cagirmak "yakala" komutunu tekrar
        gondermek olurdu ve yakalama envelope kapisini teslimat irtifasinda
        calistirirdi. Iki baglam ayni ABC metodunu PAYLASAMAZ.
        """
        raise NotImplementedError

    @abstractmethod
    async def release(self) -> bool:
        """Payload'ı serbest bırak (V33: SERVO3_RELEASE)."""
        raise NotImplementedError

    @abstractmethod
    async def stow(self) -> bool:
        """Bırakma sonrası mekanizmayı toparla (V33: SERVO2_REVERSE, 2./son
        kullanım)."""
        raise NotImplementedError

    # -- Query primitifleri (sync: anlık/cache'lenmiş durum okur) ---------

    @abstractmethod
    def is_deployed(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def is_in_capture_zone(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def has_captured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def is_grappled(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def is_secured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def has_released(self) -> bool:
        raise NotImplementedError
