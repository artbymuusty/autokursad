"""
BU DOSYA, PROJEDE GERÇEK DONANIM KOMUTUNUN YAZILACAĞI TEK YERDİR. core/ ve gz_system/
içinde bu tarz TODO veya donanım-özel kod OLMAMALIDIR. Fiziksel testler tamamlandığında
yalnızca bu dosyadaki dört metod güncellenecektir; core/ ve gz_system/ değişmeyecektir.

DÖRT SERVO NOKTASI (denetim B8, 2026-09-02 -- hepsi aynı ayrıntıya eşitlendi):

  | İşaret               | Metot                            | Görev                    | Kanal (real_system.yaml)          |
  |----------------------|----------------------------------|--------------------------|-----------------------------------|
  | FIRST MISSION SERVO  | release_payload_at_mavi_altigen  | Görev 2, 1. bırakma      | actuator.mavi_altigen_release_channel |
  | SECOND MISSION SERVO | release_payload_at_kirmizi_ucgen | Görev 2, 2. bırakma      | actuator.kirmizi_ucgen_release_channel |
  | SERVO2 (VİNÇ)        | activate_pickup_mechanism (1/2)  | Görev 3 Faz 1, indirme   | actuator.winch_channel            |
  | SERVO3 (KAVRAMA)     | activate_pickup_mechanism (2/2)  | Görev 3 Faz 1, kavrama   | actuator.grip_channel             |
  | SERVO3 (KAVRAMA)     | activate_drop_mechanism          | Görev 3 Faz 3, açma      | actuator.grip_channel             |

GÖREV K / C (2026-09-04): eski THIRD MISSION SERVO tek noktası ikiye bölündü.
Operatör tarifi kancayı indiren mekanizmayı (servo2) ile kanca içindeki
kavrama kollarını (servo3) ayrı servolar olarak tanımlıyor. Eski
`pickup_channel` / `drop_channel` anahtarları yaml'da ESKİ olarak duruyor;
kod hiçbir zaman okumadığı için bölme davranışı kırmadı.

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
        #   Açı               : GOREV3_SERVO1_ANGLES_DEG (config -- HARDCODE DEĞİL)
        #                       sol -90° | orta 0° | sağ +90°   (operatör, 2026-09-05)
        #                       Bölüm 12'deki "+90 / -90" ile aynı mekanizma; buradaki
        #                       üçüncü konum (orta = 0°) dinlenme/nötr konumdur.
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

    #: GOREV I / O-A: alinacak yukun rengi. Gorev 3 alma fazi bildirir.
    _pickup_color: str = "red"

    def set_pickup_color(self, color: str) -> None:
        if color:
            self._pickup_color = color

    async def activate_pickup_mechanism(self, altitude_m=None,
                                        deck_height_m=None, on_retry=None,
                                        on_attract=None,
                                        extend_winch: bool = True) -> bool:
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
        # SERVO2 (VİNÇ) -- 1/2: kancayı aşağı bırak
        # TODO[DONANIM]: Gerçek servo entegrasyonu
        # AYAR:
        #   Beklenen davranış : 30 cm irtifaya inildiğinde kancayı yükün hizasına
        #                       kadar SARKIT; alma bitince yukarı ÇEK. GZ karşılığı
        #                       gz_payload_actuator.extend_winch_for / set_winch.
        #   Yön               : SOLA döner = SARKIT (salım artar) |
        #                       SAĞA döner = ÇEK (salım azalır)     (operatör, 2026-09-05)
        #                       Kod karşılığı: extend_winch_for (sarkıt) / set_winch(0) (çek).
        #                       Ö1 kuralı: alma penceresi boyunca salım YALNIZCA BÜYÜR.
        #   Açı/tur           : TODO -- salım uzunluğu (m) <-> servo turu dönüşümü.
        #                       ÖLÇÜLMEDİ: dişli oranı ve makara çapı bankoda ölçülecek.
        #   Süre              : TODO -- tam salım süresi (GZ'de eklem hız sınırı 0.5 m/s)
        #   Kanal             : real_system.yaml -> actuator.winch_channel
        #
        # SERVO3 (KAVRAMA) -- 2/2: mıknatıs oturunca kolları KAPAT
        # AYAR:
        #   Beklenen davranış : Mıknatıs (GÖREV K / D) kancayı yuvanın ağzına çeker;
        #                       kilitlenme kapıları + dwell geçilince kanca içindeki
        #                       kollar KAPANIR ve yükü İÇERİDEN kavrar. Manyetik
        #                       tutuş konumlandırır, mekanik tutuşu bu servo sağlar.
        #   Açı               : GOREV3_SERVO3_CLOSED_DEG = 0°  (config -- HARDCODE DEĞİL)
        #                       Tam süpürme GOREV3_SERVO3_SWEEP_DEG = 180°, SOLDAN SAĞA
        #                       (operatör, 2026-09-05). 0° = kapalı/kavrıyor,
        #                       180° = tam açık.
        #   Zamanlama         : dwell (MAGNET_DWELL_S) DOLDUKTAN SONRA
        #                       GOREV3_SERVO3_POST_LOCK_DELAY_S kadar daha beklenir
        #                       ve o pencerede kapılar örneklenmeye DEVAM eder
        #                       (GÖREV N/A). Kapılar bozulursa kavrama YAPILMAZ.
        #   Süre              : TODO -- kolların kapanma süresi (bankoda ölçülecek)
        #   Kanal             : real_system.yaml -> actuator.grip_channel
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
        # SERVO3 (KAVRAMA) -- AÇMA yönü
        # TODO[DONANIM]: Gerçek servo entegrasyonu
        # AYAR:
        #   Beklenen davranış : Almanın TERSİ -- kavrama kolları AÇILIR ve yük
        #                       bırakılır ("servo aciliyor -- yuk birakiliyor").
        #                       ALMADAKİ İLE AYNI FİZİKSEL SERVO, ters yön.
        #   Açı               : GOREV3_SERVO3_OPEN_DEG = 180°  (config -- HARDCODE DEĞİL)
        #                       Kapanma açısının (0°) tam tersi; süpürme
        #                       GOREV3_SERVO3_SWEEP_DEG = 180°, SOLDAN SAĞA.
        #   Süre              : TODO -- kolların tam açılma süresi (bankoda ölçülecek)
        #   Kanal             : real_system.yaml -> actuator.grip_channel
        #   Önerilen kütüphane: pigpio / RPi.GPIO / PX4 AUX kanalı (MAVSDK Actuator Control)
        #
        #   DİKKAT (GZ tarafından öğrenilen, 2026-08-23): KOMUTUN döndüğünü değil
        #   SONUCUN gerçekleştiğini doğrula. Önceki GZ sürümü yalnızca komutun
        #   hatasız çalıştığına bakıyordu ve "yük bırakıldı" yazıyordu -- yük hâlâ
        #   kancadaydı ve dönüş uçuşu boyunca araçla birlikte gitti.
        await asyncio.sleep(_PLACEHOLDER_TRAVEL_S)
        logger.warning("SIMULE edildi - gercek servo BAGLI DEGIL")
        return True
