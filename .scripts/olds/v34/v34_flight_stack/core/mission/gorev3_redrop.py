import asyncio
import math
from core.config.parameters import GOREV3_REDROP_REST_HEIGHT_M
import logging
from core.interfaces.i_flight_backend import IFlightBackend
from core.interfaces.i_payload_actuator import IPayloadActuator
from core.navigation.centering_controller import CenteringController
from core.position_log.position_store import PositionStore
from core.config.parameters import GOREV3_DESCENT_ALTITUDE_M
from core.mission.visual_placement import (
    VisualPlacementAligner, carried_payload_ned_offset, settle_onto_ned,
)
from core.config.parameters import GOREV3_TRANSIT_ALTITUDE_M

# YERLESTIRME HIZALAMA IRTIFASI. Birakma irtifasinda (0.30 m) hizalanamaz, ve
# bu bir ayar meselesi degil, kadraj geometrisi:
#
#   arac 0.30 m -> kamera 0.35 m -> kadraj 0.83 x 0.62 m
#   Kirmizi Ucgen 1.00 m kenar   -> kadrajin %121'i, YANI SIGMIYOR
#
# Kirpilmis bir seklin centroid'i o seklin merkezi DEGILDIR. Olculdu
# (2026-08-27 gorevi): hizalayici o parcaya karsi "44.4 mm" raporladi ve yuk
# gercek merkezden 89.7 cm oteye dustu. Ayni kosuda merkezleme de zaten
# 0.95 m'de goruntuyu kaybedip acik cevrime dusmustu.
#
# 1.5 m'de ucgen kadraj genisliginin %27'si -- tamamen iceride ve tespit
# saglam. Olcum orada yapilir, hedefin MUTLAK konumu saklanir, sonra alcalinip
# saklanan hedefe gore KANCAYA REFERANSLI son duzeltme yapilir.
GOREV3_PLACE_ALIGN_ALTITUDE_M: float = GOREV3_TRANSIT_ALTITUDE_M

logger = logging.getLogger(__name__)

class Gorev3RedropPhase:
    """Görev 3 Rapor Bölüm 7 (operatör revizyonu, 2026-08-13): "İkinci yük
    bırakma konumunda; Araç tekrar 30 cm irtifaya alçalacaktır. Son
    merkezleme tamamlandıktan sonra GRAB SERVO ... yük hedef konuma
    bırakılacaktır." No alignment/retreat sequence needed here (unlike
    pickup) -- reuses CenteringController.go_to_and_center's staged
    descend-and-center primitive, same one Görev 2's payload drops use
    (core/mission/payload_release.py), rather than the previous hand-rolled
    IPayloadVisibilityStrategy-based approach that gorev3_pickup.py now owns
    instead."""

    def __init__(self, flight: IFlightBackend, actuator: IPayloadActuator,
                 position_store: PositionStore, centering: CenteringController):
        self.flight = flight
        self.actuator = actuator
        self.position_store = position_store
        self.centering = centering

    async def _current_alt_m(self):
        """Vehicle relative altitude, telemetry only."""
        try:
            _lat, _lon, alt = await self.flight.get_global_position()
            return alt
        except Exception:  # noqa: BLE001
            return None

    def _carried_speed(self):
        """How fast the carried load is moving relative to the target.

        Reuses the seating geometry the actuator already computes, because
        while the payload is locked the hook and the load are the same body.
        """
        try:
            g = self.actuator.seating_geometry("red")
        except Exception:  # noqa: BLE001
            return None
        return None if g is None else g.rel_speed_mps

    async def run(self) -> bool:
        logger.info("Görev 3 Faz 3 (Yeniden Bırakma) Başlatıldı.")

        kirmizi_ucgen_point = self.position_store.get('KIRMIZI_UCGEN')
        if kirmizi_ucgen_point is None:
            raise RuntimeError("Kırmızı Üçgen konumu bulunamadı! Görev 3 Faz 3 başlatılamaz.")

        # 1) GORUSUN SAGLAM OLDUGU IRTIFADA merkezle.
        converged = await self.centering.go_to_and_center(
            "KIRMIZI_UCGEN", altitude_m=GOREV3_PLACE_ALIGN_ALTITUDE_M)
        if not converged:
            logger.warning("Merkezleme yakınsamadı -- yine de devam ediliyor (best-effort).")

        # TASINAN YUKU HIZALA, ARACI DEGIL (2026-08-27).
        #
        # go_to_and_center yukaridaki merkezlemeyi GORUNTUYLE yapar, ama
        # ARACI hedefe oturtur. Yuk aracin altinda degil: kilit onu KANCAYA
        # kaynakliyor ve kanca govde (-0.090, 0)'da, ustune bir de ipin
        # salinimi var. Yani mukemmel merkezlenmis bir arac bile yuku ~9 cm
        # yana birakir. Gorev 2'nin olculen dagilimi (13-34 cm) bu terimin
        # ta kendisiydi; montaj kolu 0.28 m'den 0.035 m'ye indirildiginde
        # hata da onunla birlikte dusmustu.
        #
        # Hedef GORUNTUDEN olculur (gorevin kendi sekil tespitleri), tasinan
        # yukun konumu ise kanca pozundan gelir -- yuk kancaya kaynakli
        # oldugu icin kancanin pozu YUKUN pozudur; ikinci bir olcum yapmanin
        # anlami yok. Neden goruntuden okunmadigi visual_placement.py'nin
        # basindaki notta: yuk kirmizi, hedef de kirmizi ucgen.
        aligner = VisualPlacementAligner(
            get_detection=lambda: self.centering.detection_feed.get("KIRMIZI_UCGEN"),
            get_alt_m=self._current_alt_m,
            get_yaw_deg=self.flight.get_yaw_deg,
            get_position_ned=self.flight.get_position_ned,
            get_carried_offset=lambda: carried_payload_ned_offset(self.actuator),
            goto_ned_and_hold=lambda n, e, alt, yaw:
                self.flight.goto_position_ned_and_hold(n, e, -alt, yaw, 1.5),
            get_rel_speed=self._carried_speed)
        yaw = await self.flight.get_yaw_deg()
        # 2) KANCAYA REFERANSLI gorsel hizalama, hedefin mutlak konumu saklanir.
        place = await aligner.align(GOREV3_PLACE_ALIGN_ALTITUDE_M, yaw)
        if not place.aligned:
            # Bu bir DURDURMA sebebi degil: yuk zaten kancada ve hedefin
            # uzerindeyiz; hizalanamamak birakmayi kotulestirir, imkansiz
            # kilmaz. Ama sessizce gecmesin diye kaydediliyor.
            logger.warning("[GORSEL_YERLESTIRME] hizalanamadi (%s) -- birakma yine "
                           "de yapilacak, sonuc olculup raporlanacak.", place.reason)
        if place.target_ned is not None:
            logger.info("[GORSEL_YERLESTIRME] hedef GORUNTUDEN olculdu: NED=(%.3f, %.3f)",
                        place.target_ned[0], place.target_ned[1])

        # 3) Birakma irtifasina DIKEY in (yatay is bitti; ucgenin kadrajdan
        #    tasmasi artik onemli degil).
        _n, _e, _ = await self.flight.get_position_ned()
        logger.info("%.2f m birakma irtifasina iniliyor.", GOREV3_DESCENT_ALTITUDE_M)
        await self.flight.goto_position_ned_and_hold(
            _n, _e, -GOREV3_DESCENT_ALTITUDE_M, yaw, 6.0)

        # 4) Saklanan hedefe gore KANCAYA REFERANSLI son duzeltme.
        if place.target_ned is not None:
            residual = await settle_onto_ned(
                place.target_ned,
                get_position_ned=self.flight.get_position_ned,
                get_carried_offset=lambda: carried_payload_ned_offset(self.actuator),
                goto_ned_and_hold=lambda n, e, alt, y:
                    self.flight.goto_position_ned_and_hold(n, e, -alt, y, 2.0),
                alt_m=GOREV3_DESCENT_ALTITUDE_M, yaw_deg=yaw,
                get_rel_speed=self._carried_speed)
            if residual is not None:
                logger.info("[GORSEL_YERLESTIRME] birakma oncesi son yuk-hedef "
                            "hatasi: %.1f mm", residual * 1000)

        logger.info("Taşınan yük bırakma mekanizması aktifleşiyor...")
        dropped = await self.actuator.activate_drop_mechanism()

        # BIRAKMA SONUCUNU OLC (2026-08-23). Gorev 2'nin PAYLOAD_FINAL_POSE
        # kontrolunun Gorev 3 karsiligi yoktu: yukun nereye dustugu hic
        # olculmuyordu, dolayisiyla "Faz 3 Basarili" yazarken yuk hala
        # kancada asili olabiliyordu ve bu fark edilmiyordu.
        await asyncio.sleep(2.0)
        pose = await self.actuator.get_released_payload_pose("MAVI_ALTIGEN")
        if pose is None:
            logger.warning("[GOREV3_FINAL_POSE] yuk pozu okunamadi.")
        else:
            # E1: hedef merkezi artik kosum aninda dunya SDF'inden okunuyor
            # (bkz. gz_payload_actuator.read_target_centers). Sabit bir
            # sozlukten okumak, layout randomize edildikten sonra HER
            # mesafeyi anlamsiz kilmisti. Referans yoksa mesafe HIC
            # yazilmaz -- yanlis sayi basmaktansa susmak dogrusu.
            reference = getattr(self.actuator, "landing_reference",
                                lambda _s: None)("KIRMIZI_UCGEN")
            at_rest = pose[2] < GOREV3_REDROP_REST_HEIGHT_M
            rest_text = "YERDE" if at_rest else "HAVADA (hala kancada olabilir)"
            if reference is None:
                logger.info("[GOREV3_FINAL_POSE] x=%.3f y=%.3f z=%.3f -- hedef "
                            "merkezi bilinmiyor, mesafe olculemedi, %s",
                            pose[0], pose[1], pose[2], rest_text)
            else:
                cx, cy = reference[0], reference[1]
                dist = math.hypot(pose[0] - cx, pose[1] - cy)
                logger.info("[GOREV3_FINAL_POSE] x=%.3f y=%.3f z=%.3f -- Kirmizi Ucgen "
                            "merkezine %.1f cm, %s",
                            pose[0], pose[1], pose[2], dist * 100, rest_text)
            if not at_rest:
                logger.error("[GOREV3_FINAL_POSE] yuk yere inmemis (z=%.3f) -- "
                             "birakma dogrulanamadi.", pose[2])
                dropped = False

        if not dropped:
            logger.error("Görev 3 Faz 3 başarısız: yük bırakılamadı.")
            return False

        logger.info("Görev 3 Faz 3 Başarılı.")
        return True
