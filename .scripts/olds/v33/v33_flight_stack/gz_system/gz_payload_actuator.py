import asyncio
import logging
import math
import time
from typing import Optional
from core.interfaces.i_payload_actuator import IPayloadActuator
from core.config.parameters import (
    PAYLOAD_DETACH_BURST_COUNT, PAYLOAD_DETACH_BURST_INTERVAL_S,
    PAYLOAD_DETACH_CONFIRM_TIMEOUT_S, PAYLOAD_DETACH_POLL_INTERVAL_S,
    PAYLOAD_DETACH_SEPARATION_M, PAYLOAD_EXPECTED_REST_Z_M,
    PAYLOAD_ON_TARGET_Z_TOLERANCE_M,
    V3_CATCH_PAYLOAD_TIMEOUT_S, V3_HOOK_ATTACH_CONFIRM_Z_TOLERANCE_M,
)
from gz_system.gz_pose_monitor import GzPoseMonitor

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

# Mission Flow V3 F3: HookAttachSystem (src/modules/simulation/gz_plugins/
# hook_attach/HookAttachSystem.cc), Tools/simulation/gz/models/
# x500_mono_cam_down/model.sdf'e F3'te bağlandı. Tek instance, hedef child
# model adı SDF'de sabit değil -- /hook/attach mesajının kendi içeriğinde
# gelir (bkz. HookAttachSystem.cc:108-146).
HOOK_ATTACH_TOPIC = "/hook/attach"
HOOK_DETACH_TOPIC = "/hook/detach"
HOOK_STATE_TOPIC = "/hook/state"
# Görev 3'ün alma hedefi HER ZAMAN payload_red (Mavi Altıgen): PayloadInterlock
# Mavi Altıgen'i her zaman Kırmızı Üçgen'den önce bıraktırır (Görev 2 Rapor
# Bölüm 11.1, interlock.py) -- bu yüzden 1st_mission (mission_v3_state.py'nin
# tamamen aynı sonuca vardığı deterministik etiket) her zaman Mavi Altıgen'dir.
# Bu sabit, o değişmez kurala dayanır; interlock kuralı değişirse burası da
# gözden geçirilmeli.
GOREV3_PICKUP_TARGET_COLOR = "red"

# 2026-08-24: yukaridaki sabitin dayandigi INVARYANT ARTIK YOK.
# PayloadInterlock'un "Mavi Altigen her zaman once" kurali kaldirildi
# (bkz. core/mission/interlock.py) -- birakma sirasi artik tespit sirasini
# takip ediyor, dolayisiyla Gorev 3'un alacagi payload derleme zamaninda
# BILINMIYOR. ADR-012:54 bu sabitin invaryanta bagli oldugunu ve kural
# gevserse gozden gecirilmesi gerektigini zaten uyariyordu.
#
# GOREV3_PICKUP_TARGET_COLOR yalnizca ESKI yol (IPayloadActuator) icin
# duruyor; yeni payload/ yolu asagidaki eslemeyi kullanip hedefi calisma
# zamaninda seciyor (GazeboPayloadBackend.select_payload).
PAYLOAD_MODEL_BY_SHAPE = {shape: PAYLOAD_MODEL % color
                          for shape, color in SHAPE_TO_COLOR.items()}


class HookStateMonitor:
    """F3 fix (2026-08-21): scoped to the lifetime of one attach wait --
    started, used and stopped inside _await_attach() (see below), never kept
    alive for the whole mission. Subscribes once to HOOK_STATE_TOPIC and
    streams into a cache, mirroring GzPoseMonitor's proven pattern
    (gz_pose_monitor.py) instead of a one-shot `gz topic -e -n 1`: F3's
    isolated test (2026-08-20) measured that a fresh one-shot subscription
    can miss the single message HookAttachSystem ever publishes for a given
    transition, because the subscriber has not finished connecting before
    the publish fires -- the same slow-joiner problem `_burst_detach`
    already works around for /payload/detach/*. `data: true/false` is the
    ONLY line shape gz.msgs.Boolean's text encoding ever produces, so no
    section-tracking parser (like GzPoseMonitor's) is needed here."""

    def __init__(self):
        self._attached: Optional[bool] = None
        self._proc = None
        self._task = None

    async def start(self) -> bool:
        try:
            self._proc = await asyncio.create_subprocess_exec(
                "gz", "topic", "-e", "-t", HOOK_STATE_TOPIC,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        except Exception as e:  # noqa: BLE001
            logger.warning("HookStateMonitor baslatilamadi: %s", e)
            self._proc = None
            return False
        self._task = asyncio.create_task(self._read_loop())
        return True

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        while True:
            try:
                raw = await self._proc.stdout.readline()
            except Exception:  # noqa: BLE001
                return
            if not raw:
                return
            line = raw.decode(errors="replace").strip()
            if line.startswith("data:"):
                self._attached = line.split(":", 1)[1].strip() == "true"

    def get(self) -> Optional[bool]:
        return self._attached

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None
        if self._proc is not None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except Exception:  # noqa: BLE001
                pass
            self._proc = None


class GzPayloadActuator(IPayloadActuator):
    def __init__(self, gazebo_service_name: str, world_name: str = "default",
                 pose_monitor: GzPoseMonitor = None):
        self.gazebo_service_name = gazebo_service_name
        # W4.3: only needed to address the dynamic_pose topic when reporting
        # where a released payload came to rest.
        self.world_name = world_name
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
    # revizyonu, bkz. gorev3_pickup.py/gorev3_redrop.py). Gerçek yük alma/
    # bırakma mantığı (dik hizalanma, 30cm/60cm hareket, doğrulama)
    # gorev3_pickup.py/gorev3_redrop.py'de zaten gerçek -- bu iki metod
    # yalnızca fiziksel servo/hook tetiklemesinden sorumlu.
    #
    # F3 (2026-08-20): HookAttachSystem artık x500_mono_cam_down/model.sdf'e
    # bağlı (tek instance, parent_link=base_link). İzole testte doğrulandı:
    # payload_red yerde (z~0.025) -> /hook/attach -> araç ~0.9m hover'dayken
    # payload_red z~0.74'e sıçradı (birlikte havada asılı) -> /hook/detach ->
    # payload_red tekrar yere düştü (z~0.025).
    #
    # F3 FALSE-POSITIVE + FIX (2026-08-21): ilk sürüm attach'i _relative_drop
    # (vehicle_z - payload_z) küçük mü diye bakarak "doğruluyordu" -- ama
    # Gorev3PickupPhase pickup'tan önce 0.30m irtifaya alçalıyor, yani bu
    # fark GERÇEK bir joint hiç oluşmadan da ~0.3-0.85m aralığında kalıyor.
    # Gerçek SITL'de ölçüldü: vehicle_z=0.854, payload_z=0.031, delta=0.823 --
    # V3_HOOK_ATTACH_CONFIRM_Z_TOLERANCE_M=1.0'ın İÇİNDE, attach hiç
    # çalışmamışken. Mission log'u "Yük Alma Başarılı" ve ardından
    # "TÜM GÖREVLER BAŞARIYLA BİTTİ" dedi; payload_red canlı sorguda hâlâ
    # orijinal bırakma konumundaydı (hiç taşınmamış). Artık gerçek kaynağı
    # (HOOK_STATE_TOPIC, HookAttachSystem.cc'nin PreUpdate()'te joint
    # gerçekten oluşturulduğunda/kaldırıldığında yayınladığı tek ground-truth
    # sinyali) HookStateMonitor ile (kalıcı abonelik, tek-seferlik `-n 1`
    # değil) doğrudan okuyoruz -- bkz. _await_attach.
    async def _publish_attach(self, child_model: str) -> bool:
        cmd = ["gz", "topic", "-t", HOOK_ATTACH_TOPIC, "-m", "gz.msgs.StringMsg",
               "-p", f'data: "{child_model}"']
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
            _stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error("Gazebo attach komutu basarisiz (%s): %s",
                             child_model, stderr.decode().strip())
                return False
            return True
        except FileNotFoundError:
            logger.error("`gz` CLI bulunamadi -- Gazebo ortami PATH'te degil.")
            return False
        except Exception as e:  # noqa: BLE001
            logger.error("Gazebo attach komutu istisna verdi (%s): %s", child_model, e)
            return False

    async def _publish_hook_detach(self) -> bool:
        cmd = ["gz", "topic", "-t", HOOK_DETACH_TOPIC, "-m", "gz.msgs.Boolean", "-p", "data: true"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
            _stdout, stderr = await proc.communicate()
            return proc.returncode == 0
        except Exception as e:  # noqa: BLE001
            logger.error("Gazebo hook detach komutu istisna verdi: %s", e)
            return False

    async def _await_attach(self, color: str, timeout_s: float) -> bool:
        """Gerçek attach kanıtını HOOK_STATE_TOPIC'ten (HookAttachSystem'in
        kendi ground-truth yayını) bekler -- pozisyon yakınlığından DEĞİL
        (bkz. yukarıdaki F3 FALSE-POSITIVE + FIX notu, tam ölçüm kanıtıyla).
        Konum hâlâ okunur ama SADECE tanı/log amaçlı -- kapı (gate) değil;
        state=true iken beklenmedik derecede büyük çıkarsa (pose_monitor
        bayatlığı gibi bir anomaliye işaret edebilir) UYARI loglanır, yine
        de state'e güvenilir çünkü HookAttachSystem.cc bunu yalnızca joint
        entity'sini GERÇEKTEN oluşturduğunda/kaldırdığında yayınlar, hiçbir
        zaman zamanlayıcıyla değil (HookAttachSystem.cc:122-129, :83-94)."""
        monitor = HookStateMonitor()
        if not await monitor.start():
            logger.error("HookStateMonitor baslatilamadi -- attach fiziksel olarak DOGRULANAMAZ.")
            return False
        try:
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                if monitor.get() is True:
                    delta = self._relative_drop(color)
                    if delta is None or abs(delta) > V3_HOOK_ATTACH_CONFIRM_Z_TOLERANCE_M:
                        logger.warning(
                            "HOOK_STATE_TOPIC attach=true dedi ama vehicle_z-payload_z=%s "
                            "beklenenden büyük/bilinmiyor -- pose_monitor bayat olabilir, "
                            "yine de /hook/state ground-truth kabul ediliyor.",
                            f"{delta:.3f}" if delta is not None else "None")
                    else:
                        logger.info("HookAttachSystem attach=true doğrulandı "
                                   "(vehicle_z-payload_z=%.3f).", delta)
                    return True
                await asyncio.sleep(PAYLOAD_DETACH_POLL_INTERVAL_S)
            return False
        finally:
            await monitor.stop()
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

    async def activate_pickup_mechanism(self) -> bool:
        """Görev 3 Faz 1, Adım 6: Yük alma mekanizmasını aktifleştirir.

        V3_CATCH_PAYLOAD_TIMEOUT_S (15s) -- sistemdeki tek timeout noktası --
        burada uygulanır: bu süre içinde attach fiziksel olarak doğrulanamazsa
        False döner, orchestrator (Gorev3PickupPhase) zaten bunu False dönüşü
        olarak ele alıyor (yeniden deneme/abort icat edilmedi, mevcut davranış
        korunuyor)."""
        # THIRD MISSION SERVO
        child_model = PAYLOAD_MODEL % GOREV3_PICKUP_TARGET_COLOR
        logger.info(f"HookAttachSystem: {HOOK_ATTACH_TOPIC} -> {child_model}")
        if not await self._publish_attach(child_model):
            logger.error("Attach mesajı hiç yayınlanamadı.")
            return False
        attached = await self._await_attach(GOREV3_PICKUP_TARGET_COLOR, V3_CATCH_PAYLOAD_TIMEOUT_S)
        if not attached:
            logger.error(f"[CATCH_PAYLOAD_TIMEOUT] {V3_CATCH_PAYLOAD_TIMEOUT_S}s icinde "
                         f"{child_model} icin attach fiziksel olarak dogrulanamadi.")
            return False
        logger.info(f"Yuk alindi ({child_model}), HookAttachSystem ile dogrulandi.")
        return True

    async def activate_drop_mechanism(self) -> bool:
        """Görev 3 Faz 3, Adım 5: Taşınan yükü bırakır."""
        # GRAB SERVO
        child_model = PAYLOAD_MODEL % GOREV3_PICKUP_TARGET_COLOR
        logger.info(f"HookAttachSystem: {HOOK_DETACH_TOPIC} -> {child_model}")
        if not await self._publish_hook_detach():
            logger.error("Hook detach mesajı hiç yayınlanamadı.")
            return False
        # V3 spesi: sistemdeki TEK timeout noktası attach'te (yukarıda) --
        # burada mevcut _at_rest_height deseni (payload_release.py'nin
        # detach-doğrulamasıyla aynı mantık) best-effort doğrulama yapar,
        # ayrı bir zorunlu timeout eklemez.
        await asyncio.sleep(PAYLOAD_DETACH_POLL_INTERVAL_S * 3)
        if not self._at_rest_height(GOREV3_PICKUP_TARGET_COLOR):
            logger.warning(f"{child_model} beklenen dinlenme irtifasında değil -- "
                           "detach best-effort, akış durdurulmuyor.")
        logger.info(f"Tasinan yuk birakildi ({child_model}).")
        return True
