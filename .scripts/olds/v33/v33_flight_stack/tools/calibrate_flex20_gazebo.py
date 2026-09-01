#!/usr/bin/env python3
"""PHASE 5.5 ADIM D: FLEX-20 (Gazebo capture envelope) SITL karakterizasyonu.

HAM VERİ ÜRETİR, FLEX-20'Yİ GÜNCELLEMEZ. Script payload_config.py'ye
HİÇBİR ŞEY YAZMAZ; değeri operatör elle, ayrı bir adımda girer.

--- BU SCRIPT NEYİ ÖLÇÜYOR (VE NEYİ ÖLÇMÜYOR) -----------------------------

HookAttachSystem'de MESAFE KONTROLÜ YOKTUR (232 satırda tek bir Pose
component okuması yok; kendi yorumuna göre temas testi ÇAĞIRANA aittir,
HookAttachSystem.cc:33-35). Sonuç: publish_attach() HER mesafede başarılı
olur ve /hook/state her denemede true döner. "Hangi mesafede attach
çalışıyor?" sorusunun cevabı sabittir: HEPSİNDE. Bu yüzden tablodaki
`hook_state` sütunu tek başına hiçbir şey ayırt etmez -- ve zaten
ayırt etmesi de beklenmiyor; sütun, bu beklentinin bozulduğu bir durumu
(ör. plugin yüklü değil) yakalamak için var.

Karakterize edilebilir olan şey attach'in BAŞARISI değil, FİZİKSEL
MAKULLÜĞÜdür: joint oluştuğu anda payload ne kadar zıplıyor. Kanca
payload'ın hemen üstündeyken zıplama ~0'dır; araç metrelerce yukarıdayken
ani rijit kısıt payload'ı yukarı fırlatır -- hiçbir operatörün "yakalama"
demeyeceği bir hareket. Asıl ayırt edici sinyal `payload_jump_m` sütunudur.

Yani FLEX-20 keşfedilen bir plugin özelliği DEĞİL, bizim koyduğumuz bir
POLİTİKA EŞİĞİdir. Bu script o eşiği seçebilmek için gereken ham veriyi
üretir; eşiği KENDİSİ seçmez.

--- TASARIM ---------------------------------------------------------------

  * GzHookClient DOĞRUDAN kullanılır. PayloadManager ve
    GazeboPayloadBackend devrede DEĞİLDİR (bypass) -- tıpkı Real backend
    için konuşulan bench-kalibrasyon scripti gibi. Böylece FLEX-20 henüz
    None iken de çalışabilir: backend'in CALIBRATION GUARD'ı bu yolu
    kapatmaz.
  * Mesafe, client'ın read_vehicle_payload_distance()'ından okunur -- yani
    gz_hook_client.py::_distance()'ın TEK formülünden. Script kendi mesafe
    hesabını TUTMAZ; kalibrasyon, üretimde kullanılacak formülün ta
    kendisiyle yapılır.
  * Dikey tarama (operatör kararı, 2026-08-23): araç payload'ın üstünde
    farklı irtifalarda hover eder. Gerçek Görev 3 alçalma profiliyle
    örtüşsün diye; yatay ışınlama daha deterministik olurdu ama gerçek
    profili temsil etmezdi.
  * Her turdan sonra detach ZORUNLU. HookAttachSystem.cc:135-139: zaten
    attach'liyken gelen istek SESSİZCE yok sayılır (state yayını da
    olmaz). Detach doğrulanmadan sonraki tura geçilirse tablo "hepsi
    başarılı" der ama ilk turdan sonrası hiç çalışmamıştır. Script bunu
    her turda doğrular, doğrulayamazsa TARAMAYI DURDURUR.
"""
import argparse
import asyncio
import csv
import logging
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gz_system.gz_hook_client import GzHookClient  # noqa: E402
from gz_system.gz_payload_actuator import (  # noqa: E402
    GOREV3_PICKUP_TARGET_COLOR,
    PAYLOAD_DETACH_TOPIC,
    PAYLOAD_MODEL,
    VEHICLE_MODEL_NAME,
)
from core.config.parameters import OFFBOARD_SETPOINT_INTERVAL_S  # noqa: E402
from gz_system.gz_flight_backend import GzFlightBackend  # noqa: E402
from gz_system.gz_pose_monitor import GzPoseMonitor  # noqa: E402
from payload import payload_config  # noqa: E402

logger = logging.getLogger("flex20")

# Taranacak hedef DİKEY boşluklar (araç altı - payload üstü, metre).
# Bunlar KALİBRASYON DEĞERİ DEĞİL, tarama noktalarıdır -- hangi aralığa
# bakılacağını belirlerler, hiçbir fiziksel büyüklük iddia etmezler.
# Gerçek Görev 3 alçalma irtifası (0.30 m) ortada kalacak şekilde seçildi.
DEFAULT_GAPS_M = [0.15, 0.30, 0.50, 0.80, 1.20, 2.00]

SETTLE_BEFORE_ATTACH_S = 4.0   # hover oturması
ATTACH_STATE_TIMEOUT_S = 10.0  # /hook/state true beklerken
DETACH_STATE_TIMEOUT_S = 10.0  # /hook/state false beklerken
JUMP_OBSERVE_S = 1.5           # attach sonrasi payload yer degistirmesi penceresi
POST_DETACH_SETTLE_S = 3.0     # payload yere geri otursun

CSV_COLUMNS = [
    "trial", "commanded_gap_m", "measured_distance_m",
    "measured_clearance_m", "hook_state",
    "attach_latency_s", "payload_jump_m",
    "payload_x", "payload_y", "payload_z",
    "payload_x_after", "payload_y_after", "payload_z_after",
    "vehicle_x", "vehicle_y", "vehicle_z", "notes",
]


def _fmt(value, digits=3):
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


async def _publish_stock_release(color: str) -> None:
    """payload_red'i stok DetachableJoint'ten bırakır ki yerde SERBEST
    dursun. Yoksa payload araca zaten bağlıdır ve 'yakalama' ölçümü
    anlamsız olur."""
    topic = PAYLOAD_DETACH_TOPIC % color
    proc = await asyncio.create_subprocess_exec(
        "gz", "topic", "-t", topic, "-m", "gz.msgs.Empty", "-p", "",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await proc.wait()
    logger.info("Stok DetachableJoint birakildi: %s", topic)


class Flex20Characterizer:
    def __init__(self, client: GzHookClient, pose_monitor: GzPoseMonitor,
                 flight: GzFlightBackend, payload_model: str, vehicle_model: str):
        self.client = client
        self.pose_monitor = pose_monitor
        self.flight = flight
        self.payload_model = payload_model
        self.vehicle_model = vehicle_model
        self.rows = []
        self._target_ned = None
        self._streamer = None

    # -- yardimcilar ------------------------------------------------------

    def _payload_pose(self):
        return self.pose_monitor.get(self.payload_model)

    def _vehicle_pose(self):
        return self.pose_monitor.get(self.vehicle_model)

    def _aim_at_gap(self, payload_pose, gap_m: float) -> None:
        """Hedef setpoint'i payload'ın `gap_m` kadar üstüne kurar.

        Setpoint'i BURADA GÖNDERMEZ -- akıtma işini _setpoint_streamer
        yapar (aşağıya bkz.). Bu ayrım kasıtlı: goto_position_ned()
        setpoint'i TEK SEFER yollar ve PX4, setpoint akışı kesilince
        Offboard'dan otomatik çıkar; mavsdk_backend_base.py'nin kendi
        docstring'i bu "single-shot-then-silence" hatasını belgeliyor.
        Bu script attach/gözlem/detach boyunca saniyelerce bekliyor, yani
        akıtma olmadan tarama daha ilk turda Offboard'ı kaybederdi.

        FRAME NOTU: Gazebo dünyası ENU'dur (X=Doğu, Y=Kuzey; bkz.
        default.sdf'teki 2026-08-13 bug-fix notu), PX4 NED ise
        (kuzey, doğu, aşağı). Dönüşüm bu yüzden north=gz_y, east=gz_x.
        Aracın NED orijini spawn noktasıdır ve spawn dünya orijinindedir,
        bu yüzden ek bir kaydırma yok."""
        gx, gy, gz = payload_pose
        self._target_ned = (gy, gx, -(gz + gap_m))

    async def _setpoint_streamer(self) -> None:
        """Hedef setpoint'i kesintisiz akıtır. Tarama boyunca (attach,
        gözlem, detach beklemeleri dahil) çalışır ki PX4 Offboard'dan
        düşmesin."""
        while True:
            target = self._target_ned
            if target is not None:
                try:
                    await self.flight.goto_position_ned(target[0], target[1],
                                                        target[2], 0.0)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Setpoint akitilamadi (yoksayiliyor): %s", e)
            await asyncio.sleep(OFFBOARD_SETPOINT_INTERVAL_S)

    async def start_streaming(self) -> None:
        self._streamer = asyncio.create_task(self._setpoint_streamer())

    async def stop_streaming(self) -> None:
        if self._streamer is not None:
            self._streamer.cancel()
            try:
                await self._streamer
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._streamer = None

    # -- tek tur ----------------------------------------------------------

    async def run_trial(self, index: int, gap_m: float) -> bool:
        """Bir tarama noktası. Detach doğrulanamazsa False döner ve çağıran
        taramayı DURDURUR (sonraki turlar sessizce yok sayılırdı)."""
        notes = []
        payload_before = self._payload_pose()
        if payload_before is None:
            self._record(index, gap_m, notes=["payload pozu okunamadi -- tur atlandi"])
            return True

        self._aim_at_gap(payload_before, gap_m)
        await asyncio.sleep(SETTLE_BEFORE_ATTACH_S)

        payload_before = self._payload_pose() or payload_before
        vehicle_pose = self._vehicle_pose()
        measured = self.client.read_vehicle_payload_distance()
        # FLEX-20'nin gercekte kapiladigi buyukluk aciklik oldugu icin
        # (bkz. payload_config.py FLEX-20), ham veri ikisini de tasir --
        # gelecekteki bir gozden gecirme dogru sutuna bakabilsin diye.
        clearance = self.client.read_vehicle_payload_clearance()
        if measured is None:
            notes.append("mesafe okunamadi (poz bilinmiyor)")

        started = time.monotonic()
        published = await self.client.publish_attach()
        if not published:
            notes.append("attach YAYINLANAMADI")
            self._record(index, gap_m, measured, clearance, None, None, None,
                         payload_before, None, vehicle_pose, notes)
            return True

        state = None
        latency = None
        try:
            await asyncio.wait_for(self.client.wait_for_hook_state(True),
                                   timeout=ATTACH_STATE_TIMEOUT_S)
            latency = time.monotonic() - started
            state = True
        except asyncio.TimeoutError:
            state = self.client.hook_state()
            notes.append(f"/hook/state {ATTACH_STATE_TIMEOUT_S}s icinde true DONMEDI "
                         f"(plugin yuklu mu? model.sdf HookAttachSystem blogu)")

        await asyncio.sleep(JUMP_OBSERVE_S)
        payload_after = self._payload_pose()
        jump = (math.dist(payload_before, payload_after)
                if payload_before and payload_after else None)

        self._record(index, gap_m, measured, clearance, state, latency, jump,
                     payload_before, payload_after, vehicle_pose, notes)

        return await self._reset(index, notes)

    async def _reset(self, index: int, notes) -> bool:
        """Detach + doğrulama. Bu, taramanın devam edebilmesinin ÖN KOŞULU:
        attach'li kalırsak sonraki istekler sessizce yok sayılır."""
        if not await self.client.publish_detach():
            logger.error("Tur %d: detach YAYINLANAMADI -- tarama durduruluyor.", index)
            return False
        try:
            await asyncio.wait_for(self.client.wait_for_hook_state(False),
                                   timeout=DETACH_STATE_TIMEOUT_S)
        except asyncio.TimeoutError:
            logger.error("Tur %d: /hook/state %.1fs icinde false DONMEDI -- mekanizma "
                         "hala attach'li olabilir. Sonraki attach istekleri SESSIZCE "
                         "yok sayilirdi (HookAttachSystem.cc:135-139), bu yuzden "
                         "tarama DURDURULUYOR.", index, DETACH_STATE_TIMEOUT_S)
            return False
        await asyncio.sleep(POST_DETACH_SETTLE_S)
        return True

    def _record(self, index, gap_m, measured=None, clearance=None, state=None,
                latency=None, jump=None, payload_before=None, payload_after=None,
                vehicle_pose=None, notes=None):
        pb = payload_before or (None, None, None)
        pa = payload_after or (None, None, None)
        vp = vehicle_pose or (None, None, None)
        self.rows.append({
            "trial": index, "commanded_gap_m": gap_m,
            "measured_distance_m": measured,
            "measured_clearance_m": clearance, "hook_state": state,
            "attach_latency_s": latency, "payload_jump_m": jump,
            "payload_x": pb[0], "payload_y": pb[1], "payload_z": pb[2],
            "payload_x_after": pa[0], "payload_y_after": pa[1], "payload_z_after": pa[2],
            "vehicle_x": vp[0], "vehicle_y": vp[1], "vehicle_z": vp[2],
            "notes": "; ".join(notes or []),
        })

    # -- rapor ------------------------------------------------------------

    def write_csv(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(self.rows)
        logger.info("Ham veri yazildi: %s", path)

    def print_table(self) -> None:
        header = (f"{'#':>2}  {'hedef':>7}  {'olculen':>8}  {'aciklik':>8}  "
                  f"{'state':>6}  {'gecikme':>8}  {'ziplama':>8}  notlar")
        print("\n" + header)
        print("-" * len(header))
        for row in self.rows:
            print(f"{row['trial']:>2}  {_fmt(row['commanded_gap_m'], 2):>7}  "
                  f"{_fmt(row['measured_distance_m']):>8}  "
                  f"{_fmt(row['measured_clearance_m']):>8}  "
                  f"{str(row['hook_state']):>6}  "
                  f"{_fmt(row['attach_latency_s']):>8}  "
                  f"{_fmt(row['payload_jump_m']):>8}  {row['notes']}")
        print()
        print("SUTUN OKUMASI:")
        print("  state  : HER turda true BEKLENIR -- HookAttachSystem mesafe kontrolu")
        print("           YAPMAZ. false/None gorursen bu bir envelope bulgusu DEGIL,")
        print("           plugin/abonelik sorunudur.")
        print("  ziplama: asil ayirt edici sinyal. Joint olustugu anda payload'in yer")
        print("           degistirmesi. ~0 = kanca zaten payload'in ustunde (mesru")
        print("           yakalama). Buyudukce payload uzaktan 'cekilmis' demektir.")


def _print_flex20_reminder() -> None:
    current = payload_config.FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M
    print("=" * 74)
    print("FLEX-20 GUNCELLENMEDI -- bu script payload_config.py'ye HICBIR SEY YAZMAZ.")
    print(f"  payload_config.FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M = {current!r}")
    print()
    print("  Yukaridaki 'ziplama' sutununa bakip fiziksel olarak mesru gorunen EN")
    print("  BUYUK mesafeyi secin ve degeri payload_config.py'ye ELLE girin;")
    print("  ayni blokta CURRENT DEFAULT notunu da bu olcumle guncelleyin.")
    print("=" * 74)


async def main_async(args) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if payload_config.FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M is not None:
        logger.warning("FLEX-20 zaten dolu (%r). Karakterizasyon yine de calisir "
                       "(bu script backend'i bypass eder), ama ONCEKI bir kalibrasyonun "
                       "uzerine bakiyorsunuz -- sonuclari ona gore yorumlayin.",
                       payload_config.FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M)

    payload_model = PAYLOAD_MODEL % GOREV3_PICKUP_TARGET_COLOR
    pose_monitor = GzPoseMonitor(args.world)
    await pose_monitor.start()

    client = await GzHookClient.create(
        payload_model_name=payload_model, vehicle_model_name=VEHICLE_MODEL_NAME,
        world_name=args.world, pose_monitor=pose_monitor)

    if not client.is_state_stream_ready():
        logger.error("/hook/state akisi hazir DEGIL -- plugin yuklu olmayabilir "
                     "(model.sdf HookAttachSystem blogu). Cikiliyor.")
        await client.stop()
        await pose_monitor.stop()
        return 2

    flight = GzFlightBackend(args.connection)
    characterizer = Flex20Characterizer(client, pose_monitor, flight,
                                        payload_model, VEHICLE_MODEL_NAME)
    try:
        await flight.connect()
        await _publish_stock_release(GOREV3_PICKUP_TARGET_COLOR)
        await asyncio.sleep(POST_DETACH_SETTLE_S)

        await flight.arm()
        await flight.takeoff(max(args.gaps) + 1.0)
        await asyncio.sleep(8.0)
        await flight.start_offboard()
        # Mevcut konumu ilk hedef yap ki akis basladigi anda arac yerinde
        # dursun, sifir noktasina dogru suzulmesin.
        current_n, current_e, current_d = await flight.get_position_ned()
        characterizer._target_ned = (current_n, current_e, current_d)
        await characterizer.start_streaming()

        for index, gap in enumerate(args.gaps, start=1):
            logger.info("--- Tur %d/%d: hedef bosluk %.2f m ---",
                        index, len(args.gaps), gap)
            if not await characterizer.run_trial(index, gap):
                logger.error("Tarama tur %d'de durduruldu.", index)
                break
    finally:
        await characterizer.stop_streaming()
        try:
            await flight.stop_offboard()
            await flight.land()
            await asyncio.sleep(8.0)
        except Exception as e:  # noqa: BLE001 -- kapanis bir olcumu goturmemeli
            logger.warning("Inis sirasinda hata (yoksayiliyor): %s", e)
        await client.stop()
        await pose_monitor.stop()

    characterizer.print_table()
    characterizer.write_csv(args.out)
    _print_flex20_reminder()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="FLEX-20 (Gazebo capture envelope) SITL karakterizasyonu -- "
                    "HAM VERI uretir, FLEX-20'yi GUNCELLEMEZ.")
    parser.add_argument("--connection", default="udp://:14540")
    parser.add_argument("--world", default="default")
    parser.add_argument("--gaps", type=float, nargs="+", default=DEFAULT_GAPS_M,
                        help="Taranacak dikey bosluklar (m).")
    parser.add_argument("--out", default=None,
                        help="CSV cikti yolu (varsayilan: logs/flex20_calibration_<ts>.csv)")
    args = parser.parse_args()
    if args.out is None:
        args.out = os.path.join("logs", f"flex20_calibration_{int(time.time())}.csv")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
