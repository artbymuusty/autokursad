"""PHASE 4: RealPayloadBackend -- gerçek donanım (PX4 actuator) implementasyonu.

============================================================================
TODO(SAFETY) -- FİZİKSEL TAMAMLANMA DOĞRULANAMIYOR
============================================================================
await_capture() dahil hiçbir metod şu an fiziksel tamamlanmayı
doğrulayamıyor (telemetri/sensör yolu repoda yok). Backend "success"
dönüşü sadece komutun flight controller tarafından kabul edildiği anlamına
gelir, servo'nun fiziksel pozisyona ulaştığı anlamına GELMEZ. Gerçek uçuş
öncesi (Phase 17) bu boşluk mutlaka kapatılmalı -- sensör entegrasyonu
olmadan real flight'a GEÇİLMEMELİ.
============================================================================

TODO(ARCHITECTURE-DECISION) -- payload/ vs. IPayloadActuator
Bu payload/ paketi, real_system/real_payload_actuator.py
(IPayloadActuator) yolunun yerini almak üzere tasarlandı (supersede kararı
alındı). Bu dosyaya bu fazda dokunulmuyor/import edilmiyor. Gerçek
migrasyon (gorev3_pickup.py'nin payload_manager'a bağlanması) ayrı bir
MissionManager wiring fazında yapılacak.

--- BU FAZDA NE YAPILDI, NE YAPILMADI --------------------------------------

YAPILDI: 5 action primitifi (deploy/grapple/retract/release/stow) MAVSDK
Action.set_actuator(index, value) RPC'sine bağlandı. Her biri:
  * önce CALIBRATION GUARD çalıştırır (kendi FLEX index'i + FLEX değeri),
  * sonra TEK bir set_actuator() çağrısı yapar,
  * ActionError'ı yakalayıp False döner, başka hiçbir exception'ı yutmaz.

YAPILMADI (kasıtlı):
  * await_capture(): yakalamayı algılayacak sensör/telemetri yolu repoda
    YOK. Sahte bir "her zaman True" implementasyonu YAZILMADI -- bkz.
    metod docstring'i.
  * Query primitifleri (is_deployed/is_in_capture_zone/has_captured/
    is_grappled/is_secured/has_released): aynı nedenle NotImplementedError
    olarak bırakıldı. Bunları beslemek için gereken sensör yolu repoda
    yok; uydurma bir dönüş değeri, üst katmandaki state machine'i
    (PayloadManager.catch_box_up()'ın is_secured() kontrolü gibi) sessizce
    yanıltırdı.
  * sleep/timeout: backend içinde YOK. Zaman aşımı governance'ı
    PayloadManager'da merkezileştirilmiştir (asyncio.wait_for + FLEX
    sabitleri, bkz. payload_manager.py). Backend sadece RPC'nin kabul
    edilip edilmediğini raporlar.
  * MAVSDK bağlantısı: bu sınıf KURMAZ. `action` nesnesi (set_actuator
    metoduna sahip, tipik olarak mavsdk.System().action) constructor'da
    dışarıdan enjekte edilir.

--- "KOMUT KABUL EDİLDİ" != "FİZİKSEL POZİSYONA ULAŞILDI" ------------------

Bu ayrım bu dosyanın en kritik sözleşmesidir ve her action metodunun
docstring'inde tekrarlanır:

  True  = set_actuator() RPC'si flight controller tarafından KABUL EDİLDİ
          (PX4 komutu aldı ve ACK'ledi).
  False = RPC reddedildi (ActionError).

True dönüşü servonun hedef konuma ulaştığını, kancanın gerçekten indiğini,
kavramanın gerçekten tuttuğunu veya payload'ın gerçekten bırakıldığını
GÖSTERMEZ. Bu doğrulama sensör entegrasyonu gerektirir (bkz. yukarıdaki
TODO(SAFETY)).
"""
import logging

from mavsdk.action import ActionError

from payload import payload_config
from payload.backends.payload_backend import PayloadBackend
from payload.errors import PayloadCalibrationError

logger = logging.getLogger(__name__)


# NOT: PayloadCalibrationError PHASE 5 ADIM 0'da payload/errors.py'ye taşındı
# (Gazebo backend'i de aynı hata tipini paylaşıyor). Yukarıdaki import ile
# bu modülden de erişilebilir kalır -- davranış değişmedi, sadece konum.


# RealPayloadBackend'in HERHANGI bir komut gonderebilmesi icin kalibre
# olmasi gereken FLEX'ler -- CALIBRATION GUARD haritasinin (deploy/grapple/
# retract/release/stow) birlesimi.
REQUIRED_FLEX_NAMES = (
    "FLEX_14_SERVO2_ACTUATOR_INDEX",
    "FLEX_15_SERVO3_ACTUATOR_INDEX",
    "FLEX_16_SERVO2_DOWN_VALUE",
    "FLEX_17_SERVO3_GRAPPLE_VALUE",
    "FLEX_18_SERVO2_REVERSE_VALUE",
    "FLEX_19_SERVO3_RELEASE_VALUE",
)


def uncalibrated_flex_names():
    """Halen TBD (None) olan FLEX'lerin adlari. Cagri aninda okunur."""
    return [name for name in REQUIRED_FLEX_NAMES
            if getattr(payload_config, name) is None]


def warn_if_uncalibrated(target_logger=None):
    """BOOT ANINDA cagrilir (composition root'ta, mission baslamadan).

    NEDEN BURADA VE NEDEN ERKEN: kalibrasyon eksikligi bugun ancak Gorev 3'un
    alma adiminda -- ucusun ortasinda, dakikalar sonra -- gorunur hale
    geliyordu. Bu fonksiyon ayni gercegi kalkistan once, log'un basinda
    soyler. Mission'i BLOKLAMAZ: ucus kalkabilir, Gorev 1/2 calisir; yalnizca
    Gorev 3'un payload adimlari duser (temiz sekilde, bkz.
    gorev3_pickup.py::_run_payload_pickup).

    Eksik FLEX listesini dondurur (bos liste = kalibre)."""
    missing = uncalibrated_flex_names()
    if missing:
        (target_logger or logger).warning(
            "Real Payload Backend kalibre edilmemis (FLEX-14..19 TBD) -- gercek "
            "Gorev 3 pickup/redrop BASARISIZ olacak. Eksik: %s. Kalibrasyon: "
            "payload_config.py'deki ilgili FLEX bloklarinin HOW TO CALIBRATE "
            "adimlari (Real icin tools/ altinda bench script'i HENUZ YOK -- "
            "Phase 16). Ucus BLOKLANMIYOR: Gorev 1/2 etkilenmez.",
            ", ".join(missing))
    return missing


class RealPayloadBackend(PayloadBackend):
    """Gerçek donanım backend'i: PayloadBackend sözleşmesini MAVSDK
    Action.set_actuator(index, value) üzerinden karşılar.

    Constructor MAVSDK bağlantısı KURMAZ -- `action` nesnesi dışarıdan
    enjekte edilir (dependency injection). Bu, backend'i mock'lanabilir
    kılar ve bağlantı yaşam döngüsünü (System(), connect(), health
    bekleme) bu sınıfın sorumluluğu olmaktan çıkarır.

    Servo -> FLEX haritası:
        Servo2 (kanca indirme/geri çekme) -> index: FLEX-14
            deploy()            -> değer: FLEX-16 (SERVO2_DOWN, 1. kullanım)
            lower_for_release() -> değer: FLEX-16 (SERVO2_DOWN, 2. kullanım)
            retract() -> değer: FLEX-18 (SERVO2_REVERSE, 1. kullanım)
            stow()    -> değer: FLEX-18 (SERVO2_REVERSE, 2./son kullanım)
        Servo3 (kavrama/bırakma) -> index: FLEX-15
            grapple() -> değer: FLEX-17 (SERVO3_GRAPPLE)
            release() -> değer: FLEX-19 (SERVO3_RELEASE)

    retract() ve stow() AYNI FLEX-18 değerini paylaşır -- aynı fiziksel
    servo komutunun iki kullanımı olduğu için kasıtlı (bkz.
    payload_config.py::FLEX-18 "PAYLAŞIM NOTU").
    """

    def __init__(self, action) -> None:
        """`action`: set_actuator(index, value) coroutine'ine sahip nesne
        (tipik olarak mavsdk.System().action). Bağlantının kurulmuş olması
        çağıranın sorumluluğudur."""
        self._action = action

    # -- Yapilandirma -----------------------------------------------------

    def select_payload(self, target_shape: str) -> None:
        """Gerçek donanımda KARŞILIĞI YOK -- belgelenmiş no-op.

        Tek kanca, tek mekanizma: Servo2/Servo3 komutları hangi payload'ın
        alındığına göre DEĞİŞMEZ. Hedef seçimi bir navigasyon/vision
        sorusudur, aktüatör sorusu değil.

        (Simetrik emsal: lower_for_release() Real'de gerçek, Gazebo'da
        no-op; bu metod tam tersi.)"""
        logger.info("[PAYLOAD/REAL] select_payload(%s): no-op -- servo komutlari "
                    "hedefe gore degismez.", target_shape)

    # -- Action primitifleri ---------------------------------------------

    async def deploy(self) -> bool:
        """Kancayı indir (V33: SERVO2_DOWN) -- Servo2'yi FLEX-16 değerine sür.

        CALIBRATION GUARD: FLEX-14 (index) + FLEX-16 (değer).

        Dönüş: True = set_actuator() RPC'si flight controller tarafından
        KABUL EDİLDİ. Kancanın fiziksel olarak indiği anlamına GELMEZ
        (bkz. modül başındaki TODO(SAFETY))."""
        return await self._set_actuator(
            "deploy",
            index_flex="FLEX_14_SERVO2_ACTUATOR_INDEX",
            value_flex="FLEX_16_SERVO2_DOWN_VALUE")

    async def await_capture(self) -> bool:
        """Payload'ın yakalanmasını bekler (V33: CATCH_PAYLOAD).

        IMPLEMENT EDİLMEDİ -- KASITLI. Yakalamayı algılayacak sensör/
        telemetri yolu (manyetik temas sensörü, kanca yük hücresi vb.)
        repoda mevcut değil. Bu metod set_actuator ile ifade edilemez:
        bir komut değil, bir GÖZLEMdir. Sahte bir "her zaman True"
        implementasyonu, üst katmanın CAPTURED state'ine hiç payload
        yakalamadan geçmesine yol açardı -- bu yüzden yazılmadı.

        Kapatmak için gereken: FLEX-01 (capture envelope) ve FLEX-03
        (manyetik doğrulama debounce) kalibrasyonu + sensör okuma yolu.
        Bkz. modül başındaki TODO(SAFETY)."""
        raise NotImplementedError(
            "TODO(SAFETY/PHASE-17): RealPayloadBackend.await_capture() -- yakalamayi "
            "dogrulayacak sensor/telemetri yolu repoda yok. Sahte implementasyon "
            "KASITLI OLARAK yazilmadi; FLEX-01/FLEX-03 kalibrasyonu ve sensor "
            "entegrasyonu gerekli.")

    async def grapple(self) -> bool:
        """Kavrama mekanizmasını aktive et (V33: SERVO3_GRAPPLE) -- Servo3'ü
        FLEX-17 değerine sür.

        CALIBRATION GUARD: FLEX-15 (index) + FLEX-17 (değer).

        Dönüş: True = RPC KABUL EDİLDİ. Kavramanın fiziksel olarak tuttuğu
        anlamına GELMEZ (bkz. modül başındaki TODO(SAFETY))."""
        return await self._set_actuator(
            "grapple",
            index_flex="FLEX_15_SERVO3_ACTUATOR_INDEX",
            value_flex="FLEX_17_SERVO3_GRAPPLE_VALUE")

    async def retract(self) -> bool:
        """Kancayı payload ile birlikte geri çek (V33: SERVO2_REVERSE,
        1. kullanım) -- Servo2'yi FLEX-18 değerine sür.

        CALIBRATION GUARD: FLEX-14 (index) + FLEX-18 (değer). FLEX-18
        stow() ile PAYLAŞILIR -- aynı fiziksel komut.

        Dönüş: True = RPC KABUL EDİLDİ. Kancanın fiziksel olarak toplandığı
        veya payload'ın güvenceye alındığı anlamına GELMEZ (bkz. modül
        başındaki TODO(SAFETY)); PayloadManager.catch_box_up() bunun için
        ayrıca is_secured() sorar -- ki o da bu backend'de henüz
        NotImplementedError'dır."""
        return await self._set_actuator(
            "retract",
            index_flex="FLEX_14_SERVO2_ACTUATOR_INDEX",
            value_flex="FLEX_18_SERVO2_REVERSE_VALUE")

    async def lower_for_release(self) -> bool:
        """Teslimat irtifasinda yuku indir (V33: SERVO2_DOWN, 2. kullanim) --
        Servo2'yi FLEX-16 degerine sur.

        CALIBRATION GUARD: FLEX-14 (index) + FLEX-16 (deger) -- deploy() ile
        AYNI cift. Paylasim kasitli: fiziksel olarak tek bir servo hedef
        konumu var, iki kopya kalibrasyonda birbirinden sapabilirdi
        (FLEX-18'in retract/stow arasinda paylasilmasiyla ayni gerekce).

        Donus: True = RPC KABUL EDILDI. Yukun fiziksel olarak indigi
        anlamina GELMEZ (bkz. modul basindaki TODO(SAFETY))."""
        return await self._set_actuator(
            "lower_for_release",
            index_flex="FLEX_14_SERVO2_ACTUATOR_INDEX",
            value_flex="FLEX_16_SERVO2_DOWN_VALUE")

    async def release(self) -> bool:
        """Payload'ı serbest bırak (V33: SERVO3_RELEASE) -- Servo3'ü FLEX-19
        değerine sür.

        CALIBRATION GUARD: FLEX-15 (index) + FLEX-19 (değer).

        Dönüş: True = RPC KABUL EDİLDİ. Payload'ın fiziksel olarak ayrıldığı
        anlamına GELMEZ (bkz. modül başındaki TODO(SAFETY))."""
        return await self._set_actuator(
            "release",
            index_flex="FLEX_15_SERVO3_ACTUATOR_INDEX",
            value_flex="FLEX_19_SERVO3_RELEASE_VALUE")

    async def stow(self) -> bool:
        """Bırakma sonrası mekanizmayı toparla (V33: SERVO2_REVERSE, 2./son
        kullanım) -- Servo2'yi FLEX-18 değerine sür.

        CALIBRATION GUARD: FLEX-14 (index) + FLEX-18 (değer). FLEX-18
        retract() ile PAYLAŞILIR -- aynı fiziksel komut, farklı kullanım
        (retract yüklü, stow yüksüz).

        Dönüş: True = RPC KABUL EDİLDİ. Mekanizmanın fiziksel olarak
        toplandığı anlamına GELMEZ (bkz. modül başındaki TODO(SAFETY));
        False dönüşü PayloadManager'da STOW_FAILED terminal state'ini
        tetikler (bkz. payload_manager.py::release())."""
        return await self._set_actuator(
            "stow",
            index_flex="FLEX_14_SERVO2_ACTUATOR_INDEX",
            value_flex="FLEX_18_SERVO2_REVERSE_VALUE")

    # -- Query primitifleri (hepsi KASITLI OLARAK implement edilmedi) -----
    #
    # Bunları besleyecek sensör/telemetri yolu repoda YOK. Sahte bir dönüş
    # değeri (örn. hep True) üst katmanı sessizce yanıltırdı -- özellikle
    # PayloadManager.catch_box_up() is_secured()'a bakıp SECURED'a geçtiği
    # için, uydurma bir True "payload takılı" yanılsaması yaratırdı.
    # Bkz. modül başındaki TODO(SAFETY).

    def is_deployed(self) -> bool:
        raise NotImplementedError(self._no_sensor_msg("is_deployed"))

    def is_in_capture_zone(self) -> bool:
        raise NotImplementedError(self._no_sensor_msg("is_in_capture_zone"))

    def has_captured(self) -> bool:
        raise NotImplementedError(self._no_sensor_msg("has_captured"))

    def is_grappled(self) -> bool:
        raise NotImplementedError(self._no_sensor_msg("is_grappled"))

    def is_secured(self) -> bool:
        raise NotImplementedError(self._no_sensor_msg("is_secured"))

    def has_released(self) -> bool:
        raise NotImplementedError(self._no_sensor_msg("has_released"))

    # -- Yardımcılar ------------------------------------------------------

    @staticmethod
    def _no_sensor_msg(method_name: str) -> str:
        return (f"TODO(SAFETY/PHASE-17): RealPayloadBackend.{method_name}() -- besleyecek "
                f"sensor/telemetri yolu repoda yok. Sahte implementasyon KASITLI OLARAK "
                f"yazilmadi.")

    async def _set_actuator(self, method_name: str, index_flex: str, value_flex: str) -> bool:
        """CALIBRATION GUARD + tek set_actuator() RPC çağrısı.

        FLEX değerleri modül attribute'u olarak ÇAĞRI ANINDA okunur (import
        anında kopyalanmaz) -- böylece kalibrasyon sonrası payload_config
        güncellemesi (ve testlerdeki monkeypatch) anında etkili olur.

        Dönüş sözleşmesi: True = RPC kabul edildi, False = ActionError ile
        reddedildi. ActionError DIŞINDAKİ hiçbir exception yutulmaz --
        PayloadManager'ın "backend hatasını mission hatasıyla karıştırma"
        kuralıyla tutarlı (bkz. payload_manager.py::_run_with_timeout)."""
        index = self._require_calibrated(method_name, index_flex)
        value = self._require_calibrated(method_name, value_flex)

        logger.info("[PAYLOAD/REAL] %s -> set_actuator(index=%s, value=%s)",
                    method_name, index, value)
        try:
            await self._action.set_actuator(index, value)
        except ActionError as exc:
            logger.error("[PAYLOAD/REAL] %s -> set_actuator(index=%s, value=%s) REDDEDILDI: %s",
                         method_name, index, value, exc)
            return False
        # DIKKAT: buradaki True sadece "komut kabul edildi" demektir --
        # servo'nun fiziksel pozisyona ulastigi DOGRULANMADI.
        return True

    @staticmethod
    def _require_calibrated(method_name: str, flex_name: str):
        """CALIBRATION GUARD: tek bir FLEX sabitini oku, TBD (None) ise
        PayloadCalibrationError fırlat. set_actuator ÇAĞRILMADAN önce
        çalışır -- kalibre edilmemiş sistemde donanıma komut gitmez."""
        value = getattr(payload_config, flex_name)
        if value is None:
            raise PayloadCalibrationError(
                f"RealPayloadBackend.{method_name}(): {flex_name} kalibre edilmedi (TBD/None). "
                f"payload_config.py icindeki ilgili FLEX blogunun 'HOW TO CALIBRATE' "
                f"adimlarini uygulayip degeri girin. Kalibre edilmemis bir actuator "
                f"index/degeri ile donanima komut GONDERILMEDI.")
        return value
