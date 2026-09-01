import asyncio
import logging
from core.interfaces.i_flight_backend import IFlightBackend
from core.interfaces.i_camera_source import ICameraSource
from core.interfaces.i_detector import IDetector
from core.interfaces.i_payload_visibility_strategy import IPayloadVisibilityStrategy
from core.navigation.centering_controller import CenteringController
from core.position_log.position_store import PositionStore
from core.config.parameters import VERIFICATION_MARKER
from payload import PayloadManager, payload_config
from payload.errors import PayloadCalibrationError
from core.config.parameters import (
    GOREV3_TRANSIT_ALTITUDE_M,
    GOREV3_DESCENT_ALTITUDE_M,
    GOREV3_PICKUP_ALTITUDE_TOLERANCE_M,
    GOREV3_PICKUP_VERIFY_CLIMB_STEPS_M,
    GOREV3_PICKUP_ALIGN_MAX_ATTEMPTS,
    GOREV3_PICKUP_CLEARANCE_MAX_ATTEMPTS,
    GOREV3_PICKUP_CLEARANCE_MARGIN_M,
    GOREV3_PICKUP_MIN_APPROACH_ALTITUDE_M,
    OFFBOARD_SETPOINT_INTERVAL_S,
)

logger = logging.getLogger(__name__)

class Gorev3PickupPhase:
    """Görev 3 Rapor Bölüm 5 (operatör revizyonu, 2026-08-13): Mavi Altıgen
    konumuna (1. yükün bırakıldığı yer) dönülür, orada artık görünen Kırmızı
    Dikdörtgen'e (fiziksel 1. yük) uzun kenarına dik olacak şekilde
    hizalanılır, 30cm geriden görüntüyle doğrulanır, 60cm ileri gidilerek
    alma pozisyonuna geçilir, THIRD MISSION SERVO ile alınır, ve
    GOREV3_PICKUP_VERIFY_CLIMB_STEPS_M irtifalarına yükselerek Kırmızı
    Dikdörtgen'in artık görünmediği doğrulanır."""

    def __init__(self, flight: IFlightBackend, camera: ICameraSource, detector: IDetector,
                 payload_manager: PayloadManager, position_store: PositionStore,
                 visibility_strategy: IPayloadVisibilityStrategy, centering: CenteringController,
                 mission_v3_state=None):
        self.flight = flight
        self.camera = camera
        self.detector = detector
        self.payload_manager = payload_manager
        self.position_store = position_store
        self.visibility_strategy = visibility_strategy
        self.centering = centering
        # DINAMIK HEDEF (2026-08-24): 1st_mission artik MAVI_ALTIGEN
        # olmak ZORUNDA DEGIL -- tespit sirasina gore belirlenir.
        # None verilirse eski davranisa (MAVI_ALTIGEN) duser; uretimde
        # her zaman verilir (bkz. composition root'lar).
        self.mission_v3_state = mission_v3_state

    # Varsayilan: mission_v3_state verilmezse eski (sabit) davranis.
    target_rectangle = "KIRMIZI_DIKDORTGEN"

    def _first_mission_shape(self) -> str:
        """Gorev 3'un donecegi hedefin sekli. mission_v3_state verilmisse
        GERCEK tespit sirasindan okunur; verilmemisse (eski testler)
        MAVI_ALTIGEN'e duser."""
        if self.mission_v3_state is not None:
            shape = self.mission_v3_state.first_mission_shape
            if shape is not None:
                return shape
        return "MAVI_ALTIGEN"

    async def _center_over_payload(self) -> bool:
        """PHASE 7: aracı payload'ın ÜSTÜNE getirir -- FLEX-21'in TEK
        uygulama noktası.

        Görev 2'nin kanıtlanmış deseni (payload_release.py:88-101) aynen
        tekrar kullanılır, yeni bir yaklaşma mantığı İCAT EDİLMEZ:

          1. go_to_and_center(...) -- ofset OLMADAN merkezle. Ofseti
             merkezleme döngüsüne bias olarak vermek ÖLÇÜMLE yasaklandı:
             "This replaces biasing the vision error (the first A2), which
             corrupted the measurement it depended on and produced no net
             improvement: 40.1 / 32.5 cm against a 33.7-37.3 cm baseline"
             (centering_controller.py::descend_to_release).
          2. descend_to_release(...) -- yakınsama bitince dondurulmuş
             kestirimi FLEX-21 kadar BİR KEZ ötele (body->NED, yaw ile,
             sonra çıkarılır) ki payload'ın üstünde duran KANCA olsun,
             kamera değil.

        FLEX-21 TBD (None) iken 2. adım hiç çalışmaz ve davranış bu FLEX
        eklenmeden önceki haliyle BİREBİR aynı kalır -- irtifayı zaten 1.
        adım kapatıyor. Bu, Görev 2'deki `if mount:` guard'ının aynısıdır
        (payload_release.py:98). Kalibre edilmemiş olması bir kez loglanır.

        Eski akıştaki "30 cm'de görüntüyle aktif görme" şartı (Görev 3
        Rapor) burada DAHA GÜÇLÜ karşılanır: go_to_and_center hedefi hem
        görmek hem +/-0.01 normalize bandında merkezlemek zorunda; eski
        best-effort "3 kare gördüm, devam et" kontrolünden katıdır."""
        # DAR IRTIFA BANDI ZORUNLU (SITL bulgusu, 2026-08-24 Phase 15 kosu 1):
        # ilk surum bu cagriyi alt_tolerance_m VERMEDEN yapiyordu, yani
        # varsayilan gevsek ALTITUDE_CONVERGENCE_TOLERANCE_M (0.30 m) bandi
        # devreye giriyordu. Sonuc: merkezleme yanal olarak yakinsadi ama
        # alt_err=+0.28 m ile, yani arac ~0.58 m'de durdu; dikey aciklik
        # 0.53 m olup FLEX-20 (0.35 m) kapisini gecemedi ve catch_box_down()
        # DEPLOY_TIMEOUT ile dustu.
        #
        # Bu, go_to_and_center()'in KENDI docstring'inde zaten belgelenmis
        # hata sinifidir: "the FINAL step is handed the release band...
        # measured: payload 2 released at 0.564 m because its triangle
        # stayed visible and the loose 0.30 m band accepted it." Gorev 2'nin
        # son yaklasma adimi (payload_release.py:88-90) tam bu yuzden dar
        # bandi geciriyor; alma adimi da gecirmek ZORUNDA.
        #
        # BAND DEGERI (2026-08-24 revizyonu): ilk surum Gorev 2'nin
        # bırakma bandini (PAYLOAD_RELEASE_ALTITUDE_TOLERANCE_M = 0.05)
        # yeniden kullaniyordu; 12 kosuluk seride bunun COK DAR oldugu
        # olculdu (5/12 basarisizlik: yanal yakinsama tamam, dikey hata
        # +0.12..+0.20 m). Artik ayri bir sabit kullaniliyor
        # (GOREV3_PICKUP_ALTITUDE_TOLERANCE_M = 0.10) -- gerekcesi ve
        # FLEX-20 zarfi aritmetigi parameters.py'de.
        converged = await self.centering.go_to_and_center(
            self.target_rectangle, altitude_m=GOREV3_DESCENT_ALTITUDE_M,
            alt_tolerance_m=GOREV3_PICKUP_ALTITUDE_TOLERANCE_M)
        if not converged:
            logger.error("%s üzerinde merkezlenilemedi -- alma pozisyonuna "
                         "gidilemiyor.", self.target_rectangle)
            return False

        if not await self._descend_until_inside_capture_gate():
            return False

        hook_offset = payload_config.FLEX_21_HOOK_MOUNT_OFFSET_BODY_M
        if not hook_offset:
            logger.warning(
                "[HOOK_OFFSET] FLEX-21 kalibre edilmemis (TBD) -- kanca montaj "
                "otelemesi UYGULANMIYOR. Kanca, kameranin hizalandigi noktaya "
                "iner; aradaki montaj kolu kadar sapma beklenir. Kalibrasyon: "
                "payload_config.py FLEX-21 HOW TO CALIBRATE.")
            return True

        logger.info("[HOOK_OFFSET] FLEX-21 uygulaniyor: forward=%.3f m, right=%.3f m",
                    hook_offset[0], hook_offset[1])
        await self.centering.descend_to_release(
            self.target_rectangle, GOREV3_DESCENT_ALTITUDE_M, hook_offset)
        return True

    def _capture_gate_excess_m(self):
        """capture_gate_excess_m()'i MANAGER uzerinde de duck-typed yoklar.

        Neden dogrudan cagrilmiyor: bu bir OPSIYONEL yetenek. Yalnizca
        GazeboPayloadBackend saglar, ve gorev katmanina enjekte edilen her
        payload_manager gercek PayloadManager olmak zorunda degil (testlerdeki
        sahte manager'lar, ileride baska bir kompozisyon). Yetenegi olmayan
        bir nesneye dogrudan cagri, bu ozelligi eklemenin MEVCUT yollari
        bozmasi demek olurdu -- oysa sozlesme tam tersi: yetenek yoksa
        davranis birebir eskisi gibi kalir."""
        probe = getattr(self.payload_manager, "capture_gate_excess_m", None)
        if probe is None:
            return None
        try:
            return probe()
        except Exception:  # noqa: BLE001 -- olcum yolu gorev akisini bozamaz
            return None

    async def _descend_until_inside_capture_gate(self) -> bool:
        """Yakinsama sonrasi GERCEK acikligi okur; zarf disindaysa alcalmaya
        DEVAM eder. Icerideyse (ya da olcum yoksa) hicbir sey yapmaz.

        NEDEN GEREKLI -- iki irtifa referansi uzlastirilmiyordu (olculdu,
        2026-08-26, 4 kosuluk enstrumante seri):

            kaynak                         basarili kosu   BASARISIZ kosu
            PX4 relative_altitude          0.343 m         0.340 m
            Gazebo ground-truth model z    0.382 m         0.630 m
            fark                          +0.039 m        +0.290 m

        Merkezleme ILK sutunu okuyup "0.30 +/- 0.10 bandindayim" diyor;
        is_in_capture_zone() IKINCI sutunu okuyup 0.45 m zarfla karsilastiriyor.
        Basarisiz kosuda arac fiziksel olarak 63 cm yukarideydi ve kapi HAKLI
        OLARAK reddetti -- ama faz o noktada aninda MISSION_FAILED'a dusuyordu
        (bkz. mission_7bec65433788, +205.16s: CENTERING_CONVERGED ile
        GOREV3_PHASE_FAILED arasinda 0.6 ms). Poz TAZEYDI (yas 0.98 ms), yani
        sorun gecikme degil.

        NEDEN BANDI DARALTMAK/HEDEFI SABIT INDIRMEK COZMEZ: ikisi de PX4
        referansini kaydirir. Fark kosudan kosuya degistigi icin (0.02-0.29 m)
        sabit bir kaydirma bazi kosularda yetmez, bazilarinda gereksiz alcaltir.
        Tek dogru girdi OLCULEN fazlaligin kendisidir.

        GERCEK DONANIMA SIZMAZ: capture_gate_excess_m() yalnizca
        GazeboPayloadBackend'de tanimli; PayloadManager passthrough'u
        RealPayloadBackend icin None doner ve bu metod ILK kontrolde
        dokunmadan cikar -- yani real/dual yolunda davranis birebir eskisi
        gibidir. Zaten gercek donanimda ikilik de olusmaz: kapi da, merkezleme
        de ayni GPS/barometre referansini kullanir."""
        target_alt = GOREV3_DESCENT_ALTITUDE_M

        for attempt in range(1, GOREV3_PICKUP_CLEARANCE_MAX_ATTEMPTS + 1):
            excess = self._capture_gate_excess_m()

            if excess is None:
                # Backend olcum veremiyor (real/dual, ya da poz okunamadi).
                # "Bilmiyorum" ASLA "yakinim" degildir -- ama burada da
                # "uzagim" degildir: karar mevcut kapiya (deploy()) birakilir,
                # yani bu metod eklenmeden onceki davranisin AYNISI.
                logger.info("[PICKUP_GATE] aciklik olcumu yok -- kapali-dongu "
                            "duzeltme atlaniyor (davranis degismedi).")
                return True

            if excess <= 0:
                logger.info("[PICKUP_GATE] arac yakalama zarfinin ICINDE "
                            "(fazla=%+.3f m, deneme %d/%d) -- almaya geciliyor.",
                            excess, attempt, GOREV3_PICKUP_CLEARANCE_MAX_ATTEMPTS)
                return True

            new_alt = max(GOREV3_PICKUP_MIN_APPROACH_ALTITUDE_M,
                          target_alt - excess - GOREV3_PICKUP_CLEARANCE_MARGIN_M)
            if new_alt >= target_alt:
                # Taban'a dayandik ve daha fazla alcalamiyoruz. Tekrar denemek
                # ayni sonucu verir; dongulemek yerine acikca basarisiz ol.
                logger.error("[PICKUP_GATE] zarf disindayiz (fazla=%+.3f m) ama "
                             "hedef irtifa tabanda (%.2f m) -- daha fazla "
                             "alcalinamaz.", excess, target_alt)
                return False

            logger.warning("[PICKUP_GATE] zarf DISINDA (fazla=%+.3f m) -- hedef "
                           "irtifa %.3f m -> %.3f m, merkezleme tekrarlaniyor "
                           "(deneme %d/%d).", excess, target_alt, new_alt,
                           attempt, GOREV3_PICKUP_CLEARANCE_MAX_ATTEMPTS)
            target_alt = new_alt

            converged = await self.centering.go_to_and_center(
                self.target_rectangle, altitude_m=target_alt,
                alt_tolerance_m=GOREV3_PICKUP_ALTITUDE_TOLERANCE_M)
            if not converged:
                logger.error("[PICKUP_GATE] duzeltilmis irtifada (%.3f m) "
                             "merkezlenilemedi.", target_alt)
                return False

        # Deneme butcesi tukendi. Deploy()'u yine de cagirip ayni reddi almak
        # yerine, SEBEBI belli bir basarisizlik uretilir.
        final_excess = self._capture_gate_excess_m()
        logger.error("[PICKUP_GATE] %d denemeye ragmen zarfa girilemedi "
                     "(son fazla=%s m).", GOREV3_PICKUP_CLEARANCE_MAX_ATTEMPTS,
                     "?" if final_excess is None else f"{final_excess:+.3f}")
        return False

    async def _run_payload_pickup(self) -> bool:
        """V33 alma dizisi: catch_box_down -> grapple -> catch_box_up.

        Her adım PayloadResult döndürür; ilk başarısızlıkta durulur ve
        hangi adımın neden düştüğü loglanır (eski tek-çağrılı yolda bu
        bilgi hiç yoktu).

        REAL YOLUN BİLİNEN BOŞLUĞU (Phase 4 TODO(SAFETY)): gerçek donanımda
        RealPayloadBackend henüz kalibre edilmemiş (FLEX-14..19 TBD) ve
        yakalamayı doğrulayacak sensör yolu yok. Bu durumda backend
        PayloadCalibrationError veya NotImplementedError yükseltir.
        Bunlar BURADA yakalanır ve temiz bir faz başarısızlığına çevrilir --
        master_fsm.py:121'deki genel `except Exception` zaten çökmeyi
        önlüyor ama faz atıfını kaybediyor ve GOREV3_PHASE_FAILED yolunu
        atlıyor. Burada yakalamak o iki şeyi de korur. Mission ne çöker ne
        de sessizce takılır."""
        steps = (
            ("catch_box_down (SERVO2_DOWN + CATCH_PAYLOAD)", self.payload_manager.catch_box_down),
            ("grapple (SERVO3_GRAPPLE)", self.payload_manager.grapple),
            ("catch_box_up (SERVO2_REVERSE)", self.payload_manager.catch_box_up),
        )
        for label, step in steps:
            try:
                result = await step()
            except (PayloadCalibrationError, NotImplementedError) as e:
                logger.error(
                    "Yük alma durduruldu -- %s: gerçek donanım payload yolu henüz "
                    "hazır değil (kalibrasyon/sensör entegrasyonu Phase 17 bekliyor). "
                    "Ayrıntı: %s", label, e)
                return False
            if not result.success:
                logger.error("Yük alma başarısız -- %s: %s (state=%s)",
                             label, result.error_reason, result.final_state.value)
                return False
            logger.info("%s tamam (state=%s, %.2fs)",
                        label, result.final_state.value, result.elapsed_time)
        return True

    async def _locate_target_with_retries(self):
        """Kırmızı Dikdörtgen bulunana kadar (veya deneme sınırına kadar)
        her karede yeniden dener -- go_to_and_center()'ın 'hedef kayboldu'
        döngüsüyle aynı mantık."""
        for _ in range(GOREV3_PICKUP_ALIGN_MAX_ATTEMPTS):
            try:
                return await self.visibility_strategy.locate_target(self.detector, None)
            except RuntimeError:
                await asyncio.sleep(OFFBOARD_SETPOINT_INTERVAL_S)
        return None

    async def run(self) -> bool:
        logger.info("Görev 3 Faz 1 (Alma) Başlatıldı.")

        # DINAMIK: 1st_mission hangi sekilse ona donulur (spec md.13).
        target_shape = self._first_mission_shape()
        self.target_rectangle = VERIFICATION_MARKER[target_shape]
        logger.info("Gorev 3 hedefi: 1st_mission=%s -> aranacak dikdortgen=%s",
                    target_shape, self.target_rectangle)
        # Backend'e hangi payload'in alinacagini bildir -- Gazebo tarafinda
        # model adi bundan turer, Real'de no-op'tur.
        self.payload_manager.select_payload(target_shape)
        # Hizalama stratejisi de ayni dikdortgeni aramali -- aksi halde
        # ucgen-once senaryosunda MAVI_DIKDORTGEN aranirken strateji hala
        # KIRMIZI_DIKDORTGEN'e bakardi (2026-08-24 bulgusu).
        if hasattr(self.visibility_strategy, "rectangle_shape"):
            self.visibility_strategy.rectangle_shape = self.target_rectangle

        mavi_altigen_point = self.position_store.get(target_shape)
        if mavi_altigen_point is None:
            raise RuntimeError(f"{target_shape} konumu bulunamadı! Görev 3 başlatılamaz.")

        logger.info(f"Mavi Altıgen konumuna {GOREV3_TRANSIT_ALTITUDE_M}m irtifada gidiliyor: "
                    f"{mavi_altigen_point.gps_lat}, {mavi_altigen_point.gps_lon}")
        # BUG FIX (continuous audit, 2026-08-13): this used to hold north=0/
        # east=0 -- i.e. NOT actually navigate anywhere, just change
        # altitude in place. That was an accepted simplification before
        # CenteringController.goto_global_position_and_wait() existed (see
        # its own docstring); left unfixed after that, it meant Görev 3
        # Faz 1 started searching for Kırmızı Dikdörtgen wherever Payload
        # Mission 2 happened to leave the vehicle (Kırmızı Üçgen's
        # position), never at Mavi Altıgen where the payload actually is.
        converged = await self.centering.goto_global_position_and_wait(
            mavi_altigen_point.gps_lat, mavi_altigen_point.gps_lon, GOREV3_TRANSIT_ALTITUDE_M)
        if not converged:
            logger.warning("Mavi Altigen konumuna navigasyon zaman asimina ugradi -- yine de devam ediliyor.")

        target = await self._locate_target_with_retries()
        if target is None:
            logger.error("%s bulunamadı -- Görev 3 Faz 1 başarısız.", self.target_rectangle)
            return False

        alignment_delta_deg = await self.visibility_strategy.compute_alignment_yaw(target, None)
        current_yaw = await self.flight.get_yaw_deg()
        aligned_yaw = current_yaw + alignment_delta_deg
        logger.info(f"Kırmızı Dikdörtgenin uzun kenarına dik hizalanılıyor: "
                    f"{current_yaw:.1f} -> {aligned_yaw:.1f} derece")
        await self.flight.goto_position_ned_and_hold(0, 0, -GOREV3_TRANSIT_ALTITUDE_M, aligned_yaw, 2.0)

        # PHASE 7: eski "0.30 m geri -> 30 cm'de gorunurluk onayi -> 0.60 m
        # ileri" dansi KALDIRILDI (operator karari, 2026-08-23: yeni mekanik
        # yakalama sisteminde arac dogrudan payload'in USTUNE geliyor).
        # Yerine vision-gudumlu merkezleme + tek seferlik kanca otelemesi.
        if not await self._center_over_payload():
            return False

        logger.info("Yük alma mekanizması aktifleşiyor...")
        # THIRD MISSION SERVO
        #
        # PHASE 6.5: IPayloadActuator.activate_pickup_mechanism() yerine
        # payload/PayloadManager. Tek opak "mekanizmayı çalıştır" çağrısı,
        # V33'ün belgelenmiş üç adımına açıldı:
        #   catch_box_down() -> SERVO2_DOWN + CATCH_PAYLOAD + TIMEOUT_CHECK
        #   grapple()        -> SERVO3_GRAPPLE
        #   catch_box_up()   -> SERVO2_REVERSE (1. kullanım)
        # Üçü tırmanmadan ÖNCE, tek blokta ardışık çağrılır (operatör
        # kararı, 2026-08-23): V33 sırası retract'i taşıma/tırmanmadan önce
        # koyar, ve payload sarkarken tırmanmaktan kaçınır.
        #
        # DAVRANIŞ DEĞİŞİKLİĞİ (operatör onaylı): eski çağrının dönüşü
        # ATILIYORDU -- mekanizma başarısız olsa bile faz sessizce devam
        # edip kararı tamamen vision'a bırakıyordu. Artık mekanizma sonucu
        # BAĞLAYICI: başarısızsa vision doğrulamasına hiç geçilmez.
        # Başarılıysa aşağıdaki mevcut vision doğrulaması AYNEN çalışır ve
        # o da geçmek zorundadır.
        if not await self._run_payload_pickup():
            return False

        # PHASE 15 (2026-08-24): ALMA DOGRULAMASI ARTIK FIZIKSEL, VISION DEGIL.
        #
        # Eskiden burada "tirman ve Kirmizi Dikdortgen artik gorunmuyor mu"
        # diye bakiliyordu. Yeni yaklasma akisinda bu test YAPISAL OLARAK
        # GECILEMEZ hale geldi: arac artik payload'in TAM USTUNE geliyor
        # (Phase 7), dolayisiyla yakalanan payload kameranin altinda sallanip
        # goruntude KALIYOR. Phase 15'te 3 kosudan 2'sinde mekanik alma
        # basariliyken (CAPTURED -> GRAPPLED -> TRANSPORTING) bu adim reddetti;
        # 3 m'de tek tespit taSINAN payload'in kendisiydi. Eski dans'li akista
        # ayni adim "goruntude yok" veriyordu cunku dans araci payload'dan
        # kaydiriyordu -- yani o testin gectigi durum, payload'in gercekten
        # alindigini DEGIL, kameranin ondan uzaklastigini olcuyordu.
        #
        # Yerine gecen dogrulama daha guclu bir ground truth: joint'in
        # varligini okuyan tek bit (Gazebo'da HookAttachSystem'in /hook/state
        # yayini). Iki noktada sorulur:
        #   1. Tirmanistan ONCE  -- yuk gercekten elimizde mi
        #   2. Tirmanistan SONRA -- 3 m tirmanisa ragmen HALA elimizde mi
        # Ikincisi Phase 6 acceptance'inin olctugu seyin ta kendisidir
        # ("payload UAV'i izliyor mu", takip hatasi 0.0002 m) -- yeniden
        # implement edilmez, mission seviyesine tasinir.
        if not self._verify_payload_held("tirmanis oncesi"):
            return False

        for alt in GOREV3_PICKUP_VERIFY_CLIMB_STEPS_M:
            logger.info(f"Yükseliniyor: {alt}m")
            await self.flight.goto_position_ned_and_hold(0, 0, -alt, aligned_yaw, 2.0)

        if not self._verify_payload_held(
                f"{GOREV3_PICKUP_VERIFY_CLIMB_STEPS_M[-1]}m tirmanis sonrasi"):
            return False

        logger.info("Yük Alma Başarılı: yük fiziksel olarak alindi ve tirmanis "
                    "boyunca guvencede kaldi.")
        return True

    def _verify_payload_held(self, moment: str) -> bool:
        """Yukun FIZIKSEL olarak elimizde oldugunu backend'e sorar.

        get_state() burada YETMEZ: o FSM'in hafizasidir ve yuk dusse bile
        TRANSPORTING demeye devam eder. is_still_secured() joint bitini
        okur."""
        try:
            held = self.payload_manager.is_still_secured()
        except (PayloadCalibrationError, NotImplementedError) as e:
            logger.error("Alma dogrulanamadi (%s): gercek donanim payload sorgu yolu "
                         "henuz hazir degil (sensor entegrasyonu Phase 17 bekliyor). "
                         "Ayrinti: %s", moment, e)
            return False

        if not held:
            logger.error("[PICKUP_PAYLOAD_NOT_HELD] Alma basarisiz (%s): mekanizma "
                         "tamamlandi ama yuk fiziksel olarak elimizde DEGIL.", moment)
            return False

        logger.info("Alma dogrulandi (%s): yuk guvencede (state=%s).",
                    moment, self.payload_manager.get_state().value)
        return True
