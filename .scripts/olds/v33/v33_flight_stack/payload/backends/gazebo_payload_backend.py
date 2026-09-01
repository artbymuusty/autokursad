"""PHASE 5: GazeboPayloadBackend -- HookAttachSystem'i SARMALAYAN implementasyon.

============================================================================
TODO(SAFETY) -- SİMÜLASYON SADAKATİ SINIRLI, GERÇEK UÇUŞ KANITI DEĞİLDİR
============================================================================
Bu backend'in "başarılı" dönüşleri Gazebo'daki bir fixed joint'in varlığını
yansıtır -- gerçek bir kanca/mıknatıs mekanizmasının çalıştığını GÖSTERMEZ.
HookAttachSystem base_link'i payload'ın link'ine doğrudan "fixed" joint ile
kaynaklar (HookAttachSystem.cc:124); ne ip, ne makara, ne mıknatıs, ne de
kavrama kolu modellenmiştir. Bu paketin Gazebo yolunda geçmesi, Real yolu
için hiçbir şey kanıtlamaz (bkz. real_payload_backend.py TODO(SAFETY)).
============================================================================

TODO(ARCHITECTURE-DECISION) -- payload/ vs. gz_system/
Bu payload/ paketi, gz_system/gz_payload_actuator.py (IPayloadActuator)
yolunun yerini almak üzere tasarlandı (supersede kararı alındı, bkz.
payload_config.py). Bu dosya gz_payload_actuator.py'yi import ETMEZ ve ona
DOKUNMAZ; onun /hook/attach, /hook/detach, /hook/state kullanımını bağımsız
olarak yeniden ifade eder. Gerçek migrasyon ayrı bir MissionManager wiring
fazında yapılacak.

--- SARMALANAN GERÇEK ARAYÜZ (HookAttachSystem.cc:62-64) -------------------

HookAttachSystem bir SERVİS DEĞİL, üç TOPIC sunar. (PHASE 0 stub'ının
docstring'i "servis arayüzü" diyordu -- yanlıştı, düzeltildi.)

    /hook/attach   publish    gz.msgs.StringMsg   data = child MODEL adı
    /hook/detach   publish    gz.msgs.Boolean     data: true (false no-op)
    /hook/state    subscribe  gz.msgs.Boolean     joint GERÇEKTEN oluştu/kalktı

/hook/state, plugin'in tek ground-truth yayınıdır: PublishState(true) ancak
CreateEntity() + CreateComponent(DetachableJoint) çalıştıktan SONRA çağrılır
(HookAttachSystem.cc:122-127). Ama üç kritik özelliği vardır ve bu backend
bunların hepsini varsayar, hiçbirini düzeltmeye çalışmaz:
  * LATCH'SİZ ve geçiş başına TEK KEZ yayınlanır (:64 -- AdvertiseMessage
    Options yok). Geç bağlanan bir abone hiçbir zaman göremez.
  * BAŞARISIZLIKTA HİÇ YAYINLANMAZ. Çözülemeyen bir model adı sessizce
    sonsuza kadar yeniden denenir (:119-120, çıplak return).
  * Model adı ve zaman damgası TAŞIMAZ (:154-159).

--- BU FAZDA ALINAN KARARLAR (kullanıcı onayı, 2026-08-23) -----------------

KARAR 1 -- Sıralama (Seçenek A): Gazebo'nun tek dizisi
[attach komutu] -> [state=true]'dur; tetikleme gözlemden ÖNCE gelmek
zorundadır. ABC ise grapple()'ı await_capture()'dan SONRA koyar. Bu yüzden:
    deploy()        -> /hook/attach yayınlar (TETİKLEME)
    await_capture() -> /hook/state gözler   (SAF GÖZLEM, ABC'nin kendi
                       tanımına sadık: "bir komut değil, bir GÖZLEMdir")
    grapple()       -> belgelenmiş no-op
Böylece tetikle-sonra-gözle sırası korunur ve deploy() gerçek bir karşılık
kazanır.

KARAR 2 -- Yakınlık kapısı (FLEX-20): HookAttachSystem HİÇBİR mesafe
kontrolü yapmaz (232 satırda tek bir Pose okuması yok; kendi yorumuna göre
temas testi ÇAĞIRANA aittir, :33-35). Bu kapı olmasa deploy() aracı
payload'dan 50 m uzaktayken de kaynaklar ve catch_box_down() gerçekleşmemiş
bir yakalamayı başarılı raporlardı. Kapı FLEX-20 ile guard edilir --
FLEX-01 ile KASITLI OLARAK ayrı (gerekçe payload_config.py FLEX-20'de).

KARAR 3 -- Karşılığı olmayan metodlar (grapple/retract/stow): belgelenmiş
no-op, True döner. "Simülasyonda bu serbestlik derecesi yok" DOĞRU bir
ifadedir -- uydurulmuş bir sensör okuması değil. NotImplementedError
seçilseydi Gazebo yolu tamamen kullanılamaz olurdu: PayloadManager sadece
asyncio.TimeoutError yakalar (payload_manager.py::_run_with_timeout), yani
ilk çağrıda görev patlardı.

KARAR 4 -- Somut client YOK: bu faz yalnızca protokolü tanımlar (aşağıya
bkz.), gerçek gz-transport/CLI client'ı wiring fazına bırakılır. Böylece
payload/ paketi gz_system'den bağımsız kalır.

--- ENJEKTE EDİLEN CLIENT PROTOKOLÜ ---------------------------------------

Constructor gerçek bağlantı KURMAZ; aşağıdaki duck-typed yüzeye sahip bir
nesne dışarıdan verilir:

    async publish_attach(model_name: str) -> bool
        /hook/attach'e StringMsg yayınlar. True = mesaj YAYINLANDI.
    async publish_detach() -> bool
        /hook/detach'e Boolean(true) yayınlar. True = mesaj YAYINLANDI.
    async wait_for_hook_state(expected: bool) -> bool
        /hook/state expected değerine ULAŞANA KADAR bekler. Zaman aşımı
        YOK -- PayloadManager'ın asyncio.wait_for'u iptal eder.
    hook_state() -> Optional[bool]
        Son görülen /hook/state. None = henüz hiç geçiş görülmedi.
    is_state_stream_ready() -> bool
        /hook/state aboneliği attach'ten ÖNCE kurulmuş mu.
    read_vehicle_payload_clearance() -> Optional[float]
        Aracın altı ile payload üstü arasındaki DİKEY AÇIKLIK (m).
        None = poz bilinmiyor. FLEX-20'nin kapıladığı büyüklük budur
        (2026-08-23 operatör kararı; 3B merkez-merkez mesafe DEĞİL -- o
        semantikle kapı üretim irtifasında hiç açılmıyordu, bkz.
        payload_config.py FLEX-20). Formül kasıtlı olarak burada DEĞİL,
        client tarafında tek bir yerdedir
        (gz_system/gz_hook_client.py::_vertical_clearance).

is_state_stream_ready() KOZMETİK DEĞİL: /hook/state latch'siz ve tek
seferliktir, plugin ise 2.2 ms'de kaynaklar (2026-08-20 gz log ölçümü);
buna karşılık taze bir abonelik ~2 s discovery ister. Aboneliği attach'ten
SONRA kurmak, gözlenecek tek mesajı yapısal olarak kaçırmak demektir --
joint fiziksel olarak oluşmuşken bile timeout alınır. Bu backend aboneliği
KENDİSİ kurmaz (yaşam döngüsü sahibi değildir), ama hazır olmadan attach
YAYINLAMAZ.
"""
import logging

from payload import payload_config
from payload.backends.payload_backend import PayloadBackend
from payload.errors import PayloadCalibrationError

logger = logging.getLogger(__name__)

# TODO(PHASE-15-PARITY): Gazebo'da retract()/stow() no-op olduğu
# için (joint 'fixed', re-pozisyonlama yok) payload, yakalandığı
# açıklıkta SONSUZA KADAR sarkık kalıyor -- retract sonrası
# "güvenceye alınmış/yaslanmış" pozisyon Gazebo'da TEMSİL
# EDİLEMİYOR. Phase 6 ölçümü: 0.30m açıklıkta payload aracın
# 0.41m altında asılı, tüm transport boyunca böyle kalıyor. Bu,
# FLEX-20'nin yanlış olduğu anlamına gelmez -- Gazebo'nun
# "capture" ile "secured" arasındaki gerçek dünya ayrımını
# temsil edemediği anlamına gelir. Phase 15 parity testinde Real
# backend'in FLEX-01+retract davranışıyla karşılaştırılırken bu
# fark ele alınmalı; muhtemel çözüm retract() çağrıldığında
# joint'i yeniden konumlandırmak (Gazebo backend'e yeni iş),
# config değeri değişikliği DEĞİL.

# TODO(PHASE-6): _require_calibrated() burada ve real_payload_backend.py'de
# neredeyse aynı. Ortak bir yardımcıya çıkarılabilir; bu fazda yapılmadı
# çünkü görev sınırları real_payload_backend.py'ye dokunmayı yasaklıyor
# (yalnızca PHASE 5 ADIM 0'daki import değişikliği izinliydi).


class GazeboPayloadBackend(PayloadBackend):
    """Gazebo simülasyon backend'i: PayloadBackend sözleşmesini
    HookAttachSystem'in üç topic'i üzerinden karşılar.

    Constructor gz-transport bağlantısı KURMAZ -- client dışarıdan enjekte
    edilir. Model adlarının VARSAYILANI YOKTUR: sessizce "payload_red"
    varsaymak, yanlış payload'a kaynaklanan bir görevi fark edilmez kılardı.
    """

    def __init__(self, client, payload_model_name: str, vehicle_model_name: str,
                 payload_models_by_shape: dict = None) -> None:
        """`client`: yukarıdaki protokolü karşılayan nesne.
        `payload_model_name`: /hook/attach'e gönderilecek child MODEL adı
        (ör. "payload_red") -- plugin bunu model adıyla arar, link adıyla
        değil (HookAttachSystem.cc:117).
        `vehicle_model_name`: yakınlık kapısında poz okunacak araç modeli.
        """
        if not payload_model_name:
            raise ValueError("payload_model_name zorunlu -- sessiz bir varsayilan "
                             "yanlis payload'a kaynaklanma riskidir.")
        if not vehicle_model_name:
            raise ValueError("vehicle_model_name zorunlu -- yakinlik kapisi poz okumasi "
                             "olmadan calisamaz.")
        self._client = client
        self._payload_model_name = payload_model_name
        self._vehicle_model_name = vehicle_model_name
        # {mission sekil adi: gazebo model adi}. Composition root'ta kurulur
        # (gz_system'deki SHAPE_TO_COLOR/PAYLOAD_MODEL'den) -- payload/ paketi
        # bu esleme hakkinda hicbir sey BILMEZ, yalnizca sozlugu alir.
        self._payload_models_by_shape = dict(payload_models_by_shape or {})

    # -- Yapilandirma -----------------------------------------------------

    def select_payload(self, target_shape: str) -> None:
        """Hedef şekli, enjekte edilen haritadan Gazebo model adına çevirir
        ve hem backend'i hem client'ı günceller.

        Client de güncellenmeli: read_vehicle_payload_clearance() ve
        publish_attach() varsayılanı client'ın kendi model adını kullanıyor;
        yalnızca backend'i güncellemek ikisini SESSİZCE ayrıştırırdı.

        HARİTA BOŞSA: uyarı loglanır ve constructor'da verilen model
        KORUNUR. Bu, haritanın hiç enjekte edilmediği (eski/test) yoldur --
        tek bir model yapılandırılmışsa yanlış payload riski yoktur.
        HARİTA DOLU AMA ŞEKİL BİLİNMİYORSA: KeyError yükselir. Burada
        sessiz bir varsayılana düşmek gerçek bir yanlış-payload riskidir."""
        if not self._payload_models_by_shape:
            logger.warning("[PAYLOAD/GZ] select_payload(%s): {sekil:model} haritasi "
                           "enjekte edilmemis -- mevcut model korunuyor (%s).",
                           target_shape, self._payload_model_name)
            return
        model = self._payload_models_by_shape[target_shape]
        self._payload_model_name = model
        setter = getattr(self._client, "set_payload_model_name", None)
        if setter is not None:
            setter(model)
        logger.info("[PAYLOAD/GZ] select_payload(%s) -> model=%s", target_shape, model)

    # -- Action primitifleri ---------------------------------------------

    async def deploy(self) -> bool:
        """V33 SERVO2_DOWN'ın Gazebo karşılığı: /hook/attach'e child model
        adını yayınlar (KARAR 1 -- tetikleme burada, gözlem await_capture'da).

        CALIBRATION GUARD: FLEX-20 (yakınlık envelope'u).

        Sırayla üç kapı: (1) FLEX-20 kalibre mi, (2) araç envelope içinde mi,
        (3) /hook/state aboneliği hazır mı. Üçü de geçilmeden simülasyona
        HİÇBİR mesaj gitmez.

        Dönüş: True = attach mesajı YAYINLANDI. Joint'in oluştuğu anlamına
        GELMEZ -- bunun kanıtı yalnızca await_capture()'ın gözlediği
        /hook/state'tir."""
        if not self.is_in_capture_zone():
            logger.error("[PAYLOAD/GZ] deploy(): arac yakalama envelope'u DISINDA -- "
                         "/hook/attach yayinlanmadi. HookAttachSystem mesafe kontrolu "
                         "YAPMAZ, bu kapi tek korumadir.")
            return False

        if not self._client.is_state_stream_ready():
            logger.error("[PAYLOAD/GZ] deploy(): /hook/state aboneligi hazir DEGIL -- "
                         "/hook/attach yayinlanmadi. Latch'siz ve tek seferlik olan "
                         "attach onayi kacirilirdi (joint olussa bile timeout alinirdi).")
            return False

        logger.info("[PAYLOAD/GZ] deploy() -> /hook/attach child_model=%s",
                    self._payload_model_name)
        return await self._client.publish_attach(self._payload_model_name)

    async def await_capture(self) -> bool:
        """/hook/state'in true olmasını bekler -- plugin'in joint'i GERÇEKTEN
        oluşturduğunda yayınladığı tek ground-truth sinyali
        (HookAttachSystem.cc:122-127).

        SAF GÖZLEM: hiçbir mesaj yayınlamaz (KARAR 1). Zaman aşımı burada
        YOK -- PayloadManager çağrıyı FLEX-06 ile sarmalar ve süresi dolunca
        bu coroutine'i iptal eder. Backend'de poll aralığı/sleep de yok:
        bekleme client'ın kendi abonelik olayına devredilmiştir."""
        return await self._client.wait_for_hook_state(True)

    async def grapple(self) -> bool:
        """Gazebo'da KARŞILIĞI YOK -- belgelenmiş no-op (KARAR 3).

        HookAttachSystem'de yakalama ve kavrama AYNI OLAYDIR: tek bir
        CreateComponent(DetachableJoint) çağrısı (HookAttachSystem.cc:123).
        Ayrı bir kavrama mekanizması modellenmemiştir, dolayısıyla
        aktive edilecek bir şey yoktur.

        True = "yapılacak bir şey yoktu", "kavrama yapıldı" DEĞİL."""
        logger.info("[PAYLOAD/GZ] grapple(): no-op -- Gazebo'da yakalama ve kavrama "
                    "ayni tek joint olayidir, ayrica aktive edilecek mekanizma yok.")
        return True

    async def retract(self) -> bool:
        """Gazebo'da KARŞILIĞI YOK -- belgelenmiş no-op (KARAR 3).

        Joint "fixed" tipiyle oluşturulur (HookAttachSystem.cc:124): payload
        zaten parent_link'e rijit olarak kaynaklıdır. Sarılacak ip, makara
        veya kat edilecek mesafe yoktur.

        True = "yapılacak bir şey yoktu", "geri çekildi" DEĞİL. Not:
        PayloadManager bu dönüşün ardından is_secured()'a bakar -- o da
        joint'in varlığını okur, yani gerçek doğrulama orada yapılır."""
        logger.info("[PAYLOAD/GZ] retract(): no-op -- joint 'fixed', payload zaten rijit "
                    "kaynakli; sarilacak ip/makara modellenmemis.")
        return True

    async def lower_for_release(self) -> bool:
        """Gazebo'da KARŞILIĞI YOK -- belgelenmiş no-op (KARAR 3 deseni).

        V33 md.17 teslimat dizisinin ilk adımı ("Servo2 yükü aşağı indirir")
        bir vinç/ip hareketidir. Gazebo'da joint "fixed" tipiyle oluşturulmuş
        (HookAttachSystem.cc:124) ve indirilecek bir mekanizma modellenmemiş
        -- retract()/stow() ile tamamen aynı gerekçe.

        deploy() BURADA ÇAĞRILMAZ (kritik): deploy() /hook/attach yayınlar,
        yani teslimat anında "yakala" komutunu yeniden göndermek olurdu ve
        yakalama envelope kapısını teslimat irtifasında çalıştırırdı.

        True = "yapılacak bir şey yoktu", "yük indirildi" DEĞİL."""
        logger.info("[PAYLOAD/GZ] lower_for_release(): no-op -- indirilecek vinç/ip "
                    "mekanizmasi modellenmemis (joint 'fixed').")
        return True

    async def release(self) -> bool:
        """V33 SERVO3_RELEASE'in Gazebo karşılığı: /hook/detach'e
        Boolean(data=true) yayınlar.

        Neden yalnızca true: plugin false'u sessizce yok sayar
        (HookAttachSystem.cc:150-151).

        KASITLI OLARAK is_state_stream_ready() KAPISI YOK -- deploy()'un
        aksine. Bırakma komutunu gözlemlenebilirlik yüzünden ENGELLEMEK,
        payload'ı araca takılı bırakmak demektir; bu, doğrulanamamış bir
        bırakmadan daha kötü bir sonuçtur. Doğrulama has_released()'a
        bırakılır.

        Dönüş: True = detach mesajı YAYINLANDI. Payload'ın fiziksel olarak
        ayrıldığı anlamına GELMEZ."""
        logger.info("[PAYLOAD/GZ] release() -> /hook/detach data=true")
        return await self._client.publish_detach()

    async def stow(self) -> bool:
        """Gazebo'da KARŞILIĞI YOK -- belgelenmiş no-op (KARAR 3).
        retract() ile aynı gerekçe: toplanacak bir mekanizma modellenmemiş.

        True = "yapılacak bir şey yoktu". Bu, PayloadManager'ın STOW_FAILED
        dallanmasının Gazebo'da hiçbir zaman tetiklenmeyeceği anlamına gelir
        -- sim'de toparlanamayacak bir mekanizma olmadığı için doğru."""
        logger.info("[PAYLOAD/GZ] stow(): no-op -- toplanacak mekanizma modellenmemis.")
        return True

    # -- Query primitifleri ----------------------------------------------

    def is_deployed(self) -> bool:
        """IMPLEMENT EDİLMEDİ -- KASITLI.

        Gazebo'da "kanca indirildi" diye bir kavram YOK: ne topic, ne
        component, ne de state. Eksik olan bir SAYI değil, kavramın kendisi
        -- bu yüzden FLEX ile çözülemez. Sahte bir dönüş, üst katmana
        modellenmemiş bir serbestlik derecesi varmış gibi gösterirdi."""
        raise NotImplementedError(
            "GazeboPayloadBackend.is_deployed(): Gazebo'da 'kanca indirildi' kavraminin "
            "karsiligi YOK (HookAttachSystem base_link'i dogrudan payload'a kaynakliyor; "
            "ip/makara/servo modellenmemis). Okunacak bir yol olmadigi icin sahte "
            "implementasyon KASITLI OLARAK yazilmadi.")

    def is_in_capture_zone(self) -> bool:
        """Araç ile payload arasındaki mesafeyi FLEX-20 envelope'u ile
        karşılaştırır -- GERÇEK implementasyon (client'ın poz okuma yolu
        üzerinden).

        CALIBRATION GUARD: FLEX-20.

        Bu, HookAttachSystem'de OLMAYAN kontroldür (KARAR 2). Mesafe
        bilinmiyorsa False döner -- "bilmiyorum" asla "yakınım" olarak
        okunmaz.

        FORMÜL BURADA YOK (kasıtlı): client'ın
        read_vehicle_payload_clearance()'ı çağrılır, o da gz_hook_client.py'deki
        TEK _vertical_clearance() fonksiyonuna iner -- iki bağımsız hesap
        oluşup formül değiştiğinde biri sessizce geride kalamasın diye.

        NOT: FLEX-09 (hook-to-payload montaj ofseti) burada KASITLI olarak
        kullanılmaz: o, gerçek donanımın mekanik montaj ofsetidir; Gazebo'da
        kanca gövdesi diye ayrı bir cisim yoktur."""
        envelope = self._require_calibrated(
            "is_in_capture_zone", "FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M")

        clearance = self._client.read_vehicle_payload_clearance()
        if clearance is None:
            logger.warning("[PAYLOAD/GZ] is_in_capture_zone(): aciklik bilinmiyor "
                           "(poz okunamadi) -- False donuluyor.")
            return False

        inside = clearance <= envelope
        logger.info("[PAYLOAD/GZ] is_in_capture_zone(): dikey aciklik=%.3f m, "
                    "envelope=%.3f m -> %s", clearance, envelope, inside)
        return inside

    # -- Kapali-dongu geri besleme (2026-08-26) ---------------------------
    def capture_gate_excess_m(self):
        """Aracin yakalama zarfindan NE KADAR yukarida oldugu (m), ya da None.

        NEDEN VAR (olculdu, 2026-08-26 -- 4 kosuluk enstrumante seri):
        CenteringController "yakinsadim" kararini PX4'un relative_altitude'una
        bakarak veriyor; is_in_capture_zone() ise Gazebo ground-truth model
        pozuna bakiyor. Iki referans arasindaki fark kosudan kosuya 0.02-0.29 m
        degisiyor ve HICBIR YERDE birbirine karsi dogrulanmiyor. Olculen
        basarisiz kosuda (mission_7bec65433788) PX4 0.340 m derken gercek
        irtifa 0.630 m'ydi: merkezleme bandinin tam ortasinda "tamam" dedi,
        kapi 0.574 m aciklikla -- HAKLI OLARAK -- reddetti ve faz aninda
        MISSION_FAILED'a dustu. Poz bayat DEGILDI (yas 0.98 ms), yani sorun
        gecikme degil, referans ikiligi.

        Bu metod o ikiligi gorev katmanina OLCU olarak verir: "hala ne kadar
        yukaridasin". Gorev katmani envelope sabitini BILMEZ -- o bilgi
        burada, backend'de kalir.

        SOZLESME -- ASLA YUKSELMEZ, "bilmiyorum" ASLA "yakinim" DEGILDIR:
          None  -> cevaplanamiyor (poz okunamadi, FLEX-20 kalibre degil).
                   Cagiran bu durumda hicbir sey yapmamali; davranis bu
                   metod eklenmeden onceki haliyle birebir ayni kalir.
          <= 0  -> zarfin icindeyiz.
          > 0   -> bu kadar metre fazla yuksekteyiz.

        REAL/DUAL YOLU ETKILENMEZ: bu metod PayloadBackend arayuzunde YOK,
        yalnizca bu sinifta tanimli. RealPayloadBackend'de bulunmadigi icin
        PayloadManager'in duck-typed passthrough'u None doner ve gorev
        katmanindaki dongu hic calismaz.
        """
        envelope = payload_config.FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M
        if envelope is None:
            return None
        try:
            clearance = self._client.read_vehicle_payload_clearance()
        except Exception as e:  # noqa: BLE001 -- olcum yolu gorev akisini bozamaz
            logger.info("[PAYLOAD/GZ] capture_gate_excess_m(): aciklik okunamadi: %s", e)
            return None
        if clearance is None:
            logger.info("[PAYLOAD/GZ] capture_gate_excess_m(): aciklik bilinmiyor "
                        "(poz okunamadi) -- None donuluyor.")
            return None
        excess = clearance - envelope
        # Bilesenler de loglanir: "aciklik buyuk" tek basina ARACIN yuksek
        # oldugunu SOYLEMEZ -- payload'in beklenmedik bir z'de olmasi da ayni
        # sayiyi uretir. Iki poz olmadan bu iki hal ayirt edilemiyor ve
        # duzeltme yanlis degiskeni surebilir.
        _v = _p = None
        try:
            _v = self._client.pose(self._vehicle_model_name)
            _p = self._client.pose(self._payload_model_name)
        except Exception:  # noqa: BLE001 -- yalnizca teshis; olcumu bozamaz
            pass
        logger.info("[PAYLOAD/GZ] capture_gate_excess_m(): dikey aciklik=%.3f m, "
                    "envelope=%.3f m -> fazla=%+.3f m  [arac_z=%s payload_z=%s]",
                    clearance, envelope, excess,
                    "?" if _v is None else f"{_v[2]:.3f}",
                    "?" if _p is None else f"{_p[2]:.3f}")
        return excess

    def has_captured(self) -> bool:
        """/hook/state'in son değeri true mu -- plugin'in joint'i gerçekten
        oluşturduğunda yayınladığı ground-truth (HookAttachSystem.cc:122-127).

        `is True` KASITLI: None ("henüz hiç geçiş görülmedi") yakalanmış
        sayılmaz."""
        return self._client.hook_state() is True

    def is_grappled(self) -> bool:
        """has_captured() ile AYNI biti okur -- ve bu bir SADAKAT KAYBIDIR,
        eşdeğerlik değil.

        Gazebo'da yakalama ve kavrama tek bir CreateComponent çağrısıdır
        (HookAttachSystem.cc:123); ikisini ayırt edecek ikinci bir sinyal
        yoktur. Bu backend kısmi bir kavramayı, kaymış bir payload'ı veya
        başarısız bir kaynağı ALGILAYAMAZ -- plugin başarısızlıkta hiç
        yayın yapmaz (:119-120)."""
        return self.has_captured()

    def is_secured(self) -> bool:
        """has_captured() ile aynı biti okur.

        Sağlam temeli var: joint "fixed" tipindedir (HookAttachSystem.cc:124),
        yani "joint var" ile "rijit olarak güvenceye alındı" Gazebo'da aynı
        şeydir.

        KRİTİK: PayloadManager'ın gerçekten çağırdığı TEK query budur
        (payload_manager.py::catch_box_up). Burada NotImplementedError
        olsaydı Gazebo yolunda catch_box_up() patlardı."""
        return self.has_captured()

    def has_released(self) -> bool:
        """/hook/state'in son değeri false mu.

        `is False` KASITLI: None ("hiç geçiş görülmedi") bırakılmış sayılmaz.

        UYARI (belgelenmiş plugin sınırı): hiçbir şey takılı değilken gelen
        detach isteği HİÇ yayın üretmez (HookAttachSystem.cc:96-99), yani
        state önceki değerinde kalır. Bu metod "bırakma komutu işlendi"
        değil, "en son gözlenen geçiş ayırma yönündeydi" der."""
        return self._client.hook_state() is False

    # -- Yardımcılar ------------------------------------------------------

    @staticmethod
    def _require_calibrated(method_name: str, flex_name: str):
        """CALIBRATION GUARD: tek bir FLEX sabitini oku, TBD (None) ise
        PayloadCalibrationError fırlat.

        Real backend ile AYNI hata tipini kullanır (payload/errors.py) --
        üst katman hangi backend'in bağlı olduğunu bilmeden tek bir
        `except PayloadCalibrationError` ile kalibrasyon eksiğini
        yakalayabilmelidir.

        FLEX değeri çağrı anında modül attribute'u olarak okunur (import
        anında kopyalanmaz), böylece kalibrasyon sonrası güncelleme anında
        etkili olur."""
        value = getattr(payload_config, flex_name)
        if value is None:
            raise PayloadCalibrationError(
                f"GazeboPayloadBackend.{method_name}(): {flex_name} kalibre edilmedi "
                f"(TBD/None). payload_config.py icindeki ilgili FLEX blogunun "
                f"'HOW TO CALIBRATE' adimlarini uygulayip degeri girin. Kalibre "
                f"edilmemis bir envelope ile simulasyona komut GONDERILMEDI.")
        return value
