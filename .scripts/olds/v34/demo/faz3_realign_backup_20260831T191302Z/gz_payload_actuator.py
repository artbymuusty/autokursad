import asyncio
import logging
import os
import math
import time
from core.interfaces.i_payload_actuator import IPayloadActuator
from core.config.parameters import (
    PAYLOAD_DETACH_BURST_COUNT, PAYLOAD_DETACH_BURST_INTERVAL_S,
    PAYLOAD_DETACH_CONFIRM_TIMEOUT_S, PAYLOAD_DETACH_POLL_INTERVAL_S,
    PAYLOAD_DETACH_SEPARATION_M, PAYLOAD_EXPECTED_REST_Z_M,
    PAYLOAD_ON_TARGET_Z_TOLERANCE_M,
)
from gz_system.gz_pose_monitor import GzPoseMonitor
from core.mission.hook_seating import (
    SeatState, SeatingEvaluator, compute_seating_geometry,
    SEAT_DWELL_S, SEAT_MAX_LATERAL_M, HOOK_POSE_MAX_AGE_S,
)

logger = logging.getLogger(__name__)

# GAP FIX (Görev 2 Rapor Bölüm 12/13): IPayloadActuator's own docstring commits
# gz_system to a real Gazebo call with "TODO YOKTUR" -- the two Görev-2 release
# methods below previously just slept and returned True unconditionally, so a
# passing Görev-2 run never actually dropped anything in the sim. The real,
# compiled-and-SDF-wired mechanism is payload::PayloadDropSystem (confirmed
# against src/modules/simulation/gz_plugins/payload_drop/payload_drop_system.cc
# and its <plugin> block in Tools/simulation/gz/models/x500_mono_cam_down/model.sdf,
# NOT the simpler joint-removal stub of the same name under
# Tools/simulation/gz/plugins/payload_drop -- that one is not what's loaded).
# It exposes a color-addressed path: publishing a StringMsg "red"/"blue" on
# PAYLOAD_DROP_COLOR_TOPIC drops exactly that payload once, independent of
# call order, and it self-confirms per color via PAYLOAD_DROP_STATE_TOPIC
# ("<color>:true"/"<color>:false"). The `gz topic` CLI publish is the same
# known-working trigger mechanism already proven by .scripts/denemePayload.py
# and the old flat v32/payload.py's _gazebo_boolean_drop.
#
# Physical-color mapping (preserved unchanged from flat v32/payload.py,
# where it was already established as a deliberate team assignment, not
# incidental): RED payload <-> Mavi Altıgen target, BLUE payload <-> Kırmızı
# Üçgen target. Payload 1 (mavi_altigen) is always dropped before payload 2
# (kirmizi_ucgen) by PayloadInterlock, so this also lines up with the
# plugin's own legacy RED-then-BLUE stage_ ordering, though the color-select
# path used here does not depend on that ordering at all.
PAYLOAD_DETACH_TOPIC = "/payload/detach/%s"   # ADR-011: %s = red|blue
PAYLOAD_DROP_STATE_TOPIC = "/payload_drop_state"

# Kanca (2026-08-21). Mekanizma artik SDF'de: x500_mono_cam_down/model.sdf
# icindeki hook_winch_link + hook_rope_link + HookAttachSystem blogu.
# Mesaj tipleri EKLENTININ imzalarindan alindi, tahminle degil:
#   /hook/attach  gz.msgs.StringMsg  child model adi ("payload_red")
#   /hook/detach  gz.msgs.Boolean    data:true  (Empty DEGIL -- yanlis tiple
#                                    publish edilen mesaji gz-transport
#                                    sessizce dusurur, olcerek dogrulandi)
#   /hook/state   gz.msgs.Boolean    fixed joint gercekten kuruldu/kaldirildi
#   /hook/contact temas              yalnizca hook_tip_collision
#   /hook/winch/cmd gz.msgs.Double   ip uzamasi, metre (0 = tamamen cekili)
HOOK_ATTACH_TOPIC = "/hook/attach"
HOOK_DETACH_TOPIC = "/hook/detach"
HOOK_STATE_TOPIC = "/hook/state"
HOOK_CONTACT_TOPIC = "/hook/contact"
HOOK_WINCH_TOPIC = "/hook/winch/cmd"
# BILEREK FAZLA UZAMA. 0.30 m irtifada yuvanin ustune (dunya z=0.070) tam
# denk gelen uzama 0.29 m'dir -- yani SIFIR pay, ve PX4'un birkac cm'lik
# irtifa hatasi temasi kacirmaya yetiyor: olculdu, mission8'de 3 denemenin
# 1'inde, mission9'da 0'inda temas geldi. 0.40 m verilince kanca yuvanin
# ustunden gecmeyi "hedefler" ve fizik onu durdurur -- ayni sey zeminde de
# dogrulandi (cmd 0.12 istendi, eklem 0.059'da durdu, kanca yere dayandi).
# Eklem efor siniri 8 N: 0.15 kg yuku kaldirmaya fazlasiyla yeter ama
# yuvaya bastirip payload'i itecek kadar sert degil.
HOOK_WINCH_EXTEND_M = 0.40
# --------------------------------------------------------------------------
# IRTIFADAN TURETILEN VINC SALIMI (2026-08-31)
# --------------------------------------------------------------------------
# Yukaridaki 0.40 m artik YALNIZCA irtifa bilinmedigi durumda kullanilan
# geri-dusus degeridir. Sorun sabitin varligi degil, PAYIN SABIT VE SINIRSIZ
# olmasiydi:
#
#   0.30 m irtifada guverteye tam denk gelen salim 0.29 m (yukaridaki olcum).
#   0.40 m verilince 0.11 m gevsek ip kaliyor. Ip 4 universal eklemli bir
#   zincir (HookRopeSwing1..4); gergin haldeyken kanca dik asilir (0.005-0.9
#   derece, hook_seating.py notu), ama 0.11 m gevseklikte zincir BUKULUYOR
#   ve kanca yatiyor. Olculdu (2026-08-31, iki bagimsiz kosu):
#
#     lat=9.9mm  ins=-8.1mm  tilt=43.2deg  v=inf     <- yanal MUKEMMEL
#     lat=9.7mm  ins=-8.5mm  tilt=44.7deg  v=0.013   <- hareketsiz, 44.7 derece
#
#   Hareketsiz bir kanca gergin ipte dik asilmak ZORUNDADIR. 44.7 derece,
#   ipin gevsek oldugunun dogrudan kanitidir; yanal hata 9.7 mm ile kapinin
#   rahat icindeyken tilt kapisi (15 derece) tek basina reddediyordu.
#
# Formul tek olculmus kalibrasyon noktasindan turetildi
# (irtifa 0.30, guverte 0.070 -> tam salim 0.29):
#
#     payout = alt - deck + CHAIN_OFFSET + MARGIN
#     0.29   = 0.30 - 0.070 + 0.060 + 0        <- dogrulama
#
# NEDEN SABITI DUSURMEK DEGIL: sabit yalnizca 0.30 m'de dogru olurdu.
# GOREV3_DESCENT_ALTITUDE_M degisirse, ya da baska bir irtifada alma
# denenirse (HOOK_VISUAL_ALIGN_ALTITUDE_M gibi), ya da farkli yukseklikte
# bir hedef gelirse formul kendini duzeltir, sabit sessizce yanlislasir.
HOOK_PAYOUT_CHAIN_OFFSET_M = 0.060      # olculen kalibrasyondan turetildi
HOOK_RECEIVER_DECK_HEIGHT_M = 0.070     # payload kutusu yuksekligi (yerde)
# PX4'un birkac cm'lik irtifa hatasini yutacak pay.
#
# GECICI DEGER -- SONUCU BELIRLEMEDI, iki gozlenmis hata yonunun ARASINDA
# oldugu icin secildi. 2026-08-31 taramasi (0.02 / 0.04 / 0.06, her biri tam
# bir demo kosusu, toplam 9 alma denemesi, ~1980 oturma ornegi):
#
#   * Hicbiri kapiyi araladi: CAPTURE_CANDIDATE ucunde de 0.
#   * Yanal hata bir egilim GOSTERMEDI: ortalamalar 71.0 / 75.2 / 67.4 mm,
#     ama kosu ICI sacilim 46-88 mm, yani kosular arasi farktan buyuk.
#     Sebebi acik: baglayici kapi lateral ve payout lateral'e dokunmuyor.
#   * Verinin sinirladigi tek sey YON:
#       0.02 AZ  -- bir denemenin tamami too_high (220/220 ornek,
#                   ins=-277.7 mm), kanca guverteye hic ulasmadi.
#       0.06 FAZLA -- ins=+68.6 mm, guvertenin 6.9 cm altinda.
#       0.04 ARADA -- eksenel 19.8 / 20.6 / 38.7 mm; ucunden ikisi kabul
#                   bandinin ([-4, +22] mm) icinde, herhangi bir margin'in
#                   en iyisi.
#
# YENIDEN TURETILMELI: lateral sorunu (gorsel hizalama -> oturma gecisinde
# hatanin buyumesi) cozuldukten sonra. O zamana kadar eksenel davranis
# lateral tarafindan maskeleniyor ve bu deger olculerek secilemez.
HOOK_PAYOUT_MARGIN_DEFAULT_M = 0.04
HOOK_PAYOUT_MARGIN_ENV = "KURSAD_HOOK_PAYOUT_MARGIN_M"


def hook_payout_margin_m() -> float:
    """Salim payi (m). Ortam degiskeni varsa o, yoksa varsayilan."""
    raw = os.environ.get(HOOK_PAYOUT_MARGIN_ENV)
    if raw is None:
        return HOOK_PAYOUT_MARGIN_DEFAULT_M
    try:
        return float(raw)
    except ValueError:
        logger.warning("[HOOK] %s okunamadi (%r) -- varsayilan %.3f m kullaniliyor",
                       HOOK_PAYOUT_MARGIN_ENV, raw, HOOK_PAYOUT_MARGIN_DEFAULT_M)
        return HOOK_PAYOUT_MARGIN_DEFAULT_M


def hook_payout_m(altitude_m, deck_height_m: float = HOOK_RECEIVER_DECK_HEIGHT_M,
                  margin_m=None) -> float:
    """Kanca burnunu guvertenin uzerine getirecek vinc salimi (m).

    altitude_m None ise (irtifa okunamadi) HOOK_WINCH_EXTEND_M'e duser --
    eski davranis, yani bilinmeyen irtifada davranis degismez.
    """
    if altitude_m is None:
        return HOOK_WINCH_EXTEND_M
    if margin_m is None:
        margin_m = hook_payout_margin_m()
    payout = altitude_m - deck_height_m + HOOK_PAYOUT_CHAIN_OFFSET_M + margin_m
    # Negatif salim anlamsiz; ust sinir eski sabittir (bundan fazlasi zaten
    # zinciri buker, ki duzeltmeye calistigimiz sey odur).
    return max(0.0, min(payout, HOOK_WINCH_EXTEND_M))
HOOK_WINCH_RETRACT_M = 0.0
# Vincin 0.29 m'ye inmesi ~3 s suruyor; 6 s pencere dardi
# (mission8: 3 denemenin 2'sinde temas hic gelmedi).
HOOK_CONTACT_TIMEOUT_S = 12.0
HOOK_STATE_TIMEOUT_S = 5.0
HOOK_PICKUP_ATTEMPTS = 3
# Kilitten sonra ipteki salinimin sonmesi icin beklenen sure.
HOOK_SETTLE_S = 3.0
# Birakma sonrasi ayrilmayi dogrulama penceresi ve deneme sayisi.
HOOK_DETACH_CONFIRM_S = 4.0
HOOK_DETACH_ATTEMPTS = 3
# KANCANIN GERCEK POZU. hook_body_link, x500_mono_cam_down/model.sdf icinde
# dort parcali ipin ucundaki gercek CAD govdesidir. Kanca poz kaynagi ARTIK
# BUDUR; "arac pozu + sabit govde ofseti" kestirimi KALDIRILDI.
#
# NEDEN (kabul testi, 2026-08-26): eski kod kanca ucunu
#     tip = arac_xy + (-0.090, 0) yaw ile dondurulmus
# diye hesapliyordu. Kanca menteseli bir ipte sallandigi icin bu kestirimin
# gercek poza gore hatasi OLCULDU: ortalama 0.86 cm, p95 2.76 cm, alma
# penceresinde en fazla 8.23 cm, tasima sirasinda 19.86 cm -- 5 cm'lik bir
# esigin karsisinda. Sabit ofset varsayimi bu yuzden yok.
HOOK_LINK_NAME = "hook_body_link"
# Kanca-yuk bagil hizini sonlu farkla olcerken kullanilan pencere. 48 Hz'lik
# poz akisinda tek adimli fark gurultulu; ~0.1 s uzerinden turetmek onu
# yumusatir ve yine de bir "gecerken yakalama" olayindan cok daha kisadir.
HOOK_REL_SPEED_WINDOW_S = 0.10
# Oturma (seating) kapisinin ornekleme araligi. Poz akisi ~48 Hz, yani
# 0.05 s her ornekte taze veri demek; SEAT_DWELL_S = 0.30 s icine en az 6
# bagimsiz ornek dusuyor.
HOOK_SEATING_POLL_S = 0.05
GZ_STATE_LISTEN_TIMEOUT_S = 3.0


VEHICLE_MODEL_NAME = "x500_mono_cam_down_0"
PAYLOAD_MODEL = "payload_%s"

# Sim ground truth, read straight off Tools/simulation/gz/worlds/default.sdf.
# NOT mission input -- the mission is vision-driven and never learns where a
# target is. This exists only so a post-drop observation can be scored
# honestly ("0.41 m from the hexagon centre") instead of merely "above
# ground", which was the weak check that let a 4.9 m miss pass as a success
# on the first ADR-011 flight (F3).
TARGET_CENTERS = {"MAVI_ALTIGEN": (0.0, 15.0), "KIRMIZI_UCGEN": (0.0, 40.0)}
SHAPE_TO_COLOR = {"MAVI_ALTIGEN": "red", "KIRMIZI_UCGEN": "blue"}


class GzPayloadActuator(IPayloadActuator):
    def __init__(self, gazebo_service_name: str, world_name: str = None,
                 pose_monitor: GzPoseMonitor = None):
        # Olcum alanlari (davranisa etkisi YOK, yalnizca gorunurluk).
        # gorev3_pickup bunlari okuyup event bus'a yayinliyor; actuator'un
        # kendisi telemetriye bagimli kalmasin diye burada yalnizca veri
        # birakiliyor.
        self.last_seating_report = None
        self.last_pickup_report = None
        self.gazebo_service_name = gazebo_service_name
        # W4.3: only needed to address the dynamic_pose topic when reporting
        # where a released payload came to rest.
        # Follows PX4_GZ_WORLD -- see GzPoseMonitor.__init__ for why a
        # hard-coded "default" silently breaks every non-default world.
        self.world_name = world_name or os.environ.get("PX4_GZ_WORLD", "default")
        # F2: injected rather than created here so the one gz-transport
        # discovery cost is paid once, at mission start, and not at the
        # instant the servo fires.
        self.pose_monitor = pose_monitor or GzPoseMonitor(world_name)
        # F2 reporting: servo command -> observed separation, per colour.
        self.detach_latency_s = {}

    def _relative_drop(self, color: str):
        """Vehicle z minus payload z. Constant (the mount offset) while the
        joint holds; grows the moment the body is free. Measured relative to
        the vehicle rather than to the ground so a drone that is climbing
        away cannot be mistaken for a payload that is falling."""
        payload = self.pose_monitor.get(PAYLOAD_MODEL % color)
        vehicle = self.pose_monitor.get(VEHICLE_MODEL_NAME)
        if payload is None or vehicle is None:
            return None
        return vehicle[2] - payload[2]

    def measure_mount_vector(self, shape_type: str):
        """Where the payload actually hangs, measured at the instant of
        release rather than reasoned about.

        This exists because reasoning about it failed twice. The world SDF
        mounts the payloads at y = -+0.28, but that y is in Gazebo's FLU
        model frame at SPAWN yaw, while the aim correction is consumed in
        PX4's FRD body frame at FLIGHT yaw -- and the vehicle sits at ~86
        deg of Gazebo yaw once it is flying north. Two sign/frame guesses
        produced two wrong flights (0.243 m -> 0.850 m, then -0.299 m).
        Reporting the measured vector, in both frames, ends the guessing.

        Returns None when either pose is unknown."""
        color = SHAPE_TO_COLOR.get(shape_type)
        if color is None:
            return None
        payload = self.pose_monitor.get(PAYLOAD_MODEL % color)
        vehicle = self.pose_monitor.get(VEHICLE_MODEL_NAME)
        quat = self.pose_monitor.get_quat(VEHICLE_MODEL_NAME)
        if payload is None or vehicle is None or quat is None:
            return None
        dx, dy = payload[0] - vehicle[0], payload[1] - vehicle[1]
        qx, qy, qz, qw = quat
        yaw = math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
        # World delta -> vehicle FLU (X forward, Y left) -> PX4 FRD right.
        forward = dx * math.cos(yaw) + dy * math.sin(yaw)
        left = -dx * math.sin(yaw) + dy * math.cos(yaw)
        return {"world_dx": round(dx, 4), "world_dy": round(dy, 4),
                "gazebo_yaw_deg": round(math.degrees(yaw), 2),
                "body_forward_m": round(forward, 4),
                "body_right_m": round(-left, 4)}

    async def _publish_detach(self, color: str) -> bool:
        topic = PAYLOAD_DETACH_TOPIC % color
        cmd = ["gz", "topic", "-t", topic, "-m", "gz.msgs.Empty", "-p", ""]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE)
            _stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error("Gazebo detach komutu basarisiz (%s): %s",
                             color, stderr.decode().strip())
                return False
            return True
        except FileNotFoundError:
            logger.error("`gz` CLI bulunamadi -- Gazebo ortami PATH'te degil.")
            return False
        except Exception as e:  # noqa: BLE001
            logger.error("Gazebo detach komutu istisna verdi (%s): %s", color, e)
            return False

    async def _delayed_publish(self, color: str, delay_s: float) -> bool:
        if delay_s:
            await asyncio.sleep(delay_s)
        return await self._publish_detach(color)

    async def _burst_detach(self, color: str) -> bool:
        """Publishes the detach message several times in quick succession.

        gz-transport is a slow joiner: a publisher that advertises and sends
        in the same breath can lose the message, because the subscriber (the
        DetachableJoint plugin) has not finished connecting. Each
        `gz topic -p` is a fresh short-lived process, so it hits that window
        every single time -- the leading explanation for the several-second
        late detach measured on the first ADR-011 flight. The burst costs
        nothing; the confirmation poll below is what proves it worked."""
        sent = await asyncio.gather(*[
            self._delayed_publish(color, i * PAYLOAD_DETACH_BURST_INTERVAL_S)
            for i in range(PAYLOAD_DETACH_BURST_COUNT)])
        return any(sent)

    async def _await_separation(self, color: str, baseline, timeout_s: float,
                                started: float = None):
        """Polls the pose cache until the payload has visibly left the
        vehicle. Returns the latency in seconds, or None if it has not
        separated within the window.

        `started` is the SERVO COMMAND instant, not the moment polling
        began. Timing from the start of polling instead would have silently
        subtracted the entire publish cost and reported 0.000 s for a
        release that actually took the best part of a second."""
        started = time.monotonic() if started is None else started
        while time.monotonic() - started < timeout_s:
            current = self._relative_drop(color)
            if (current is not None
                    and abs(current - baseline) > PAYLOAD_DETACH_SEPARATION_M):
                return time.monotonic() - started
            if self._at_rest_height(color):
                return time.monotonic() - started
            await asyncio.sleep(PAYLOAD_DETACH_POLL_INTERVAL_S)
        return None

    def _at_rest_height(self, color: str) -> bool:
        """T1: a payload released from very low down has nowhere to fall.

        Separation is normally judged on the body dropping away from the
        vehicle, which needs a fall. On the Phase 13 flight payload 2 was
        released at 0.159 m -- its underside already resting on the ground
        -- so detaching moved it by nothing at all, the release was reported
        UNCONFIRMED, and the vehicle held for the full 60 s over a payload
        that was sitting exactly where it belonged. A body already at its
        rest height is released whether or not it moved to get there.

        Safe against false positives: while attached at a normal 0.45 m
        release the payload sits at ~0.474 m, an order of magnitude above
        the rest band."""
        payload = self.pose_monitor.get(PAYLOAD_MODEL % color)
        if payload is None:
            return False
        return abs(payload[2] - PAYLOAD_EXPECTED_REST_Z_M) <= PAYLOAD_ON_TARGET_Z_TOLERANCE_M

    async def _publish_color_drop(self, color: str) -> bool:
        """ADR-011 + F2: releases one payload, and CONFIRMS it separated.

        Was a StringMsg on /payload_drop_color, which made PayloadDropSystem
        SPAWN a new model -- and a runtime-spawned body gets no reliable
        collision pairs in this gz-sim build, so every drop fell through the
        world (measured: a real release logged at z=-0.72, still falling).
        The payload now exists from world load and is simply released here.

        Returns True only when separation was OBSERVED. False means the
        payload is still attached and the caller must not climb away --
        precisely the failure that put payload 2 down 4.9 m off the triangle
        while the log cheerfully said RELEASED."""
        topic = PAYLOAD_DETACH_TOPIC % color
        baseline = self._relative_drop(color)
        logger.info("Gazebo DetachableJoint tetikleniyor: %s", topic)

        # The burst runs CONCURRENTLY with the watch. Awaiting it first would
        # mean the clock only starts after ~1 s of `gz topic` process cost,
        # and the reported latency would exclude the very delay it exists to
        # measure -- the first run of this code duly reported 0.000 s.
        servo_at = time.monotonic()
        burst = asyncio.create_task(self._burst_detach(color))

        if baseline is None:
            if not await burst:
                logger.error("Gazebo detach mesaji hic yayinlanamadi (%s).", color)
                return False
            # No pose data at all: the monitor never started, or Gazebo has
            # not published this body yet. We cannot tell attached from
            # separated, so we must claim neither. Reported as unknown (not
            # failure) so a missing observer can never ground a flight.
            logger.warning("Yuk pozu okunamadi (%s) -- ayrilma DOGRULANAMADI, "
                           "basarisiz da sayilmiyor.", color)
            self.detach_latency_s[color] = None
            return True

        latency = await self._await_separation(color, baseline,
                                               PAYLOAD_DETACH_CONFIRM_TIMEOUT_S, servo_at)
        if not await burst:
            logger.error("Gazebo detach mesaji hic yayinlanamadi (%s).", color)
            return False
        if latency is None:
            logger.warning("Yuk %s ayrilmadi -- detach yeniden yayinlaniyor.", color)
            await self._burst_detach(color)
            latency = await self._await_separation(
                color, baseline, 2 * PAYLOAD_DETACH_CONFIRM_TIMEOUT_S, servo_at)

        self.detach_latency_s[color] = latency
        if latency is None:
            logger.error("[PAYLOAD_DETACH_UNCONFIRMED] %s: yuk hala araca bagli.", color)
            return False
        logger.info("Yuk ayrildi (%s), gecikme %.3f s.", color, latency)
        return True

    async def is_release_confirmed(self, shape_type: str) -> bool:
        """F2: lets the caller keep holding position and re-checking while a
        release is unconfirmed, instead of climbing away on a hope."""
        color = SHAPE_TO_COLOR.get(shape_type)
        if color is None:
            return False
        payload = self.pose_monitor.get(PAYLOAD_MODEL % color)
        vehicle = self.pose_monitor.get(VEHICLE_MODEL_NAME)
        if payload is None or vehicle is None:
            return False
        # Absolute test, not a delta: by now the body should be on the
        # ground, well below a vehicle still hovering at release altitude.
        return (vehicle[2] - payload[2]) > PAYLOAD_EXPECTED_REST_Z_M + PAYLOAD_DETACH_SEPARATION_M

    async def retry_release(self, shape_type: str) -> bool:
        color = SHAPE_TO_COLOR.get(shape_type)
        if color is None:
            return False
        return await self._burst_detach(color)

    def landing_reference(self, shape_type: str):
        """F3: (target_x, target_y, expected_rest_z) so a landing can be
        scored against the shape it was aimed at. Sim-only ground truth;
        returns None for shapes with no known centre, and core code then
        degrades to the old above-ground check."""
        centre = TARGET_CENTERS.get(shape_type)
        if centre is None:
            return None
        return (centre[0], centre[1], PAYLOAD_EXPECTED_REST_Z_M)

    def detach_latency(self, shape_type: str):
        return self.detach_latency_s.get(SHAPE_TO_COLOR.get(shape_type))

    async def release_payload_at_mavi_altigen(self) -> bool:
        """Görev 2, 1. yük bırakma: RED payload -> Mavi Altıgen hedefi."""
        # FIRST MISSION SERVO
        return await self._publish_color_drop("red")

    async def release_payload_at_kirmizi_ucgen(self) -> bool:
        """Görev 2, 2. yük bırakma: BLUE payload -> Kırmızı Üçgen hedefi."""
        # SECOND MISSION SERVO
        return await self._publish_color_drop("blue")

    # Görev 3'ün kendi algoritması operatör tarafından tanımlandı (2026-08-13
    # revizyonu, bkz. gorev3_pickup.py/gorev3_redrop.py) -- artık kapsam
    # dışı değil. Ancak bu iki metod için (pickup/drop) hâlâ SDF-instantiated
    # bir mekanizma yok: HookAttachSystem derlenmiş durumda
    # (src/modules/simulation/gz_plugins/hook_attach/HookAttachSystem.cc,
    # topics /hook/attach, /hook/detach, /hook/state) ama hiçbir .sdf/.world
    # dosyasında referans edilmiyor, yani şimdi publish etmek hiçbir şeyi
    # tetiklemez. Gerçek yük alma/bırakma mantığı (dik hizalanma, 30cm/60cm
    # hareket, doğrulama) gorev3_pickup.py/gorev3_redrop.py'de zaten
    # gerçek -- yalnızca bu iki metodun İÇİ (fiziksel servo/hook tetikleme)
    # simüle, mekanizma SDF'ye eklenene kadar.
    async def get_released_payload_pose(self, shape_type: str):
        """W4.3: where the released payload body actually ended up.

        ADR-011: the payload is a world-loaded model with a fixed name
        (payload_red / payload_blue), read straight off
        /world/<world>/dynamic_pose/info.

        Returns (x, y, z) or None. Purely observational: it is called after
        the servo has already fired, and every failure path returns None so a
        missing pose is reported as "unavailable" rather than guessed at."""
        # ADR-011: the payload is a world-loaded model with a fixed name now,
        # not a spawn named payload_drop_<color>_<n>.
        color = SHAPE_TO_COLOR.get(shape_type)
        if color is None:
            return None
        # F2: read from the shared pose cache instead of spawning a fresh
        # `gz topic -e -n 1`. That one-shot subscription cost ~2 s of
        # discovery on every call, and -- worse -- BLOCKS FOREVER once the
        # scene goes quiet, because dynamic_pose/info only publishes
        # entities that moved this step. Reading the cache returns the last
        # observed pose of a settled body immediately, which is exactly the
        # question being asked.
        return self.pose_monitor.get(PAYLOAD_MODEL % color)

    def get_released_payload_tilt_deg(self, shape_type: str):
        """F3 diagnosis: how far the payload is from lying flat.

        payload_red came to rest at z=0.156 on the first ADR-011 flight.
        0.156 is not a random number: it is the target surface (0.006) plus
        half of the prism's LONG side (0.150) -- i.e. the slab was standing
        on its edge, not lying on its face. Reporting tilt turns that from
        an inference into an observation."""
        color = SHAPE_TO_COLOR.get(shape_type)
        if color is None:
            return None
        quat = self.pose_monitor.get_quat(PAYLOAD_MODEL % color)
        if quat is None:
            return None
        qx, qy, qz, qw = quat
        # Angle between the body z axis and world z, straight from the
        # rotation matrix's (2,2) term -- no euler conversion needed.
        cos_tilt = max(-1.0, min(1.0, 1.0 - 2.0 * (qx * qx + qy * qy)))
        return round(math.degrees(math.acos(cos_tilt)), 1)

    async def _gz_pub(self, topic: str, msgtype: str, payload: str) -> bool:
        """`gz topic -p` ile tek mesaj. _publish_detach ile ayni desen:
        asyncio subprocess, cunku senkron beklemek Offboard setpoint akisini
        durdurur ve PX4 ~500ms'de Offboard'dan duser."""
        cmd = ["gz", "topic", "-t", topic, "-m", msgtype, "-p", payload]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE)
            _out, err = await proc.communicate()
            if proc.returncode != 0:
                logger.error("gz publish basarisiz (%s): %s", topic, err.decode().strip()[:160])
                return False
            return True
        except FileNotFoundError:
            logger.error("`gz` CLI bulunamadi -- Gazebo ortami PATH'te degil.")
            return False
        except Exception as e:  # noqa: BLE001
            logger.error("gz publish istisna verdi (%s): %s", topic, e)
            return False

    async def _gz_wait_for(self, topic: str, timeout_s: float, needle: str = "",
                           after_start=None) -> bool:
        """topic'te timeout_s icinde mesaj (istege bagli: needle iceren) var mi.

        `gz topic -e`'yi subprocess olarak calistirip cikisini okur; asla
        senkron bloke etmez, yani cagiran Offboard setpoint'lerini
        surdurebilir.

        after_start: abone AYAGA KALKTIKTAN SONRA calistirilacak coroutine.
        /hook/state tek atimlik yayinlar: once publish edip sonra dinlemeye
        baslamak mesaji kaciriyordu -- olculdu (mission8, 14:38:44
        "kilidi onaylamadi", oysa temas gelmisti ve joint muhtemelen
        kurulmustu). Tetikleyiciyi buraya vererek sira garanti altina
        aliniyor."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "gz", "topic", "-e", "-t", topic,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        except Exception as e:  # noqa: BLE001
            logger.error("gz echo baslatilamadi (%s): %s", topic, e)
            return False
        try:
            if after_start is not None:
                # gz-transport'un abonelik kesfi icin kisa pay; publish'i
                # ancak bundan sonra tetikle.
                await asyncio.sleep(0.8)
                await after_start()
            buf = b""
            deadline = asyncio.get_event_loop().time() + timeout_s
            while asyncio.get_event_loop().time() < deadline:
                try:
                    chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if not chunk:
                    break
                buf += chunk
                if buf.strip() and (not needle or needle.encode() in buf):
                    return True
            return False
        finally:
            try:
                proc.kill()
                await proc.wait()
            except Exception:  # noqa: BLE001
                pass

    def is_hook_attached(self) -> bool:
        """Kancada yuk asili mi. HookAttachSystem'in /hook/state onayiyla
        set edilir; alma fazinin dogrulamasi buna bakar."""
        return getattr(self, "_hook_attached", False)

    def payload_altitude_m(self, color: str):
        """Yukun dunya z'si (m), olculemezse None. Alma dogrulamasinda
        'yuk aracla birlikte yukseldi mi' sorusunu cevaplar."""
        pose = self.pose_monitor.get(PAYLOAD_MODEL % color) if self.pose_monitor else None
        return None if pose is None else pose[2]

    def get_hook_world_pose(self):
        """THE authoritative hook pose. WORLD frame, from Gazebo.

        Returns (position, quaternion, age_s) for hook_body_link -- the real
        CAD hook body on the end of the four-segment rope -- or None when the
        pose is unavailable. Callers MUST treat None, and any age beyond
        HOOK_POSE_MAX_AGE_S, as "cannot validate" and refuse to attach.

        This replaces the old `_hook_tip_xy()`, which derived the hook
        position from the vehicle body pose plus a fixed x = -0.090 offset.
        That offset is only correct while the rope hangs perfectly plumb;
        measured error against this pose was up to 8.23 cm during pickup and
        19.86 cm during transport (acceptance test, 2026-08-26).

        Reuses the ALREADY RUNNING GzPoseMonitor subscription -- no second
        pose pipeline is created.
        """
        if self.pose_monitor is None:
            return None
        return self.pose_monitor.link_world_pose(VEHICLE_MODEL_NAME, HOOK_LINK_NAME)

    def _payload_world_pose(self, color: str):
        """WORLD pose of the payload link, i.e. of the receiver."""
        if self.pose_monitor is None:
            return None
        name = PAYLOAD_MODEL % color
        pos = self.pose_monitor.get(name)
        quat = self.pose_monitor.get_quat(name)
        if pos is None or quat is None:
            return None
        age = self.pose_monitor.age_s(name)
        return pos, quat, (0.0 if age is None else age)

    def _relative_speed_mps(self, color: str, hook_pos, payload_pos):
        """|d(hook - payload)/dt| from a short finite-difference window.

        Returns None until enough history exists; the seating gate treats
        that as "cannot validate" rather than as zero, because an unknown
        speed must never satisfy a speed limit.
        """
        now = time.monotonic()
        rel = tuple(hook_pos[i] - payload_pos[i] for i in range(3))
        hist = getattr(self, "_rel_hist", None)
        if hist is None:
            hist = self._rel_hist = []
        hist.append((now, rel))
        cutoff = now - max(HOOK_REL_SPEED_WINDOW_S * 3.0, 0.5)
        while len(hist) > 2 and hist[0][0] < cutoff:
            hist.pop(0)
        ref = None
        for t_old, r_old in hist:
            if now - t_old >= HOOK_REL_SPEED_WINDOW_S:
                ref = (t_old, r_old)
            else:
                break
        if ref is None:
            return None
        dt = now - ref[0]
        if dt <= 1e-6:
            return None
        d = tuple(rel[i] - ref[1][i] for i in range(3))
        return math.sqrt(sum(c * c for c in d)) / dt

    def reset_seating_history(self) -> None:
        """Drop the velocity window (call between pickup attempts)."""
        self._rel_hist = []

    def seating_geometry(self, color: str):
        """Hook pose expressed in the receiver frame, or None.

        This is the ONLY geometry the pickup gate is allowed to consult.
        """
        hook = self.get_hook_world_pose()
        pay = self._payload_world_pose(color)
        if hook is None or pay is None:
            return None
        hook_pos, hook_quat, hook_age = hook
        pay_pos, pay_quat, pay_age = pay
        speed = self._relative_speed_mps(color, hook_pos, pay_pos)
        if speed is None:
            # No velocity estimate yet -> report it as unbounded so the gate
            # fails closed instead of silently accepting an unmeasured speed.
            speed = float("inf")
        return compute_seating_geometry(hook_pos, hook_quat, pay_pos, pay_quat,
                                        rel_speed_mps=speed,
                                        pose_age_s=max(hook_age, pay_age))

    def hook_to_receiver_offset_world(self, color: str):
        """World-horizontal vector FROM the hook nose TO the receiver axis.

        Returns (d_east, d_north) in metres, i.e. the Gazebo-world (ENU) x/y
        displacement that would put the hook on the receiver axis, or None if
        either pose is unavailable.

        This is what lets the pickup phase CLOSE THE LOOP on the real hook
        instead of dead-reckoning it from the airframe. The vehicle's own
        NED frame is axis-aligned with the Gazebo world (gz +x = East,
        gz +y = North, verified in flight), so a caller converts with
            north += d_north ; east += d_east
        without needing to know either frame's origin -- this is a relative
        displacement, not a position.
        """
        hook = self.get_hook_world_pose()
        pay = self._payload_world_pose(color)
        if hook is None or pay is None:
            return None
        hook_pos, hook_quat, _age = hook
        pay_pos, _pq, _pa = pay
        # Nose point, not the link origin: the link origin sits 64.65 mm above
        # the nose, so a tilted hook would otherwise be mis-corrected.
        from core.mission.hook_seating import HOOK_NOSE_OFFSET_M, _rotate
        off = _rotate(hook_quat, (0.0, 0.0, HOOK_NOSE_OFFSET_M))
        nose_x = hook_pos[0] + off[0]
        nose_y = hook_pos[1] + off[1]
        return (pay_pos[0] - nose_x, pay_pos[1] - nose_y)

    def hook_nose_ned_offset_m(self):
        """Hook NOSE position relative to the vehicle origin, as (north, east).

        Gazebo world is ENU and PX4's local frame is NED with the same axes
        (gz +x = East, gz +y = North, verified in flight), so this is a pure
        axis swap on a RELATIVE displacement -- neither frame's origin is
        needed.

        This is the hook half of the visual-alignment error. It comes from the
        real hook pose rather than from the image on purpose: the hook hangs
        below the camera while the receiver sits on the ground, so the two are
        at very different depths and differencing them in PIXELS carries a
        bias of up to ~0.2 m (see core/mission/visual_alignment.py). The hook
        pose is the same simulated mechanical sensor the seating gate already
        trusts; the RECEIVER, which is what actually has to be found, is
        measured from the camera.
        """
        hook = self.get_hook_world_pose()
        veh = self.pose_monitor.get(VEHICLE_MODEL_NAME) if self.pose_monitor else None
        if hook is None or veh is None:
            return None
        from core.mission.hook_seating import HOOK_NOSE_OFFSET_M, _rotate
        pos, quat, _age = hook
        off = _rotate(quat, (0.0, 0.0, HOOK_NOSE_OFFSET_M))
        nose_x, nose_y = pos[0] + off[0], pos[1] + off[1]
        return (nose_y - veh[1], nose_x - veh[0])      # (north, east)

    def hook_lateral_error_m(self, color: str):
        """Hook-to-receiver LATERAL error (m), measured perpendicular to the
        receiver axis using the real hook pose. None if unmeasurable."""
        geom = self.seating_geometry(color)
        return None if geom is None else geom.lateral_m

    def magnet_gap_m(self, color: str):
        """DEPRECATED NAME, kept for existing callers/log lines.

        It never measured a magnet. Nothing in this build simulates magnetic
        force: the hook magnet (O10 x 2) and the payload's steel target disc
        (O12.4) are <visual> elements with no collision and no force plugin.
        This returns the same LATERAL error as hook_lateral_error_m().
        """
        return self.hook_lateral_error_m(color)

    def is_hook_seated(self) -> bool:
        return getattr(self, "_seat_state", SeatState.APPROACHING) is SeatState.SEATED

    def hook_seat_state(self):
        return getattr(self, "_seat_state", SeatState.APPROACHING)

    async def _await_seating(self, color: str, timeout_s: float):
        """Wait until the hook is PHYSICALLY SEATED in the receiver.

        REPLACES `_await_capture`, which accepted a pickup on horizontal
        distance alone. Acceptance Case 7 (2026-08-26) drove that gate into
        a false capture: hook 2.42 cm laterally from the receiver but 1.97 m
        ABOVE it, reported captured, welded, and hoisted a payload that was
        still resting on the ground. Measured post-lock hook<->payload
        distance: 1.68 m.

        The gate now evaluates, in the RECEIVER's own frame and from the REAL
        hook pose (see get_hook_world_pose):

            lateral    <= SEAT_MAX_LATERAL_M      (bore mouth radius)
            insertion  in [SEAT_MIN_INSERTION_M, SEAT_MAX_INSERTION_M]
            tilt       <= SEAT_MAX_TILT_RAD       (axes, not yaw: the bore
                                                   is rotationally symmetric)
            rel_speed  <= SEAT_MAX_REL_SPEED_MPS  (no locking mid pass-through)
            pose_age   <= HOOK_POSE_MAX_AGE_S     (stale pose fails closed)

        and all of them must hold CONTINUOUSLY for SEAT_DWELL_S, so a hook
        swinging through the envelope cannot latch on a single sample.

        Every threshold is derived from the exported CAD in
        core/mission/hook_seating.py -- none of them is a tuned constant.

        /hook/contact is intentionally NOT consulted any more. It fires on
        the hook tip touching ANYTHING, ground included (measured:
        collision2 { name: "ground_plane::link::collision" }), so it can only
        ever weaken a geometric decision it cannot corroborate.
        """
        evaluator = SeatingEvaluator()
        self.reset_seating_history()
        self._seat_state = SeatState.APPROACHING
        deadline = asyncio.get_event_loop().time() + timeout_s
        # EN IYI ESZAMANLI ORNEK. Onceden best_lat ve best_ins BAGIMSIZ
        # izleniyordu ve rapor satiri yaniltiyordu: 2026-08-31 kosusunda
        # "En iyi yanal 7.4 mm, en iyi eksenel +0.9 mm" yazdi, ama o iki
        # deger FARKLI orneklerdendi -- yanal 7.4 mm iken kanca 43 derece
        # egik ve guverte ustundeydi, eksenel +0.9 mm iken yanal 36.7 mm'ydi.
        # Okuyan "1 mm kalmisti" saniyor, oysa hicbir ornek yakin degildi.
        # Artik TEK bir ornek secilir: once en az kapi ihlali, esitlikte en
        # kucuk yanal hata.
        best_geom = None
        best_failn = None
        fail_counts = {}
        candidate_samples = 0
        sample_count = 0
        # KANCA-ARAC OFSETI, oturma penceresi boyunca (mekanizma 2b olcumu,
        # 2026-08-31). Duzeltme dongusu bu buyuklugu 0.94 m'de logluyor;
        # burada 0.33 m'deki karsiligini topluyoruz ki "denge konumu
        # irtifayla degisiyor" hipotezi tek bir anlik olcume degil, dagilima
        # dayansin.
        offs = []
        last_log = 0.0

        while asyncio.get_event_loop().time() < deadline:
            geom = self.seating_geometry(color)
            now = time.monotonic()
            state = evaluator.update(geom, now)
            self._seat_state = state

            # SALT OLCUM: hicbir kosulda oturma kararini ya da gorevi
            # etkilememeli. Poz kaynagi eksikse (testlerdeki sahte monitor
            # gibi) sessizce atlanir -- bu satirin varligi davranisi
            # degistirmemeli.
            try:
                _o = self.hook_nose_ned_offset_m()
            except Exception:  # noqa: BLE001
                _o = None
            if _o is not None:
                offs.append(_o)
            if geom is not None:
                sample_count += 1
                fails = geom.failures()
                for f in fails:
                    key = f.split("(")[0]
                    fail_counts[key] = fail_counts.get(key, 0) + 1
                if (best_failn is None or len(fails) < best_failn
                        or (len(fails) == best_failn and best_geom is not None
                            and geom.lateral_m < best_geom.lateral_m)):
                    best_failn, best_geom = len(fails), geom
            if state is SeatState.CAPTURE_CANDIDATE:
                candidate_samples += 1

            if state is SeatState.SEATED:
                logger.info("[HOOK] OTURDU (SEATED): %s -- dwell %.2f s",
                            geom.describe(), evaluator.dwell_elapsed(now))
                self.last_seating_report = {
                    "seated": True, "samples": sample_count,
                    "capture_candidate_samples": candidate_samples,
                    "gate_rejections": dict(fail_counts),
                    "best_simultaneous": {
                        "lateral_mm": round(geom.lateral_m * 1000, 1),
                        "insertion_mm": round(geom.insertion_m * 1000, 1),
                        "tilt_deg": round(math.degrees(geom.tilt_rad), 1),
                        "rel_speed_mps": round(geom.rel_speed_mps, 3),
                        "gates_failed": 0},
                }
                return True

            if now - last_log >= 1.0:
                last_log = now
                if geom is None:
                    logger.warning("[HOOK] kanca pozu YOK -- oturma dogrulanamiyor, "
                                   "alma reddedilecek.")
                else:
                    logger.info("[HOOK] %s  %s  [%s]", state.value, geom.describe(),
                                ", ".join(evaluator.last_failures) or "ok")
            await asyncio.sleep(HOOK_SEATING_POLL_S)

        self._seat_state = SeatState.APPROACHING
        self.last_seating_report = {
            "seated": False,
            "samples": sample_count,
            "capture_candidate_samples": candidate_samples,
            "gate_rejections": dict(sorted(fail_counts.items(), key=lambda kv: -kv[1])),
            "best_simultaneous": (
                {"lateral_mm": round(best_geom.lateral_m * 1000, 1),
                 "insertion_mm": round(best_geom.insertion_m * 1000, 1),
                 "tilt_deg": round(math.degrees(best_geom.tilt_rad), 1),
                 "rel_speed_mps": round(best_geom.rel_speed_mps, 3),
                 "gates_failed": best_failn}
                if best_geom is not None else None),
            "hook_offset_mean": ([round(sum(o[0] for o in offs) / len(offs), 4),
                                  round(sum(o[1] for o in offs) / len(offs), 4)]
                                 if offs else None),
            "hook_offset_samples": len(offs),
        }
        if offs:
            _mn = (sum(o[0] for o in offs) / len(offs), sum(o[1] for o in offs) / len(offs))
            logger.info("[KANCA_DENGE] oturma penceresi ortalama kanca_ofset="
                        "(%+.4f, %+.4f)  (%d ornek)", _mn[0], _mn[1], len(offs))
        logger.warning(
            "[HOOK] OTURMADI (%.1f s). En iyi ESZAMANLI ornek: %s (%s kapi ihlali). "
            "CAPTURE_CANDIDATE ornegi: %d/%d. Kapi retleri: %s. "
            "Sinirlar: yanal<=%.1f mm, dwell %.2f s.",
            timeout_s,
            best_geom.describe() if best_geom is not None else "olculemedi",
            best_failn if best_failn is not None else "?",
            candidate_samples, sample_count,
            ", ".join(f"{k}={v}" for k, v in
                      sorted(fail_counts.items(), key=lambda kv: -kv[1])) or "yok",
            SEAT_MAX_LATERAL_M * 1000, SEAT_DWELL_S)
        return False

    async def set_winch(self, extension_m: float) -> bool:
        """Vinci hedef uzamaya surer (metre, 0 = tamamen cekili)."""
        logger.info("[HOOK] vinc -> %.2f m", extension_m)
        return await self._gz_pub(HOOK_WINCH_TOPIC, "gz.msgs.Double", f"data: {extension_m}")

    async def activate_pickup_mechanism(self, altitude_m=None,
                                        deck_height_m: float = HOOK_RECEIVER_DECK_HEIGHT_M) -> bool:
        """Görev 3 Faz 1, Adım 6: yükü kancayla al.

        Gercek sira (operator tarifi, 2026-08-21): kanca yukun hizasina
        inecek, ucundaki magnet yuvaya denk gelirse oraya oturacak, sonra
        kanca icindeki servo donup kilitleyecek. Simulasyonda magnet+servo
        ikilisinin karsiligi tek sey: HookAttachSystem'in fixed joint'i.
        Temas once dogrulanir, cunku joint'i temassiz kurmak "havada
        kilitlendi" demek olurdu."""
        # THIRD MISSION SERVO
        payout = hook_payout_m(altitude_m, deck_height_m)
        logger.info("[HOOK] vinc salimi: %.3f m  (irtifa=%s, guverte=%.3f, "
                    "zincir ofseti=%.3f, pay=%.3f)",
                    payout,
                    f"{altitude_m:.3f} m" if altitude_m is not None else "BILINMIYOR -> sabit",
                    deck_height_m, HOOK_PAYOUT_CHAIN_OFFSET_M, hook_payout_margin_m())
        attempts_report = []
        for attempt in range(1, HOOK_PICKUP_ATTEMPTS + 1):
            logger.info("[HOOK] alma denemesi %d/%d", attempt, HOOK_PICKUP_ATTEMPTS)
            await self.set_winch(payout)

            color = SHAPE_TO_COLOR["MAVI_ALTIGEN"]
            seated = await self._await_seating(color, HOOK_CONTACT_TIMEOUT_S)
            if self.last_seating_report is not None:
                attempts_report.append(dict(self.last_seating_report, attempt=attempt))
            self.last_pickup_report = {"payout_m": round(payout, 4),
                                       "margin_m": round(hook_payout_margin_m(), 4),
                                       "altitude_m": (round(altitude_m, 3)
                                                      if altitude_m is not None else None),
                                       "attempts": attempts_report}
            if not seated:
                logger.warning("[HOOK] oturma dogrulanmadi (%.1fs) -- /hook/attach "
                               "YAYINLANMADI, vinc cekiliyor, tekrar denenecek",
                               HOOK_CONTACT_TIMEOUT_S)
                await self.set_winch(HOOK_WINCH_RETRACT_M)
                await asyncio.sleep(1.0)
                continue

            # SEATED -> LOCKING. The attach message is published ONLY from
            # here, i.e. only after the seating gate above has passed. That
            # ordering is the whole point of this phase: the runtime fixed
            # joint is the simulated MECHANICAL LOCK, and a mechanical lock
            # that can be created without the hook being in the receiver is
            # exactly the Case 7 defect.
            self._seat_state = SeatState.LOCKING
            logger.info("[HOOK] SEATED -> LOCKING: servo kilitleniyor")
            model = PAYLOAD_MODEL % color

            async def _send_attach():
                await self._gz_pub(HOOK_ATTACH_TOPIC, "gz.msgs.StringMsg", f'data: "{model}"')

            locked = await self._gz_wait_for(HOOK_STATE_TOPIC, HOOK_STATE_TIMEOUT_S, "true",
                                             after_start=_send_attach)
            if not locked:
                self._seat_state = SeatState.APPROACHING
                logger.warning("[HOOK] /hook/state kilidi onaylamadi -- temizlenip tekrar denenecek")
                # Onay kacmis olabilir ama joint KURULMUS olabilir; oyle bir
                # durumda yeniden attach "Already attached; ignoring" ile
                # sessizce duser ve faz asla ilerlemez. Temiz duruma don.
                await self._gz_pub(HOOK_DETACH_TOPIC, "gz.msgs.Boolean", "data: true")
                await self.set_winch(HOOK_WINCH_RETRACT_M)
                await asyncio.sleep(1.0)
                continue

            # Vinc BILEREK acik birakiliyor (operator, 2026-08-21). Toplamak
            # yuku govdeye dogru cekiyor: kilitli yuk, kancanin cekili
            # konumuna (base_link-0.145) kadar yukselir ve orada iniş
            # takimi/govde ile ayni hacme girer. mission12'de yuk hedefin
            # 7 m gerisine, y=33'e dustu; en olasi sebep bu. Ipte asili
            # kalan yuk hem gercek duzenege uygun hem de o temasi tamamen
            # ortadan kaldiriyor. Vinc, yuk BIRAKILDIKTAN sonra
            # activate_drop_mechanism icinde toplanir -- inisden once
            # toplanmazsa kanca yere iniş takimindan once deger.
            self._hook_attached = True
            self._seat_state = SeatState.LOCKED
            geom = self.seating_geometry(color)
            logger.info("[HOOK] LOCKED (%s) -- vinc acik, yuk ipte%s", model,
                        f"; oturma: {geom.describe()}" if geom is not None else "")
            # Salinim sonsun diye kisa bir sabitleme; tasima bunun uzerine
            # baslar.
            await asyncio.sleep(HOOK_SETTLE_S)
            return True

        self._seat_state = SeatState.APPROACHING
        logger.error("[HOOK] %d denemede yuk OTURMADI -- hicbir /hook/attach yayinlanmadi.",
                     HOOK_PICKUP_ATTEMPTS)
        await self.set_winch(HOOK_WINCH_RETRACT_M)
        return False

    async def activate_drop_mechanism(self) -> bool:
        """Görev 3 Faz 3, Adım 5: kancadaki yükü bırak (servo geri doner)."""
        # GRAB SERVO
        color = SHAPE_TO_COLOR["MAVI_ALTIGEN"]        # payload_red
        logger.info("[HOOK] servo aciliyor -- yuk birakiliyor")

        # SONUCU DOGRULA, KOMUTU DEGIL (olculdu, 2026-08-23 kosusu).
        #
        # Onceki surum yalnizca _gz_pub'in donusune bakiyordu; o ise "gz
        # komutu hatasiz calisti" demek, "joint gercekten kaldirildi" demek
        # degil. Sonuc: "yuk birakildi, vinc toplandi" ve "Faz 3 Basarili"
        # yazildi, ama yuk hala kancadaydi -- donus ucusu boyunca aracla
        # birlikte gitti (olculdu: yuk aracin 13 cm yaninda, 7 cm altinda,
        # x 19.5 -> 24.3 aracla beraber ilerledi).
        #
        # /hook/state ile onaylamak burada ISE YARAMAZ: eklenti
        # msg.set_data(false) yayinliyor ve protobuf varsayilan degeri
        # atladigi icin mesaj BOS govdeyle gidiyor, yani "mesaj yok"tan
        # ayirt edilemiyor. O yuzden Gorev 2'nin kanitlanmis yontemi
        # kullaniliyor: yuk aractan FIZIKSEL olarak ayrildi mi.
        baseline = self._relative_drop(color)
        for attempt in range(1, HOOK_DETACH_ATTEMPTS + 1):
            if not await self._gz_pub(HOOK_DETACH_TOPIC, "gz.msgs.Boolean", "data: true"):
                return False
            started = time.monotonic()
            latency = await self._await_separation(color, baseline,
                                                   HOOK_DETACH_CONFIRM_S, started)
            if latency is not None:
                logger.info("[HOOK] ayrilma dogrulandi (%.2f s, deneme %d).", latency, attempt)
                break
            logger.warning("[HOOK] yuk %.1f s icinde ayrilmadi (deneme %d/%d).",
                           HOOK_DETACH_CONFIRM_S, attempt, HOOK_DETACH_ATTEMPTS)
        else:
            logger.error("[HOOK] yuk BIRAKILAMADI -- kancada asili kalmis olabilir.")
            await self.set_winch(HOOK_WINCH_RETRACT_M)
            return False

        self._hook_attached = False
        self._seat_state = SeatState.APPROACHING
        await asyncio.sleep(0.5)
        # Vinc ancak SIMDI toplanir: tasima boyunca acik kaldi (bkz.
        # activate_pickup_mechanism). Acik birakilirsa 0.40 m uzamayla kanca
        # ucu base_link-0.545'te olur, yani arac inerken yere iniş
        # takimindan (base_link-0.2264) cok once deger.
        await self.set_winch(HOOK_WINCH_RETRACT_M)
        logger.info("[HOOK] yuk birakildi, vinc toplandi.")
        return True
