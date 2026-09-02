"""
BU DOSYA, PROJEDE GERÇEK DONANIM KOMUTUNUN YAZILACAĞI TEK YERDİR. core/ ve gz_system/
içinde bu tarz TODO veya donanım-özel kod OLMAMALIDIR. Fiziksel testler tamamlandığında
yalnızca bu dosyadaki dört metod güncellenecektir; core/ ve gz_system/ değişmeyecektir.

DÖRT SERVO NOKTASI (denetim B8, 2026-09-02 -- hepsi aynı ayrıntıya eşitlendi):

  | İşaret               | Metot                            | Görev                    | Kanal (real_system.yaml)          |
  |----------------------|----------------------------------|--------------------------|-----------------------------------|
  | FIRST MISSION SERVO  | release_payload_at_mavi_altigen  | Görev 2, 1. bırakma      | actuator.mavi_altigen_release_channel |
  | SECOND MISSION SERVO | release_payload_at_kirmizi_ucgen | Görev 2, 2. bırakma      | actuator.kirmizi_ucgen_release_channel |
  | THIRD MISSION SERVO  | activate_pickup_mechanism        | Görev 3 Faz 1 (alma)     | actuator.pickup_channel           |
  | GRAB SERVO           | activate_drop_mechanism          | Görev 3 Faz 3 (bırakma)  | actuator.drop_channel             |

MANUEL AYAR İÇİN: her metodun içindeki `# AYAR:` bloğu açıyı, süreyi ve kanalı
tek yerde toplar. Bir noktayı ayarlamak için yalnızca o bloğa bakman yeterli.
Değerlerin `None`/TODO olanları HENÜZ ÖLÇÜLMEDİ -- fiziksel test sırasında
doldurulacak; uydurulmuş bir açı yazmak, yanlış bir açıyla uçmaktan farksızdır.

SIMÜLASYON KARŞILIĞI: gz_system/gz_payload_actuator.py aynı dört işareti taşır
(satır 552, 557, 1249, 1328) ve orada TODO YOKTUR -- Gazebo DetachableJoint /
HookAttachSystem ile gerçek davranış vardır. Davranış farkı KASITLIDIR:
GZ'de fiziksel tetikleme simüle edilir, burada henüz hiç tetikleme yoktur.
"""

import asyncio
import logging
from core.interfaces.i_payload_actuator import IPayloadActuator

logger = logging.getLogger(__name__)

#: Her metottaki `await asyncio.sleep(...)` YER TUTUCUDUR -- gerçek servonun
#: hareket süresiyle değiştirilecek. Şu anki değer yalnızca "bir şey oldu"
#: hissi vermek içindir, ölçülmüş bir süre DEĞİLDİR.
_PLACEHOLDER_TRAVEL_S = 0.5


class RealPayloadActuator(IPayloadActuator):

    async def release_payload_at_mavi_altigen(self) -> bool:
        """Görev 2 Rapor Bölüm 12: servo 90° sağa, ardından 90° sola hareket ederek
        Mavi Altıgen'deki (RED payload) yükü bırakır."""
        logger.info("release_payload_at_mavi_altigen cagrildi")
        # FIRST MISSION SERVO
        # TODO[DONANIM]: Gerçek servo entegrasyonu
        # AYAR:
        #   Beklenen davranış : servo 90° SAĞA, ardından 90° SOLA (Görev 2 Rapor Bölüm 12)
        #   Açı               : +90° / -90°  (Bölüm 12'de tanımlı)
        #   Süre              : TODO -- servo datasheet'inden ya da bankoda ölçülecek
        #   Kanal             : real_system.yaml -> actuator.mavi_altigen_release_channel
        #   Önerilen kütüphane: pigpio / RPi.GPIO / PX4 AUX kanalı (MAVSDK Actuator Control)
        await asyncio.sleep(_PLACEHOLDER_TRAVEL_S)  # yer tutucu, gerçek servo süresiyle değişecek
        logger.warning("SIMULE edildi - gercek servo BAGLI DEGIL")
        return True

    async def release_payload_at_kirmizi_ucgen(self) -> bool:
        """Görev 2 Rapor Bölüm 12: İkinci yük bırakma mekanizması --
        Kırmızı Üçgen'e (BLUE payload)."""
        logger.info("release_payload_at_kirmizi_ucgen cagrildi")
        # SECOND MISSION SERVO
        # TODO[DONANIM]: Gerçek servo entegrasyonu
        # AYAR:
        #   Beklenen davranış : Bölüm 12'deki AYNI mekanizma, İKİNCİ servo üzerinde.
        #                       Renk eşlemesi kasıtlı: BLUE payload <-> Kırmızı Üçgen
        #                       (gz_payload_actuator.py'de "deliberate team assignment").
        #   Açı               : 1. nokta ile aynı beklenir (+90° / -90°) -- DONANIMDA DOĞRULA.
        #                       İki servo farklı monte edildiyse yön ters olabilir.
        #   Süre              : TODO -- 1. nokta ile aynı servo tipi ise aynı değer
        #   Kanal             : real_system.yaml -> actuator.kirmizi_ucgen_release_channel
        #   Önerilen kütüphane: pigpio / RPi.GPIO / PX4 AUX kanalı (MAVSDK Actuator Control)
        await asyncio.sleep(_PLACEHOLDER_TRAVEL_S)
        logger.warning("SIMULE edildi - gercek servo BAGLI DEGIL")
        return True

    async def activate_pickup_mechanism(self, altitude_m=None,
                                        deck_height_m=None, on_retry=None) -> bool:
        """Görev 3 Rapor Bölüm 5, Adım 6: Yük alma mekanizmasını aktifleştirir.

        İMZA DÜZELTMESİ (denetim B2, 2026-09-02): bu metot `(self)` idi, ama
        core/mission/gorev3_pickup.py:906 onu
        `activate_pickup_mechanism(altitude_m=..., on_retry=...)` diye çağırıyor
        ve IPayloadActuator ile gz_payload_actuator.py:1238 zaten üç argümanı da
        taşıyor. Gerçek uçuşta Görev 3 Faz 1 servo tetikleme anına ulaştığında
        TypeError ile düşerdi -- SİMÜLASYONDA GÖRÜNMEZ, çünkü orada
        GzPayloadActuator kullanılıyor."""
        logger.info("activate_pickup_mechanism cagrildi (altitude_m=%s deck_height_m=%s)",
                    altitude_m, deck_height_m)
        # THIRD MISSION SERVO
        # TODO[DONANIM]: Gerçek servo entegrasyonu
        # AYAR:
        #   Beklenen davranış : Operatör tarifi (2026-08-21) -- kanca yükün hizasına
        #                       iner, ucundaki MIKNATIS yuvaya oturur, SONRA kanca
        #                       içindeki servo DÖNÜP KİLİTLER. Yani bu bir kilitleme
        #                       dönüşüdür, 1./2. noktadaki aç-kapa değildir.
        #   Açı               : TODO -- kilit açısı (kanca CAD'inden ya da bankoda ölçülecek)
        #   Süre              : TODO -- kilidin oturması için gereken süre
        #   Kanal             : real_system.yaml -> actuator.pickup_channel
        #   Önerilen kütüphane: pigpio / RPi.GPIO / PX4 AUX kanalı (MAVSDK Actuator Control)
        #
        #   ARGÜMANLAR (gz_payload_actuator.hook_payout_m ile aynı sözleşme):
        #     altitude_m    -- tetikleme anındaki AGL irtifa; vinç salımı bundan türetilir
        #     deck_height_m -- alınacak yükün güverte yüksekliği
        #     on_retry      -- her yeniden denemeden ÖNCE çağrılır (araç yeniden konumlansın).
        #                      GZ tarafı HOOK_PICKUP_ATTEMPTS kez dener; gerçek
        #                      implementasyon da temas doğrulanamazsa denemeli.
        #   Üçü de OPSİYONEL: yok sayan bir aktüatör hâlâ geçerlidir (IPayloadActuator).
        await asyncio.sleep(_PLACEHOLDER_TRAVEL_S)
        logger.warning("SIMULE edildi - gercek servo BAGLI DEGIL")
        return True

    async def activate_drop_mechanism(self) -> bool:
        """Görev 3 Rapor Bölüm 7, Adım 5: Taşınan yükü bırakır."""
        logger.info("activate_drop_mechanism cagrildi")
        # GRAB SERVO
        # TODO[DONANIM]: Gerçek servo entegrasyonu
        # AYAR:
        #   Beklenen davranış : 3. noktanın TERSİ -- kanca servosu GERİ DÖNER ve
        #                       kilidi açar, yük düşer ("servo aciliyor -- yuk
        #                       birakiliyor", gz_payload_actuator.py:1330).
        #   Açı               : TODO -- 3. noktadaki kilit açısının tersi
        #   Süre              : TODO -- kilidin tam açılması için gereken süre
        #   Kanal             : real_system.yaml -> actuator.drop_channel
        #                       (3. nokta ile AYNI fiziksel servo olabilir; öyleyse
        #                        iki alana da aynı numara yazılır)
        #   Önerilen kütüphane: pigpio / RPi.GPIO / PX4 AUX kanalı (MAVSDK Actuator Control)
        #
        #   DİKKAT (GZ tarafından öğrenilen, 2026-08-23): KOMUTUN döndüğünü değil
        #   SONUCUN gerçekleştiğini doğrula. Önceki GZ sürümü yalnızca komutun
        #   hatasız çalıştığına bakıyordu ve "yük bırakıldı" yazıyordu -- yük hâlâ
        #   kancadaydı ve dönüş uçuşu boyunca araçla birlikte gitti.
        await asyncio.sleep(_PLACEHOLDER_TRAVEL_S)
        logger.warning("SIMULE edildi - gercek servo BAGLI DEGIL")
        return True
