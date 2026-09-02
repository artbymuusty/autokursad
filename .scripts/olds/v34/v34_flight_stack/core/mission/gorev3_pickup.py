import asyncio
import math
import logging
from core.interfaces.i_flight_backend import IFlightBackend
from core.interfaces.i_camera_source import ICameraSource
from core.interfaces.i_detector import IDetector
from core.interfaces.i_payload_actuator import IPayloadActuator
from core.interfaces.i_payload_visibility_strategy import IPayloadVisibilityStrategy
from core.navigation.centering_controller import CenteringController
from core.position_log.position_store import PositionStore
from core.detection.camera_intrinsics import default_camera_intrinsics
from gz_system.gz_payload_actuator import HOOK_WINCH_EXTEND_M
from core.mission.visual_alignment import VisualHookAligner
from core.config.parameters import (
    GOREV3_CRUISE_ALTITUDE_M,
    GOREV3_TRANSIT_ALTITUDE_M,
    GOREV3_DESCENT_ALTITUDE_M,
    GOREV3_RETREAT_DISTANCE_M,
    GOREV3_PICKUP_VERIFY_CLIMB_STEPS_M,
    GOREV3_PICKUP_ALIGN_MAX_ATTEMPTS,
    GOREV3_PICKUP_VISIBILITY_CONFIRM_FRAMES,
    OFFBOARD_SETPOINT_INTERVAL_S,
)

# Kanca govde ofseti: mono_cam x=+0.085, hook_winch_link x=-0.090
# (Tools/simulation/gz/models/x500_mono_cam_down/model.sdf) -- ikisi de
# yuklerin (uzun kenar 0.14 m) iki ucunda 1.5 cm payla. Ortalayan
# kamera ile kanca arasi 0.175 m; eskiden 0.70 m idi ve o korlemesine
# kayma temasin en buyuk hata kaynagiydi.
HOOK_BODY_OFFSET_FORWARD_M = 0.175
# Alma denemeleri boyunca konumu tutmak icin ayrilan sure:
# 3 deneme x (12 s yakalama penceresi + vinc/geri cekme) icin pay.
PICKUP_HOLD_S = 70.0
# Kanca hizalamasinin yapildigi irtifa. Gorus burada hala guvenilir:
# 1.2 m'de yuk 63 x 22 px = 1417 px2 (HSV_MIN_AREA_RECT_BASE=400'un
# 3.5 kati) ve kadraj 2.84 x 2.13 m, yani 0.175 m'lik kanca ofseti
# hedefi kenara itmiyor (0.30 m'de ayni ofset 315 px ile kadrajin
# kenarina dayaniyordu -- PHASE 13 D3'un olcup reddettigi rejim).
HOOK_ALIGN_ALTITUDE_M = 1.2
# Yuk kamerada kaybolursa kac metre yukselip yeniden aranacak
# ve kac kez denenecek (operator, 2026-08-23).
HOOK_REACQUIRE_CLIMB_M = 1.0
HOOK_REACQUIRE_MAX_CLIMBS = 3
# Kancanin yukun ORTASINA denk geldigini goruntuden dogrulama
# esigi. Magnet zaten en fazla 5 cm'den yakaliyor; goruntu
# kontrolu ayni buyuklukte olmali ki tutarsiz olmasin.
HOOK_VISION_ALIGN_TOLERANCE_M = 0.05
# KANCA POZUNA GORE KAPALI CEVRIM HIZALAMA (2026-08-26).
# Kanca artik menteseli bir ipin ucunda ve gercek pozu Gazebo'dan
# okunabiliyor (actuator.hook_to_receiver_offset_world). Bu yuzden alma
# irtifasinda son bir duzeltme yapiliyor: olculen kanca-yuva sapmasi kadar
# arac otelenir, ip sonene kadar beklenir, tekrar olculur.
#
# NEDEN GEREKLI: govde ofsetiyle acik cevrim konumlanmanin olculen yanal
# hatasi 24-56 mm (kabul testi, 2026-08-26). Yeni oturma kapisinin yanal
# siniri yuvanin agiz yaricapi olan 23.25 mm; yani acik cevrim TEK BASINA
# CAD'in gerektirdigi hassasiyeti tutturamiyor. Duzeltme, olcumu yapan
# poz kaynaginin ta kendisiyle kapatiliyor.
# Vinci hizalamadan ONCE salmak icin beklenen sure. Vinc 0.40 m komutu
# aliyor ve SDF'deki eklem hiz siniri 0.5 m/s, yani hareketin kendisi ~0.8 s;
# geri kalani kancanin guverteye oturup ipteki salinimin (olculen periyot
# 0.831 s) sonmesi icin. 4 s, ~4.8 periyot.
HOOK_PAYOUT_SETTLE_S = 4.0
# GORSEL HIZALAMA IRTIFASI. Hizalama alma irtifasinda (0.30 m) YAPILAMAZ, ve
# bu bir ayar meselesi degil, kadraj geometrisi:
#
# Faz, KANCAYI yuvanin uzerine getirmek icin araci HOOK_BODY_OFFSET_FORWARD_M
# (0.175 m) ileri kaydirir. O anda KAMERA yuvadan 0.175 + 0.085 = 0.260 m
# ileridedir (0.085 = kameranin govde kol mesafesi). Yuva bu durumda kadrajda
#     v = 0.260 * 539.94 / derinlik   piksel asagida gorunur,
# ve yari-kadraj yalnizca 480 px:
#     arac 0.30 m -> derinlik 0.280 -> 501 px  KADRAJ DISI
#     arac 0.45 m -> derinlik 0.430 -> 327 px  (yari-kadrajin %68'i)
#     arac 0.70 m -> derinlik 0.680 -> 206 px  (%43)
# Olculdu: 0.30 m'de gorev 30 yinelemede yalnizca 7 tespit yapabildi ve
# "receiver_lost" ile guvenli sekilde durdu -- dogru davranis, yanlis irtifa.
#
# 0.90 m: derinlik 0.88, yuva merkezden 160 px asagida, yukun uzak kenari
# 204 px'te -- yari-kadrajin (480 px) %42'si, yani servo hedefe yaklasirken
# yuvayi kadraj disina itme riski yok. 0.55 m denendi ve yetmedi: yakalama
# 20 tespitten sonra "receiver_lost" ile dustu, cunku hizalama ilerledikce
# yuva alt kenara dogru kayiyor.
#
# Yuksekte hizalamak artik BEDAVA, cunku vinc hizalama ve inis boyunca TOPLU
# (asagi bak) ve son duzeltme zaten alma irtifasinda yapiliyor. Dedektorun
# 66 kareli olcumunde bu bant (0.90-1.40 m) 0.076 cm merkez hatasi veriyor.
HOOK_VISUAL_ALIGN_ALTITUDE_M = 0.90
HOOK_ALIGN_MAX_CORRECTIONS = 6
# Duzeltmeyi birakma esigi: oturma kapisinin yanal sinirinin yarisi. Yarisi,
# cunku kapinin tam sinirinda durmak PX4'un birkac mm'lik surukklenmesiyle
# hemen disari cikar.
HOOK_ALIGN_TARGET_LATERAL_M = 0.010
# Havadaki gorsel hizalamanin hedefi. Hassas is asagida yapiliyor
# (_settle_hook_onto), orada vinc acik ve her duzeltme DINLENEN kancayi
# guverte uzerinde SURUKLUYOR -- havada ayni hassasiyeti istemek yalnizca
# sarkacla bogusmak demek: olculdu, 23 saglam tespitle bile 31 mm'de zaman
# asimina ugradi. 30 mm, oturma kapisinin 23.25 mm'lik sinirinin hemen
# ustunde ve asagidaki duzeltmenin rahatca kapatabilecegi bir artik.
HOOK_VISUAL_ALIGN_TOLERANCE_M = 0.030
# Havada yakinsamamis olsa bile, bu buyuklugun altindaki bir artik hata
# asagidaki _settle_hook_onto tarafindan kapatilabilir. Uzerindeyse olcum
# guvenilmez demektir ve faz guvenli sekilde durur.
HOOK_VISUAL_ALIGN_MAX_USABLE_M = 0.12
# ALMA IRTIFASINDAKI SON DUZELTMENIN KAZANCI VE SONUMLEMESI.
#
# Vinc salinirken kanca serbest dusup salliniyor: olculdu, payout ONCESI
# yanal 14.3 mm / egim 0.2 derece iken, payout SONRASI 64.6 mm / 33.3 derece.
# Kanca artik guverte ustunde DINLENIYOR, yani her duzeltme onu surukluyor --
# ama surtunme ve sarkac nedeniyle hemen takip etmiyor.
#
# Tam hatayi tek adimda uygulamak (dead-beat) bu yuzden asiyor: olculdu,
# 93 -> 131 -> 68 -> 68 -> 48 -> 78 mm, yakinsamiyor. Kazanc 0.5 ile her adim
# kalan hatanin yarisini kapatir, ve her adimdan sonra kancanin gercekten
# durmasi beklenir (olculen sarkac periyodu 0.831 s; 2.5 s ~3 periyot).
HOOK_SETTLE_GAIN = 0.5
HOOK_SETTLE_WAIT_S = 2.5
# Kanca hala hareket ediyorken olcmek, hareketin kendisini hata sanmak demek.
HOOK_SETTLE_MAX_SPEED_MPS = 0.03
# Her duzeltmeden sonra ipin sonmesi icin beklenen sure. Olculen sarkac
# periyodu 0.831 s; iki periyot, kucuk bir otelemenin uyandirdigi salinimi
# oturma kapisinin hiz sinirinin altina indirmeye yeter.
HOOK_ALIGN_SETTLE_S = 1.7
# Alma dogrulamasi: yuk en az bu kadar yukselmis olmali.
# Tirmanis adimlari 1/2/3 m oldugu icin bu esik cok gevsek
# secildi -- amac 'gercekten kalkti mi', 'ne kadar' degil.
PICKUP_LIFT_CONFIRM_M = 0.30
# Gorev 3 kirmizi payload'i alir (mavi altigene birakilan).
SEARCH_CENTER_RED = "red"
SHAPE_TO_COLOR_RED = SEARCH_CENTER_RED

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
                 actuator: IPayloadActuator, position_store: PositionStore,
                 visibility_strategy: IPayloadVisibilityStrategy, centering: CenteringController,
                 publisher=None):
        # publisher OPSIYONEL ve varsayilani None: bu faz simdiye kadar event
        # bus'a HIC yayin yapmiyordu ve tum alma detayi yalnizca mission.log'a
        # gidiyordu. Sonucu 2026-08-31'de olculdu: olay akisinda faz basi ile
        # faz sonu arasinda 77-89 s "sessizlik" gorunuyordu ve bu YANLISLIKLA
        # "kod takilmis" diye okundu -- oysa kod her adimi calistiriyordu.
        # Yayin yalnizca GORUNURLUK ekler, davranisi degistirmez; None
        # verildiginde (testler) hicbir sey yayinlanmaz.
        self.publisher = publisher
        self.flight = flight
        self.camera = camera
        self.detector = detector
        self.actuator = actuator
        self.position_store = position_store
        self.visibility_strategy = visibility_strategy
        self.centering = centering

    def _publish(self, code: str, message: str = "", data: dict = None,
                 severity=None):
        """Olay yayinla; publisher yoksa sessizce gec (davranis degismez)."""
        if self.publisher is None:
            return
        try:
            from core.telemetry.events import Event, Severity, Category
            self.publisher.publish(Event(
                code=code, subsystem="Gorev3PickupPhase",
                category=Category.LIFECYCLE,
                severity=severity or Severity.INFO,
                message=message, data=data or {}))
        except Exception:  # noqa: BLE001 -- gorunurluk gorevi dusuremez
            logger.debug("[GOREV3] olay yayinlanamadi: %s", code, exc_info=True)

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


    async def _rect_pixel_offset(self):
        """KIRMIZI_DIKDORTGEN'in kanca hedef noktasina gore PIKSEL sapmasi.

        Kamera govde +0.085'te, kanca -0.090'da. Kamera bir noktayi kare
        MERKEZINDE gorurken o nokta govde (+0.085, 0)'dadir; kanca ise
        HOOK_BODY_OFFSET_FORWARD_M kadar geridedir. Dolayisiyla kanca yukun
        TAM ORTASINDAYKEN yuk, kare merkezinin GERISINDE su kadar piksel
        gorunur:
            offset_px = HOOK_BODY_OFFSET_FORWARD_M * f / irtifa
        Asagi bakan kamerada govde-ileri, goruntu -y yonudur (bkz.
        centering_controller'daki isaret notu), yani beklenen nokta
        merkezin ALTINDA +offset_px'tedir.

        Doner: (sapma_m, gorunur_mu). Gorunmuyorsa (None, False)."""
        try:
            detections = await self.detector.detect(None)
        except Exception:  # noqa: BLE001
            return (None, False)
        rect = next((d for d in detections if d.shape_type == "KIRMIZI_DIKDORTGEN"), None)
        if rect is None:
            return (None, False)
        try:
            _lat, _lon, alt = await self.flight.get_global_position()
        except Exception:  # noqa: BLE001
            return (None, True)
        intr = default_camera_intrinsics()
        res_w, res_h = self.camera.get_resolution()
        if intr is None or not alt or alt <= 0:
            return (None, True)
        focal = intr.scaled_to(res_w, res_h).focal_px
        if not focal:
            return (None, True)
        want_x = res_w / 2.0
        want_y = res_h / 2.0 + HOOK_BODY_OFFSET_FORWARD_M * focal / alt
        dx_px = rect.center_px[0] - want_x
        dy_px = rect.center_px[1] - want_y
        return (math.hypot(dx_px, dy_px) * alt / focal, True)

    async def _reacquire_by_climbing(self, aligned_yaw: float) -> bool:
        """Yuk kamerada yoksa 1 m yukselip yeniden bul ve kancaya gore ortala.

        Operator istegi (2026-08-23). Alma irtifasinda kadraj 0.71 x 0.53 m;
        kucuk bir konum hatasi yuku kadraj disina atmaya yetiyor ve o
        noktadan korlemesine devam etmek anlamsiz."""
        for step in range(1, HOOK_REACQUIRE_MAX_CLIMBS + 1):
            n0, e0, _d = await self.flight.get_position_ned()
            _lat, _lon, alt = await self.flight.get_global_position()
            higher = alt + HOOK_REACQUIRE_CLIMB_M
            logger.warning("Kirmizi Dikdortgen kamerada yok -- %d/%d: %.1f m'ye yukseliniyor.",
                           step, HOOK_REACQUIRE_MAX_CLIMBS, higher)
            await self.flight.goto_position_ned_and_hold(n0, e0, -higher, aligned_yaw, 3.0)
            if await self._locate_target_with_retries() is None:
                continue
            logger.info("Hedef yeniden bulundu -- %.1f m'de kancaya gore ortalanıyor.", higher)
            await self.centering.go_to_and_center("KIRMIZI_DIKDORTGEN", altitude_m=higher)
            return True
        return False

    async def _settle_hook_onto(self, recv_ned, yaw_deg: float, alt_m: float):
        """Drive the RESTING hook onto a receiver position measured earlier.

        The camera cannot see the receiver down here, so the target comes from
        the visual alignment done at HOOK_VISUAL_ALIGN_ALTITUDE_M. What closes
        the loop is the hook's own real pose: the winch is out and the hook is
        resting, so each nudge drags it across the deck rather than swinging
        it, which is why this converges where a mid-air correction would not.

        Returns the final lateral error in metres, or None if the hook pose
        was unreadable (in which case the seating gate will refuse anyway).
        """
        last = None
        for i in range(1, HOOK_ALIGN_MAX_CORRECTIONS + 1):
            hook = getattr(self.actuator, "hook_nose_ned_offset_m", lambda: None)()
            if hook is None:
                logger.warning("[SON_DUZELTME] kanca pozu okunamadi.")
                return None
            n0, e0, _ = await self.flight.get_position_ned()
            err_n = recv_ned[0] - (n0 + hook[0])
            err_e = recv_ned[1] - (e0 + hook[1])
            last = math.hypot(err_n, err_e)
            if last <= HOOK_ALIGN_TARGET_LATERAL_M:
                logger.info("[SON_DUZELTME] %d/%d yanal %.1f mm -- hedefin icinde.",
                            i, HOOK_ALIGN_MAX_CORRECTIONS, last * 1000)
                return last
            step_n = err_n * HOOK_SETTLE_GAIN
            step_e = err_e * HOOK_SETTLE_GAIN
            # ITERASYON BASINA HAM OLCUM (2026-08-31). Onceden yalnizca hata
            # BUYUKLUGU ve komut loglaniyordu; kancanin araci takip edip
            # etmedigini anlamak icin poz gerekiyordu ve bu tur onu
            # err = 2 x komut ozdesliginden TURETMEK zorunda kalindi. Artik
            # dogrudan yaziliyor: kanca ofseti, arac NED'i ve ikisinden
            # cikan MUTLAK kanca konumu.
            logger.info("[SON_DUZELTME] %d/%d yanal %.1f mm -> (kuzey %+.3f, dogu %+.3f)"
                        "  | kanca_ofset=(%+.4f, %+.4f) arac_ned=(%.4f, %.4f)"
                        " kanca_mutlak=(%.4f, %.4f)",
                        i, HOOK_ALIGN_MAX_CORRECTIONS, last * 1000, step_n, step_e,
                        hook[0], hook[1], n0, e0, n0 + hook[0], e0 + hook[1])
            self._publish("GOREV3_CORRECTION_STEP", f"{i}/{HOOK_ALIGN_MAX_CORRECTIONS}",
                          data={"iteration": i, "lateral_mm": round(last * 1000, 1),
                                "step_n": round(step_n, 4), "step_e": round(step_e, 4),
                                "hook_offset": [round(hook[0], 4), round(hook[1], 4)],
                                "vehicle_ned": [round(n0, 4), round(e0, 4)],
                                "hook_abs": [round(n0 + hook[0], 4), round(e0 + hook[1], 4)],
                                "altitude_m": round(alt_m, 3)})
            await self.flight.goto_position_ned_and_hold(
                n0 + step_n, e0 + step_e, -alt_m, yaw_deg, HOOK_SETTLE_WAIT_S)
            # Kanca gercekten durana kadar bekle: hareket halindeyken olcmek
            # hareketi hata sanmaktir.
            #
            # BEKLEME YETERLILIGI OLCULUYOR (2026-08-31): 10 x 0.25 s = 2.5 s
            # tavani, olculen 0.831 s'lik sarkac periyodunun ~3 kati olarak
            # secilmisti -- ama o periyot VINC CEKILIYKEN olculdu. Tam
            # salimda ip daha uzun, periyot daha buyuk olabilir. Tavana
            # dayanip dayanmadigimiz artik loglaniyor; dayaniyorsa sabit
            # ayni orani koruyarak yeniden turetilmelidir.
            _settle_polls = 0
            for _ in range(10):
                g = getattr(self.actuator, "seating_geometry", lambda _c: None)(
                    SHAPE_TO_COLOR_RED)
                if g is None or g.rel_speed_mps <= HOOK_SETTLE_MAX_SPEED_MPS:
                    break
                _settle_polls += 1
                await asyncio.sleep(0.25)
            if _settle_polls >= 10:
                logger.warning("[SON_DUZELTME] %d/%d kanca 2.5 s'de DURMADI "
                               "(bekleme tavanina dayandi) -- olcum hareket "
                               "halinde alinmis olabilir.",
                               i, HOOK_ALIGN_MAX_CORRECTIONS)
        logger.warning("[SON_DUZELTME] butce doldu; son yanal %s",
                       f"{last * 1000:.1f} mm" if last is not None else "olculemedi")
        return last

    async def _hook_trace(self, duration_s: float, hz: float = 10.0):
        """Kanca izini ~hz Hz orneklet (SALT OLCUM, Y1 turu 2026-08-31).

        Amac, inisin kancayi ne zaman kaydirdigini UC AYRI ANA ayirmak:
          1. inis SIRASINDA (kanca havada asili)
          2. TEMAS aninda (burun kutuya/zemine deger)
          3. SONRASINDA (arac sabit, kanca yerde)
        Tek bir "inis kaydiriyor" sonucuna indirgememek icin burun DUNYA z'si
        de kaydedilir: temas ani, z izinin duzlestigi noktadir.

        Gorev akisina hicbir sekilde girmez; arka planda calisir, her hata
        yutulur ve iptal edilebilir.
        """
        import time as _t
        t0 = _t.monotonic()
        try:
            while _t.monotonic() - t0 < duration_s:
                off = nose_z = alt = None
                try:
                    off = self.actuator.hook_nose_ned_offset_m()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    hp = self.actuator.get_hook_world_pose()
                    if hp is not None:
                        from core.mission.hook_seating import HOOK_NOSE_OFFSET_M, _rotate
                        pos, quat, _age = hp
                        nose_z = pos[2] + _rotate(quat, (0.0, 0.0, HOOK_NOSE_OFFSET_M))[2]
                except Exception:  # noqa: BLE001
                    pass
                try:
                    alt = await self._current_alt_m()
                except Exception:  # noqa: BLE001
                    pass
                logger.info("[KANCA_IZ] t=%.2f alt=%s off_n=%s off_e=%s nose_z=%s",
                            _t.monotonic() - t0,
                            f"{alt:.3f}" if alt is not None else "-",
                            f"{off[0]:+.4f}" if off else "-",
                            f"{off[1]:+.4f}" if off else "-",
                            f"{nose_z:+.4f}" if nose_z is not None else "-")
                await asyncio.sleep(1.0 / hz)
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 -- olcum gorevi dusuremez
            logger.debug("[KANCA_IZ] ornekleyici hata verdi", exc_info=True)

    async def _current_alt_m(self):
        """Vehicle relative altitude, or None. Telemetry only -- no sim truth."""
        try:
            _lat, _lon, alt = await self.flight.get_global_position()
            return alt
        except Exception:  # noqa: BLE001
            return None

    async def _align_hook_on_receiver(self, aligned_yaw: float, alt_m: float):
        """Close the loop on the REAL hook pose before attempting a pickup.

        Reads the measured hook-nose -> receiver-axis offset straight from
        Gazebo and translates the vehicle by it. Repeats until the lateral
        error is inside HOOK_ALIGN_TARGET_LATERAL_M or the correction budget
        runs out.

        Returns the final measured lateral error in metres, or None if the
        hook pose was never available (in which case the pickup will be
        refused downstream -- a hook we cannot see is a hook we cannot seat).

        Gazebo world is ENU and PX4's local frame is NED with the same axes,
        so a world (dx_east, dy_north) displacement maps to
        (north += dy, east += dx). Only a DELTA is used, so the two frames'
        origins never have to be reconciled.
        """
        last = None
        for i in range(1, HOOK_ALIGN_MAX_CORRECTIONS + 1):
            off = None
            try:
                off = self.actuator.hook_to_receiver_offset_world(SHAPE_TO_COLOR_RED)
            except Exception:  # noqa: BLE001
                off = None
            if off is None:
                logger.warning("[KANCA_HIZA] kanca pozu okunamadi (%d/%d) -- "
                               "duzeltme yapilamiyor.", i, HOOK_ALIGN_MAX_CORRECTIONS)
                return None
            d_east, d_north = off
            last = math.hypot(d_east, d_north)
            if last <= HOOK_ALIGN_TARGET_LATERAL_M:
                logger.info("[KANCA_HIZA] %d/%d yanal %.1f mm -- hedefin (%.0f mm) icinde.",
                            i, HOOK_ALIGN_MAX_CORRECTIONS, last * 1000,
                            HOOK_ALIGN_TARGET_LATERAL_M * 1000)
                return last
            n0, e0, _d = await self.flight.get_position_ned()
            logger.info("[KANCA_HIZA] %d/%d yanal %.1f mm -> arac (kuzey %+.3f, dogu %+.3f) m oteleniyor.",
                        i, HOOK_ALIGN_MAX_CORRECTIONS, last * 1000, d_north, d_east)
            await self.flight.goto_position_ned_and_hold(
                n0 + d_north, e0 + d_east, -alt_m, aligned_yaw, HOOK_ALIGN_SETTLE_S)
        try:
            off = self.actuator.hook_to_receiver_offset_world(SHAPE_TO_COLOR_RED)
            if off is not None:
                last = math.hypot(off[0], off[1])
        except Exception:  # noqa: BLE001
            pass
        logger.warning("[KANCA_HIZA] butce doldu; son yanal %s",
                       f"{last * 1000:.1f} mm" if last is not None else "olculemedi")
        return last

    async def run(self) -> bool:
        logger.info("Görev 3 Faz 1 (Alma) Başlatıldı.")

        mavi_altigen_point = self.position_store.get('MAVI_ALTIGEN')
        if mavi_altigen_point is None:
            raise RuntimeError("Mavi Altıgen konumu bulunamadı! Görev 3 başlatılamaz.")

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
        # GOREV D (2026-09-03): CLIMB-THEN-CRUISE, IKI ASAMADA.
        #
        # Onceki hal tek bir goto_global_position_and_wait(..., 1.5 m) idi ve
        # OLCULDU (PX4 ULog): 50.8 m yol, max |v_xy| 11.92 m/s, pitch max
        # 42.09 derece, 0.9-1.7 m irtifada. Mutlak pozisyon setpoint'i hizi
        # PX4'e birakiyor; tavan MPC_XY_VEL_MAX = 12.0 (olculen 11.92) ve
        # MPC_TILTMAX_AIR = 45 (olculen 42.09).
        #
        # NEDEN IKI CAGRI, TEK DEGIL: motion_fsm'de cruise_alt =
        # max(start_alt, target_alt) oldugu icin CLIMB ve DESCEND ayni bacakta
        # ASLA birlikte tetiklenemez (motion_fsm.py:221-225). Tek bir
        # goto_waypoint(..., 1.5) cagrisi max(1.5,1.5)=1.5 verir, yani duz
        # 1.5 m'de seyir -- istenen "once 3 m'ye cik, sonra yatay" profili
        # cikmaz. motion_fsm DEGISTIRILMEDI; iki cagri istenen profili
        # mevcut mekanizmayla uretiyor:
        #
        #   1) CLIMB (1.5 -> 3.0) -> HOLD -> CRUISE (~50 m @3 m) -> ARRIVAL_HOLD
        #   2) DESCEND (3.0 -> 1.5) -> ARRIVAL_HOLD          (yatay mesafe ~0)
        #
        # Kapi: motion_profile.enabled False iken goto_waypoint zaten eski
        # goto_global_position_and_wait'e duser, yani gercek ucus davranisi
        # degismez.
        converged = await self.centering.goto_waypoint(
            mavi_altigen_point.gps_lat, mavi_altigen_point.gps_lon, GOREV3_CRUISE_ALTITUDE_M)
        if not converged:
            logger.warning("Mavi Altigen'e seyir irtifasinda (%.1f m) navigasyon zaman "
                           "asimina ugradi -- yine de devam ediliyor.", GOREV3_CRUISE_ALTITUDE_M)

        # Hedefin UZERINDE dikey alcalma: yatay mesafe ~0 oldugu icin bu cagri
        # yalnizca DESCEND + ARRIVAL_HOLD calistirir.
        converged = await self.centering.goto_waypoint(
            mavi_altigen_point.gps_lat, mavi_altigen_point.gps_lon, GOREV3_TRANSIT_ALTITUDE_M)
        if not converged:
            logger.warning("Mavi Altigen konumuna navigasyon zaman asimina ugradi -- yine de devam ediliyor.")

        self._publish("GOREV3_PICKUP_STEP", "transit_complete")
        target = await self._locate_target_with_retries()
        if target is None:
            logger.error("Kırmızı Dikdörtgen bulunamadı -- Görev 3 Faz 1 başarısız.")
            return False

        alignment_delta_deg = await self.visibility_strategy.compute_alignment_yaw(target, None)
        current_yaw = await self.flight.get_yaw_deg()
        aligned_yaw = current_yaw + alignment_delta_deg
        logger.info(f"Kırmızı Dikdörtgenin uzun kenarına dik hizalanılıyor: "
                    f"{current_yaw:.1f} -> {aligned_yaw:.1f} derece")
        # BUG FIX (2026-08-21): goto_position_ned_and_hold MUTLAK NED alir
        # (mavsdk_backend_base.py: PositionNedYaw(north,east,down) dogrudan
        # offboard.set_position_ned'e gider, EKF orijinine gore). Bu faz onu
        # goreli govde otelemesiymis gibi cagiriyordu: (0, -0.30, -0.30) "0.3m
        # geride" degil, EVDEN 0.30 m batida demekti. Altigen evden 15 m
        # kuzeyde oldugu icin arac yukun ustunde kalmayip eve donuyordu.
        # Olculdu (mission7, 12:36:22): "30cm pozisyonunda hedef gorunurlugu
        # dogrulanamadi" -- hedef 15 m uzaktaydi; ve fazin son testi
        # ("Kirmizi Dikdortgen goruntude yok -> Yuk Alma Basarili") tam da
        # hedeften UZAKLASILDIGI icin gecti. Artik her hedef, o anki NED
        # konumundan govde ötelemesiyle hesaplaniyor -- log mesajlarinin
        # zaten iddia ettigi davranis.
        n0, e0, _d0 = await self.flight.get_position_ned()
        _c = math.cos(math.radians(aligned_yaw))
        _s = math.sin(math.radians(aligned_yaw))

        def _body_to_ned(forward_m: float, right_m: float):
            return (n0 + forward_m * _c - right_m * _s,
                    e0 + forward_m * _s + right_m * _c)

        await self.flight.goto_position_ned_and_hold(
            n0, e0, -GOREV3_TRANSIT_ALTITUDE_M, aligned_yaw, 2.0)

        # GERI CEKILME KALDIRILDI (2026-08-21) ve ortalama GORUS DOSTU bir
        # irtifaya tasindi. Olculdu (mission17):
        #
        #   16:25:43,257 [CENTERING] KIRMIZI_DIKDORTGEN 1/150 dx=+162px dy=+374px
        #   16:25:43,379 [LOW_ALT_OPEN_LOOP_DESCENT] goruntu 0.38m'de kayboldu
        #   16:25:43,640 [LOW_ALT_OPEN_LOOP_DESCENT] 0.341m'ye ulasildi
        #
        # Yeniden ortalama 390 ms'de dondu, yani hic ortalamadi. Sebep zincirleme:
        # GOREV3_RETREAT_DISTANCE_M=0.30 hedefi 0.30 m geriye atiyor, ardindan
        # 0.30 m'ye inildiginde kadraj yalnizca 0.71 x 0.53 m kaliyor, hedef
        # kenara/disari dusuyor ve kontrolcu acik cevrim alcalmaya geciyor.
        # dy=+374px zaten 0.208 m demek -- kamera-kanca ofsetiyle ayni mertebe.
        #
        # Geri cekilme, sabit uzunlukta sarkan bir ipi yukun uzerinden
        # SURUKLEMEK icin tasarlanmisti; vincle dogru hareket supurmek degil
        # hedefin uzerinde durup ipi salmak, yani bu adimin artik bir islevi
        # yok. Simdi: gorus dostu irtifada ortala -> kanca ofsetini orada
        # uygula -> yalnizca DIKEY in. Yatay is bittikten sonra iniyoruz, yani
        # kadrajin daralmasi artik onemli degil.
        self._publish("GOREV3_PICKUP_STEP", "yaw_aligned",
                      data={"aligned_yaw_deg": round(aligned_yaw, 2)})
        logger.info(f"{HOOK_ALIGN_ALTITUDE_M}m irtifada (gorus dostu) hedefe ortalanıyor...")
        centered = await self.centering.go_to_and_center(
            "KIRMIZI_DIKDORTGEN", altitude_m=HOOK_ALIGN_ALTITUDE_M)
        if not centered:
            logger.warning("Hizalama irtifasinda ortalama yakinsamadi -- devam ediliyor (best-effort).")

        # Bu 30cm'lik pozisyonda hedefin hâlâ görüntüde olduğunu N kare
        # boyunca doğrula (Görev 3 Rapor: "bu 30 cm'de görüntü işleme ile
        # aktif görmek istiyorum") -- best-effort görünürlük onayı, tam
        # yeniden ortalama değil (araç zaten hizalı ve konumlanmış).
        visible_frames = 0
        for _ in range(GOREV3_PICKUP_VISIBILITY_CONFIRM_FRAMES * 3):
            try:
                await self.visibility_strategy.locate_target(self.detector, None)
                visible_frames += 1
                if visible_frames >= GOREV3_PICKUP_VISIBILITY_CONFIRM_FRAMES:
                    break
            except RuntimeError:
                visible_frames = 0
            await asyncio.sleep(OFFBOARD_SETPOINT_INTERVAL_S)
        if visible_frames < GOREV3_PICKUP_VISIBILITY_CONFIRM_FRAMES:
            logger.warning("30cm pozisyonunda hedef görünürlüğü doğrulanamadı -- devam ediliyor (best-effort).")

        # KANCA HIZALAMASI (2026-08-21): kamera govde +0.35'te, kanca -0.35'te,
        # yani aralarinda 0.70 m var. Ortalamayi kamera yapiyor, dolayisiyla
        # hedef ORTALANDIGINDA kanca hala 0.35 m geride. Kancayi hedefin
        # uzerine getirmek icin arac 0.35 m ILERI kayar: kanca = arac +
        # govde(-0.35,0) oldugundan, arac hedef + govde(+0.35,0)'a gidince
        # kanca tam hedefe oturur. Hedef bu kaymada kameradan cikar; ayni
        # "olc, sonra korlemesine uygula" deseni payload birakmada da
        # kullaniliyor (bkz. [AIM_OFFSET_APPLIED]/[MOUNT_VECTOR_MEASURED]).
        #
        # Geri-cekil/ileri-git supurmesi kaldirildi: o koreografi sabit
        # uzunlukta sarkan bir ipi yukun uzerinden SURUKLEMEK icindi. Vincle
        # dogru hareket supurmek degil, hedefin uzerinde durup ipi salmak.
        # ALCAK IRTIFADA YENIDEN ORTALA (2026-08-21). Asagidaki oteleme
        # KOR: hedef, arac ilerledigi anda kameradan cikar. Dolayisiyla
        # otelemenin dogrulugu, BASLADIGI konumun dogrulugu kadardir.
        # Onceden baslangic noktasi 1.5 m'de yapilmis ortalamadan sonra bir
        # geri-cekilme ve bir alcalma gecirmis oluyordu; hatalar birikiyordu.
        # Olculdu: kanca yakalama alani 2.7 cm iken mission12 1. denemede
        # tuttu, mission14'te 3 denemenin hicbiri tutmadi.
        #
        # Burada tazelenmis bir ortalama, otelemeyi sifira yakin hatadan
        # baslatir. 0.30 m'de kadraj 0.71 x 0.53 m, yuk 0.14 x 0.05 m --
        # hedef rahatlikla goruste.
        #
        # NOT: gorus hatasini yanlamak (go_to_and_center'in aim_offset_body_m
        # parametresi) BILEREK kullanilmiyor: PHASE 13 D3 o yolu olcup
        # reddetti -- hedefi kadraj kenarina itip olcumun kendisini
        # bozuyordu. 0.175 m ofset 0.30 m'de 315 px eder, ayni tuzak.
        # Oteleme tazelenmis konumdan hesaplanmali.
        n0, e0, _d0 = await self.flight.get_position_ned()
        _c = math.cos(math.radians(aligned_yaw))
        _s = math.sin(math.radians(aligned_yaw))

        logger.info(f"Kanca hedefin uzerine getiriliyor (govde +{HOOK_BODY_OFFSET_FORWARD_M}m ileri)...")
        _hn, _he = _body_to_ned(HOOK_BODY_OFFSET_FORWARD_M, 0.0)
        # Once YALNIZCA yatay: hizalama irtifasinda otele.
        await self.flight.goto_position_ned_and_hold(
            _hn, _he, -HOOK_ALIGN_ALTITUDE_M, aligned_yaw, 4.0)
        # Sonra YALNIZCA dikey: ayni yatay noktada alma irtifasina in.
        # HIZALAMA IRTIFASINA in, ALMA irtifasina degil.
        #
        # Kanca ofseti uygulandiktan sonra kamera yuvadan 0.260 m ileridedir
        # (0.175 kanca + 0.085 kamera kolu). 0.30 m'de bu, yuku kadrajin
        # 501 px asagisina atar -- yari-kadraj 480 px, yani DISARI. Olculdu
        # (2026-08-27 kosusu): tam burada "Kirmizi Dikdortgen yeniden
        # bulunamadi" ile faz dustu, cunku asagidaki goruntu kontrolu
        # bakabilecegi bir yuk bulamadi.
        #
        # 0.90 m'de yuva 160 px'te, yari-kadrajin %33'u. Hem asagidaki
        # goruntu dogrulamasi hem de onu izleyen gorsel hizalama ayni
        # irtifada calisir; alma irtifasina inis hizalama bittikten SONRA.
        self._publish("GOREV3_PICKUP_STEP", "hook_offset_applied",
                      data={"forward_m": HOOK_BODY_OFFSET_FORWARD_M})
        logger.info(f"{HOOK_VISUAL_ALIGN_ALTITUDE_M}m hizalama irtifasina dikey iniliyor...")
        await self.flight.goto_position_ned_and_hold(
            _hn, _he, -HOOK_VISUAL_ALIGN_ALTITUDE_M, aligned_yaw, 5.0)

        # GORUNTU ILE HIZA DOGRULAMASI (operator, 2026-08-23): "kancanin
        # yukun ortasina temas ettigini goruntu isleme ile algila".
        # Kanca yukun ortasindayken yuk, kare merkezinin
        # HOOK_BODY_OFFSET_FORWARD_M * f / irtifa kadar gerisinde gorunmeli.
        # Sapma buradan metre cinsinden okunuyor.
        #
        # Yuk kamerada HIC yoksa korlemesine devam etmek anlamsiz: 0.30 m'de
        # kadraj yalnizca 0.71 x 0.53 m, kucuk bir hata yuku disari atiyor.
        # O durumda 1 m yukselip yeniden bulunur ve kancaya gore ortalanir.
        offset_m, visible = await self._rect_pixel_offset()
        if not visible:
            if await self._reacquire_by_climbing(aligned_yaw):
                n0, e0, _d0 = await self.flight.get_position_ned()
                _c = math.cos(math.radians(aligned_yaw))
                _s = math.sin(math.radians(aligned_yaw))
                _hn, _he = _body_to_ned(HOOK_BODY_OFFSET_FORWARD_M, 0.0)
                await self.flight.goto_position_ned_and_hold(
                    _hn, _he, -HOOK_VISUAL_ALIGN_ALTITUDE_M, aligned_yaw, 5.0)
                offset_m, visible = await self._rect_pixel_offset()
            if not visible:
                logger.error("Kirmizi Dikdortgen yeniden bulunamadi -- Görev 3 Faz 1 başarısız.")
                return False
        # KALIBRASYON: goruntu tahmini ile simulator gercegini YAN YANA yaz.
        # 2026-08-23 kosusunda ikisi ayristi -- goruntu 5.7 cm, gercek 0.7 cm.
        # Sebebi henuz bilinmiyor (irtifa kaynagi dogru cikti:
        # get_global_position()[2] zaten relative_altitude_m; kamera da
        # gercekten govde +0.085'te). Tahminle duzeltmek yerine olcuyoruz:
        # birkac kosunun verisi sistematik bir sapma gosterirse duzeltilir.
        # KARAR MERCII ARTIK IKISI DE DEGIL: alma, kancanin GERCEK Gazebo
        # pozundan hesaplanan OTURMA GEOMETRISIYLE karara baglaniyor
        # (core/mission/hook_seating.py). Buradaki iki sayi yalnizca
        # goruntunun guvenilirligini olcmek icin yan yana yaziliyor.
        truth_gap = None
        try:
            # Gercek kanca pozundan olculen yanal hata (magnet DEGIL: bu
            # yapida manyetik kuvvet simule edilmiyor).
            truth_gap = self.actuator.hook_lateral_error_m(SHAPE_TO_COLOR_RED)
        except Exception:  # noqa: BLE001
            pass
        try:
            _la, _lo, _alt_now = await self.flight.get_global_position()
        except Exception:  # noqa: BLE001
            _alt_now = None
        logger.info("[HIZA_KALIBRASYON] goruntu=%s  gercek=%s  irtifa=%s",
                    f"{offset_m * 100:.1f} cm" if offset_m is not None else "yok",
                    f"{truth_gap * 100:.1f} cm" if truth_gap is not None else "yok",
                    f"{_alt_now:.2f} m" if _alt_now is not None else "yok")

        if offset_m is not None:
            if offset_m <= HOOK_VISION_ALIGN_TOLERANCE_M:
                logger.info("[GORUNTU] kanca yukun ortasinda: sapma %.1f cm (tol %.0f cm).",
                            offset_m * 100, HOOK_VISION_ALIGN_TOLERANCE_M * 100)
            else:
                logger.warning("[GORUNTU] kanca yukun ortasinda DEGIL: sapma %.1f cm "
                               "(tol %.0f cm) -- alma yine de denenecek; oturma kapisi "
                               "gercek kanca pozundan kendi kararini veriyor.",
                               offset_m * 100, HOOK_VISION_ALIGN_TOLERANCE_M * 100)

        # KAPALI CEVRIM KANCA HIZALAMASI (Blocker 1, 2026-08-26).
        # Buraya kadar her sey acik cevrimdi: kamera hedefi ortalar, arac
        # govde ofseti kadar oteler, iner. Kanca ipin ucunda oldugu icin o
        # zincirin sonunda nerede oldugu OLCULMEDEN bilinemez. Simdi
        # olculuyor ve duzeltiliyor; oturma kapisi da ayni pozu kullaniyor.
        # VINCI ONCE SAL, SONRA HIZALA (2026-08-26 canli kosusu).
        #
        # Ilk surumde sira tersti: once hizala, sonra alma mekanizmasini
        # cagir -- ve alma mekanizmasi ilk isi olarak vinci 0.40 m saliyordu.
        # Yani hizalama kanca HAVADAYKEN (vinc cekili, base_link-0.133)
        # olculuyor, sonra kanca 30 cm asagi iniyor, o inis sirasinda
        # salliniyor ve yukun YANINA konuyordu. Olculdu: hizalama 9.0 mm'ye
        # yakinsadi, ardindan oturma kapisi 12 s boyunca 38-103 mm gordu ve
        # ucunde de hakli olarak reddetti.
        #
        # Ip sarkan bir kancada olcumun BIRAKILACAGI yerde yapilmasi gerekir.
        # Vinc simdi once saliniyor, kanca guverteye/zemine oturuyor, ve
        # duzeltmeler kancanin gercek calisma pozisyonunu suruyor.
        # VINC HIZALAMA BOYUNCA TOPLU KALIR -- olculdu, 2026-08-27.
        #
        # Onceki sira (once sal, sonra hizala) gorsel hizalamayi 5.1 mm'ye
        # yakinsatiyordu ve ardindan oturma kapisi 222 mm olcuyordu. Sebep
        # gorus degil, ip: vinc acikken alma irtifasina inilince kanca
        # guverteye/zemine dayanir ve inisin geri kalani ipte GEVSEKLIK olur.
        # Bu dosyanin ve arac SDF'sinin kendi notlari gevsekligin kancayi
        # devirdigini zaten kaydediyor (olculen 49 derece). Devrilen kanca
        # hizalandigi yerde durmaz.
        #
        # Toplu vincle kanca govdenin (-0.090, 0) altinda dik sarkar ve
        # nerede oldugu bellidir. Hizalama orada bitirilir, dikey inilir
        # (dikey inis yatay hizayi bozmaz), ve vinc EN SON salinir; boylece
        # payout saf dikey bir harekettir.
        # Zaten hizalama irtifasindayiz (yukaridaki inis oraya yapildi); bu
        # yalnizca savunmaci bir teyit tutusu.
        await self.flight.goto_position_ned_and_hold(
            _hn, _he, -HOOK_VISUAL_ALIGN_ALTITUDE_M, aligned_yaw, 2.0)

        # GORSEL HIZALAMA (2026-08-27). Alici artik KAMERADAN olculuyor.
        #
        # Onceki surum yuvanin konumunu dogrudan Gazebo'dan (ground truth)
        # aliyordu. O, gercek bir dronede var olmayan bir bilgi: gorev artik
        # yuvayi goruntuden buluyor (core/detection/receiver_detector.py,
        # 66 etiketli karede alma irtifasinda 0.68 mm ortalama merkez hatasi),
        # ve hatayi kancanin GERCEK pozuna karsi kapatiyor.
        #
        # Neden piksel farki degil de metre farki: kanca kameranin ALTINDA,
        # yuva ise YERDE; iki farkli derinlik. Goruntude ust uste getirmek
        # 1.2 m'lik bir suzulmede ~0.2 m yanilir ve kancanin O45 govdesi
        # 0.65 m'nin altinda yuvanin agzini zaten kapatir. Ayrinti:
        # core/mission/visual_alignment.py.
        aligner = VisualHookAligner(
            get_frame=self.camera.get_frame,
            get_alt_m=lambda: self._current_alt_m(),
            get_yaw_deg=self.flight.get_yaw_deg,
            get_position_ned=self.flight.get_position_ned,
            get_hook_ned_offset=getattr(self.actuator, "hook_nose_ned_offset_m",
                                        lambda: None),
            goto_ned_and_hold=lambda n, e, alt, yaw: self.flight.goto_position_ned_and_hold(
                n, e, -alt, yaw, 1.2),
            color=SHAPE_TO_COLOR_RED,
            # SALT OLCUM (mekanizma 2c): gorus tahmininin yaninda gercek
            # yanal hatayi da kaydeder, karar akisina girmez.
            get_truth_lateral_m=lambda: getattr(
                self.actuator, "hook_lateral_error_m", lambda _c: None)(SHAPE_TO_COLOR_RED))
        vis = await aligner.align(HOOK_VISUAL_ALIGN_ALTITUDE_M, aligned_yaw,
                                  tolerance_m=HOOK_VISUAL_ALIGN_TOLERANCE_M)
        logger.info("[GORSEL_HIZA] %s: son hata=%s, %d iterasyon, %d tespit, "
                    "%.3f m hareket", vis.reason,
                    f"{vis.final_error_m * 1000:.1f} mm" if vis.final_error_m is not None else "yok",
                    vis.iterations, vis.detections, vis.travel_m)
        # GORUS KAYBOLURSA KOR DEVAM ETME. Ama "yakinsamadi" ile "goremedim"
        # ayni sey degil: elde saglam bir yuva olcumu varsa ve artik hata
        # asagidaki duzeltmenin kapatabilecegi buyuklukteyse devam etmek
        # dogru -- son sozu zaten oturma kapisi soyluyor.
        usable = vis.converged or (
            vis.receiver_ned is not None
            and vis.final_error_m is not None
            and vis.final_error_m <= HOOK_VISUAL_ALIGN_MAX_USABLE_M)
        if not usable:
            logger.error("Görsel hizalama kullanilabilir bir olcum vermedi (%s, "
                         "hata=%s) -- Görev 3 Faz 1 GUVENLI SEKILDE durduruluyor.",
                         vis.reason,
                         f"{vis.final_error_m * 1000:.1f} mm" if vis.final_error_m else "yok")
            return False
        if not vis.converged:
            logger.warning("Görsel hizalama yakinsamadi (%s) ama yuva olcumu "
                           "saglam (artik %.1f mm) -- alma irtifasindaki "
                           "duzeltmeyle devam ediliyor.",
                           vis.reason, vis.final_error_m * 1000)
        final_lateral = vis.final_error_m
        recv_ned = vis.receiver_ned
        logger.info("[GORSEL_HIZA] yuva GORUNTUDEN olculdu: NED=(%.3f, %.3f)",
                    recv_ned[0], recv_ned[1]) if recv_ned else None

        # DIKEY IN, sonra VINCI SAL, sonra GORUS OLCUMUNE GORE SON DUZELTME.
        #
        # Kamera, kancanin yuvaya ULASTIGI irtifada yuvayi GOREMEZ: kanca
        # yuvanin ustundeyken kamera 0.26 m ileridedir ve 0.30 m'de bu 501 px
        # asagi duser, yari-kadraj ise 480 px. Olculdu: gorev orada 30
        # yinelemede 7 tespit yapabildi ve hakli olarak reddetti.
        #
        # Bu yuzden gorus YUKARIDA olcer, asagida UYGULANIR. Yuva hareket
        # etmez, dolayisiyla iyi olculmus bir konum sonradan kullanilabilir.
        # Son duzeltme, saklanan GORUS konumuna karsi kancanin GERCEK pozuyla
        # kapatilir -- ve sonucu her halukarda oturma kapisi dogrular.
        # SIRALAMA (2026-08-31): SAL -> HAVADA DUZELT -> DIKEY IN.
        #
        # Onceki sira "dikey in -> sal -> duzelt" idi ve iki olcum onu
        # reddediyor:
        #
        #   a) Salim hatayi aciyor. Kayitli olcum (bu dosyanin 100-113
        #      satirlari): payout ONCESI yanal 14.3 mm / egim 0.2 derece,
        #      payout SONRASI 64.6 mm / 33.3 derece.
        #   b) Salimdan SONRA kanca guverte/zemin uzerinde DINLENIYOR ve
        #      duzeltme onu takip ettiremiyor. Olculdu (2026-08-31, uc temiz
        #      kosu): arac komut yonunde kumulatif ~70 mm oteledi, kanca ise
        #      BAGIMSIZ olarak 28 / 49 / 189 mm kaydi. Ayni kontrol yasasi
        #      kanca HAVADAYKEN (gorsel hizalama fazi, vinc cekili) 18.6 /
        #      27.3 / 13.3 mm'ye yakinsiyor.
        #
        # Yani sorun kontrol yasasinda ya da olcumde degil (ikisi de dogru,
        # hook_nose_ned_offset_m gercek Gazebo pozunu okuyor); YANLIS
        # REJIMDE calistirilmasinda. Cozum rejimi degistirmek:
        #
        #   1. Vinci burada, HALA YUKARIDAYKEN sal. Kanca ~0.5 m'de serbest
        #      asili kalir, yani salimin acdigi hata duzeltilebilir bir anda
        #      olusur.
        #   2. Duzeltmeyi kanca SERBESTKEN kos -- calistigi kanitlanmis rejim.
        #   3. Sonra SAF DIKEY in. Yanal surukleme hic olmaz; dikey inis
        #      sarkaci yatay otelemeye kiyasla cok daha az uyarir.
        #
        # hook_payout_m() DEGISMEDI: salim yine SON irtifaya gore hesaplanir,
        # kanca yalnizca inis tamamlanana kadar daha yuksekte asili kalir.
        # SALIM HESABI TEK KAYNAKTAN: actuator.extend_winch_for(). Gorev
        # katmani artik hook_payout_m'i kendisi cagirmiyor; hedef irtifayi
        # verir, hesabi aktuator yapar -- alma anindaki yeniden hesapla ayni
        # kod yolundan gecer.
        _extend = getattr(self.actuator, "extend_winch_for", None)
        if _extend is not None:
            _payout_alt = await self._current_alt_m()
            logger.info("Vinc salinacak (hedef irtifa %.2f m icin) -- ARAC HALA "
                        "%.2f m'de, kanca serbest asili kalacak.",
                        GOREV3_DESCENT_ALTITUDE_M,
                        _payout_alt if _payout_alt is not None else float("nan"))
            await _extend(GOREV3_DESCENT_ALTITUDE_M)
            await asyncio.sleep(HOOK_PAYOUT_SETTLE_S)

        if recv_ned is not None:
            self._publish("GOREV3_PICKUP_STEP", "correction_airborne_start")
            corrected = await self._settle_hook_onto(recv_ned, aligned_yaw,
                                                     HOOK_VISUAL_ALIGN_ALTITUDE_M)
            if corrected is not None:
                final_lateral = corrected

        _hn, _he, _ = await self.flight.get_position_ned()
        # KANCA DENGE KONUMU: INIS ONCESI. Mekanizma 2b olcumu (2026-08-31).
        # Duzeltme dongusu kancayi 0.94 m'de hizaliyor, oturma kapisi ise
        # 0.33 m'de olcuyor. Aradaki sistematik kayma olculdu (+22.7 / +43.1
        # mm) ve bunun yalnizca %22-51'i aracin kendi kaymasiyla aciklandi.
        # Kalan terim "kancanin ARACA GORE denge konumu irtifayla degisiyor"
        # hipotezi; onu kanitlamak ya da curutmek icin ayni buyuklugu inisin
        # IKI YANINDA olcup karsilastirmak gerekiyor.
        try:
            _off_before = getattr(self.actuator, "hook_nose_ned_offset_m", lambda: None)()
        except Exception:  # noqa: BLE001 -- salt olcum, gorevi dusuremez
            _off_before = None
        _alt_before = await self._current_alt_m()
        logger.info("[KANCA_DENGE] INIS ONCESI irtifa=%s kanca_ofset=%s",
                    f"{_alt_before:.3f} m" if _alt_before is not None else "yok",
                    f"({_off_before[0]:+.4f}, {_off_before[1]:+.4f})" if _off_before else "yok")
        # Y1 OLCUM TURU: iz, inisin BASINDAN ilk alma denemesinin sonuna
        # kadar kesintisiz akar ki uc an (inis / temas / sonrasi) tek bir
        # zaman ekseninde ayirt edilebilsin.
        _trace = asyncio.create_task(self._hook_trace(45.0))
        logger.info("Hizalandi -- %.2f m alma irtifasina SAF DIKEY iniliyor "
                    "(yanal hareket yok).", GOREV3_DESCENT_ALTITUDE_M)
        self._publish("GOREV3_PICKUP_STEP", "vertical_descent_start",
                      data={"from_m": HOOK_VISUAL_ALIGN_ALTITUDE_M,
                            "to_m": GOREV3_DESCENT_ALTITUDE_M,
                            "lateral_before_mm": (round(final_lateral * 1000, 1)
                                                  if final_lateral is not None else None)})
        await self.flight.goto_position_ned_and_hold(
            _hn, _he, -GOREV3_DESCENT_ALTITUDE_M, aligned_yaw, 6.0)
        # Hizalama araci otelemis olabilir; tutma noktasi tazelenmeli.
        _hn, _he, _ = await self.flight.get_position_ned()

        logger.info("Yük alma mekanizması aktifleşiyor...")
        # KONUMU ALMA BOYUNCA TUT (2026-08-21). Yukaridaki
        # goto_position_ned_and_hold, alma baslamadan ONCE doner; alma ise
        # 3 denemede ~50 s surebiliyor. O sure boyunca hicbir setpoint
        # yayinlanmadigi icin PX4 Offboard'dan dusuyor ve arac kayiyor.
        # Olculdu (mission15, magnet mesafesi denemeler boyunca):
        #     1. deneme  4.1 cm   <- 4.0 cm esigin 1 mm disi
        #     2. deneme  9.8 cm
        #     3. deneme 11.1 cm
        # Yani ilk deneme neredeyse tutmus, sonra arac surekli uzaklasmis.
        # Setpoint akisini almaya PARALEL surdurmek bu kaymayi kaldirir.
        # TUTMA GOREVI, yeniden hizalama sirasinda DURDURULUP yeni konumda
        # yeniden baslatilabilsin diye bir kapta tutuluyor: iki ayri gorev
        # ayni anda setpoint yayinlarsa PX4 celiskili hedefler alir.
        _hold_ref = {}

        def _start_hold(n_, e_):
            _hold_ref["t"] = asyncio.create_task(self.flight.goto_position_ned_and_hold(
                n_, e_, -GOREV3_DESCENT_ALTITUDE_M, aligned_yaw, PICKUP_HOLD_S))

        async def _stop_hold():
            t = _hold_ref.pop("t", None)
            if t is None:
                return
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

        async def _on_retry(attempt: int):
            """Vinc cekili (kanca havada) -- duzeltmeyi yeniden kos."""
            if recv_ned is None:
                return
            await _stop_hold()
            logger.info("[YENIDEN_HIZA] deneme %d oncesi, kanca havada -- "
                        "duzeltme yeniden kosuluyor", attempt + 1)
            corrected = await self._settle_hook_onto(recv_ned, aligned_yaw,
                                                     GOREV3_DESCENT_ALTITUDE_M)
            logger.info("[YENIDEN_HIZA] deneme %d icin yeni yanal: %s",
                        attempt + 1,
                        f"{corrected * 1000:.1f} mm" if corrected is not None else "olculemedi")
            self._publish("GOREV3_REALIGN_BETWEEN_ATTEMPTS",
                          f"deneme {attempt + 1}",
                          data={"next_attempt": attempt + 1,
                                "lateral_mm": (round(corrected * 1000, 1)
                                               if corrected is not None else None)})
            n2, e2, _ = await self.flight.get_position_ned()
            _start_hold(n2, e2)

        _start_hold(_hn, _he)
        # Vinc salimi artik IRTIFADAN turetiliyor (gz_payload_actuator.
        # hook_payout_m). Irtifa okunamazsa None gecilir ve actuator eski
        # sabit salima duser -- davranis bilinmeyen irtifada degismez.
        # KANCA DENGE KONUMU: INIS SONRASI. Yukaridaki olcumun esi.
        try:
            _off_after = getattr(self.actuator, "hook_nose_ned_offset_m", lambda: None)()
        except Exception:  # noqa: BLE001 -- salt olcum, gorevi dusuremez
            _off_after = None
        _pick_alt = await self._current_alt_m()
        if _off_before is not None and _off_after is not None:
            _d_n = _off_after[0] - _off_before[0]
            _d_e = _off_after[1] - _off_before[1]
            _d = math.hypot(_d_n, _d_e)
            logger.info("[KANCA_DENGE] INIS SONRASI irtifa=%s kanca_ofset=(%+.4f, %+.4f)"
                        "  ->  DEGISIM=(%+.1f, %+.1f) mm  |%.1f mm|",
                        f"{_pick_alt:.3f} m" if _pick_alt is not None else "yok",
                        _off_after[0], _off_after[1], _d_n * 1000, _d_e * 1000, _d * 1000)
            self._publish("GOREV3_HOOK_EQUILIBRIUM_SHIFT",
                          f"{_d * 1000:.1f} mm",
                          data={"alt_before_m": (round(_alt_before, 3)
                                                 if _alt_before is not None else None),
                                "alt_after_m": (round(_pick_alt, 3)
                                                if _pick_alt is not None else None),
                                "offset_before": [round(_off_before[0], 4), round(_off_before[1], 4)],
                                "offset_after": [round(_off_after[0], 4), round(_off_after[1], 4)],
                                "shift_mm": round(_d * 1000, 1)})
        self._publish("GOREV3_PICKUP_STEP", "pickup_attempt_start",
                      data={"altitude_m": (round(_pick_alt, 3)
                                           if _pick_alt is not None else None)})
        try:
            picked = await self.actuator.activate_pickup_mechanism(
                altitude_m=_pick_alt, on_retry=_on_retry)
        finally:
            await _stop_hold()
        _trace.cancel()
        try:
            await _trace
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        _report = getattr(self.actuator, "last_pickup_report", None)
        if _report is not None:
            from core.telemetry.events import Severity as _Sev
            # Severity uyesi WARN'dir, WARNING DEGIL (events.py:31). Ilk
            # yazimda WARNING kullanildi ve bu, _publish'in kendi try/except'i
            # DISINDA, cagri yerinde AttributeError'a yol acti -- olay hic
            # yayinlanmadi. 2026-08-31 taramasinin 0.04 kosusunda yakalandi.
            self._publish("HOOK_SEATING_RESULT",
                          "seated" if picked else "not_seated",
                          data=_report,
                          severity=_Sev.INFO if picked else _Sev.WARN)
        # THIRD MISSION SERVO
        # BUG FIX (2026-08-21): donus degeri ATILIYORDU. Mekanizma simule bir
        # placeholder oldugu surece zararsizdi (hep True donuyordu), ama artik
        # gercek kancayi suruyor ve basarisiz olabiliyor. Olculdu (mission10):
        # kanca 3 denemede de yuku alamadi, faz yine de devam etti ve
        # "TUM GOREVLER BASARIYLA TAMAMLANDI" raporlandi -- hicbir yuk
        # tasinmadan. Yuk alinamadiysa faz basarisizdir.
        if not picked:
            logger.error("Yük alma mekanizması yükü alamadı -- Görev 3 Faz 1 başarısız.")
            return False

        # Tirmanistan ONCEKI yuk irtifasi -- asagidaki dogrulama "yuk aracla
        # birlikte yukseldi mi" sorusunu buna gore cevapliyor.
        payload_z_before = self.actuator.payload_altitude_m(SHAPE_TO_COLOR_RED)

        for alt in GOREV3_PICKUP_VERIFY_CLIMB_STEPS_M:
            logger.info(f"Yükseliniyor: {alt}m")
            # BUG FIX (2026-08-21): (0, 0) mutlak NED'de EV demek. Bu dongu
            # "yukselmek" isterken araci her adimda eve ucuruyordu; mission10
            # bu yuzden evden 48 m otede indi ve fazin son testi ("Kirmizi
            # Dikdortgen goruntude yok") hedeften uzaklasildigi icin gecti.
            # Yalnizca irtifa degismeli, yatay konum korunmali.
            _vn, _ve, _ = await self.flight.get_position_ned()
            await self.flight.goto_position_ned_and_hold(_vn, _ve, -alt, aligned_yaw, 2.0)
            # ADR-010 P3: `self.detector` is a FeedDetector, which answers
            # from the shared DetectionFeed and ignores the frame -- Görev 3
            # must not be a second detect() caller (see vision_runtime.py).
            # None is passed rather than a freshly grabbed frame precisely to
            # make that explicit: the frame this phase could grab is NOT the
            # frame the streak logic was advanced on.
            detections = await self.detector.detect(None)
            still_visible = any(d.shape_type == "KIRMIZI_DIKDORTGEN" for d in detections)
            if still_visible:
                logger.warning(f"{alt}m irtifada Kırmızı Dikdörtgen hâlâ görüntüde.")

        logger.info("Doğrulama kontrolü yapılıyor (son irtifa)...")
        detections = await self.detector.detect(None)
        still_visible = any(d.shape_type == "KIRMIZI_DIKDORTGEN" for d in detections)

        # HUKUM TERSINE CEVRILDI (olculdu, 2026-08-23 kosusu).
        #
        # Eski test: "yuk alindiysa yerden kalkar, dolayisiyla kamerada
        # GORUNMEZ" -- ve goruntude kalmasi basarisizlik sayiliyordu. Bu,
        # yuk YERDE kalirken dogruydu. Artik yuk KANCADA asili ve kanca
        # govdenin altinda: arac yukseldikce yuk de birlikte yukseliyor ve
        # kamerada gorunmeye DEVAM ediyor. Yani eski test, basarinin ta
        # kendisini basarisizlik sayiyordu:
        #     23:35:25 [HOOK] KILITLENDI (payload_red) -- vinc acik, yuk ipte
        #     23:35:34 Kirmizi Dikdortgen hala goruntude! Alma basarisiz.
        #
        # Yeni hukum iki gercek kanita dayaniyor:
        #   1) HookAttachSystem'in /hook/state onayi (fixed joint kuruldu)
        #   2) yukun aracla BIRLIKTE yukselmis olmasi
        # Eski gozlem SILINMEDI, yalnizca hukum olmaktan cikarilip log'a
        # dusuruldu -- yuk yerde kalsaydi gorunmemesi hala anlamli bir
        # isaret, ama tek basina karar verdirmiyor.
        attached = self.actuator.is_hook_attached()
        lifted_m = None
        if payload_z_before is not None:
            z_now = self.actuator.payload_altitude_m(SHAPE_TO_COLOR_RED)
            if z_now is not None:
                lifted_m = z_now - payload_z_before

        logger.info("[ALMA_DOGRULAMA] kanca_kilitli=%s  yuk_yukseldi=%s  "
                    "dikdortgen_goruntude=%s (bu sonuncusu artik yalnizca gozlem)",
                    attached,
                    f"{lifted_m:+.2f} m" if lifted_m is not None else "olculemedi",
                    still_visible)

        if not attached:
            logger.warning("Kanca kilitli degil -- Alma başarısız.")
            return False
        if lifted_m is not None and lifted_m < PICKUP_LIFT_CONFIRM_M:
            logger.warning("Yuk aracla birlikte yukselmedi (%.2f m < %.2f m) -- "
                           "Alma başarısız.", lifted_m, PICKUP_LIFT_CONFIRM_M)
            return False

        logger.info("Yük Alma Başarılı (kanca kilitli%s).",
                    f", yuk {lifted_m:+.2f} m yukseldi" if lifted_m is not None else "")
        return True
