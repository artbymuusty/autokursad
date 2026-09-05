#!/usr/bin/env python3
"""GOREV K / D: manyetik cekim OLCUMU -- kontrollu A/B, gorevden bagimsiz.

NEDEN VAR: operator "cekim, J demosundaki 41-72 mm'lik yanal hatayi
GERCEKTEN cozuyor mu, varsaymayin olcun" dedi. Tam gorev kosumu bu olcumu
vermiyor: dort kosum ust uste alma penceresine girmeden once yuku goruntude
bulamadi (tespit oynakligi), yani cekim kodu bir kez bile calismadi.

Bu arac pencereyi DOGRUDAN kuruyor: bir yuku yere birakir, aracin kancasini
istenen yanal hatayla (varsayilan 41 mm -- olculen ariza bandinin alt ucu)
yukun uzerine getirir, vinci salar ve oturma dongusunu KOSAR. Ayni sey iki
kez yapilir:
    KONTROL : on_attract=None  -> cekim yok (bugunku davranis)
    CEKIM   : on_attract=cb    -> cekim acik
Ikisinin seat_trace'i (yanal hata zaman serisi) yan yana raporlanir.

SITL'in ZATEN CALISIYOR olmasi gerekir (safe_sitl_launcher.sh).

    python3 tools/magnet_attract_probe.py --lateral-mm 41
"""
import argparse
import asyncio
import math
import statistics
import sys
import time

from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw

from gz_system.gz_pose_monitor import GzPoseMonitor
from gz_system.gz_payload_actuator import (
    GzPayloadActuator, PAYLOAD_MODEL, VEHICLE_MODEL_NAME, HOOK_WINCH_RETRACT_M,
)
from core.config.parameters import (
    GOREV3_MAGNET_ATTRACT_GAIN, GOREV3_MAGNET_ATTRACT_MAX_STEP_M,
    GOREV3_DESCENT_ALTITUDE_M,
)

RENK = "blue"          # KIRMIZI_UCGEN'e birakilan yuk -- gorevdeki alma hedefi
YAW = 0.0


def log(msg):
    print(f"[PROBE {time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Tutucu:
    """Arka planda ayni setpoint'i tekrarlayan basit tutma dongusu.

    PX4 ~500 ms setpoint'siz kalinca Offboard'dan duser; gorev katmani da
    ayni nedenle goto_position_ned_and_hold kullaniyor.
    """

    def __init__(self, drone):
        self.drone = drone
        self.n = self.e = 0.0
        self.d = -GOREV3_DESCENT_ALTITUDE_M
        self._task = None

    async def _loop(self):
        while True:
            await self.drone.offboard.set_position_ned(
                PositionNedYaw(self.n, self.e, self.d, YAW))
            await asyncio.sleep(0.1)

    def hedef(self, n, e, d=None):
        self.n, self.e = n, e
        if d is not None:
            self.d = d

    async def basla(self, n, e, d):
        self.hedef(n, e, d)
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def dur(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None


async def pencere(actuator, drone, tutucu, monitor, lateral_m, cekim: bool,
                  timeout_s: float):
    """Tek bir oturma penceresi kos ve seat_trace dondur."""
    # Hedef: kanca, yuvanin ekseninden `lateral_m` KUZEYDE dursun.
    yuk = monitor.get(PAYLOAD_MODEL % RENK)
    arac = monitor.get(VEHICLE_MODEL_NAME)
    if yuk is None or arac is None:
        log("HATA: yuk/arac pozu okunamadi")
        return None
    off = actuator.hook_nose_ned_offset_m() or (0.0, 0.0)
    pv = await drone.telemetry.position_velocity_ned().__aiter__().__anext__()
    # dunya ENU: x=Dogu, y=Kuzey
    d_n = (yuk[1] - arac[1]) - off[0] + lateral_m
    d_e = (yuk[0] - arac[0]) - off[1]
    hedef_n = pv.position.north_m + d_n
    hedef_e = pv.position.east_m + d_e
    log(f"{'CEKIM' if cekim else 'KONTROL'}: hedef NED ({hedef_n:+.3f}, {hedef_e:+.3f}), "
        f"kanca ofseti ({off[0]:+.3f}, {off[1]:+.3f}), istenen yanal {lateral_m*1000:.0f} mm")

    await tutucu.basla(hedef_n, hedef_e, -0.9)
    await asyncio.sleep(6.0)                      # 0.9 m'de sakinles
    tutucu.hedef(hedef_n, hedef_e, -GOREV3_DESCENT_ALTITUDE_M)
    await asyncio.sleep(6.0)                      # 0.30 m'ye in

    await actuator.extend_winch_for(GOREV3_DESCENT_ALTITUDE_M)

    async def _on_attract(dn, de, dist_m):
        step_n = dn * GOREV3_MAGNET_ATTRACT_GAIN
        step_e = de * GOREV3_MAGNET_ATTRACT_GAIN
        mag = math.hypot(step_n, step_e)
        if mag > GOREV3_MAGNET_ATTRACT_MAX_STEP_M and mag > 0:
            k = GOREV3_MAGNET_ATTRACT_MAX_STEP_M / mag
            step_n *= k
            step_e *= k
        tutucu.hedef(tutucu.n + step_n, tutucu.e + step_e)
        log(f"  cekim adimi: d={dist_m*1000:5.1f} mm  adim=({step_n*1000:+5.1f}, "
            f"{step_e*1000:+5.1f}) mm")

    seated = await actuator._await_seating(RENK, timeout_s,
                                           on_attract=_on_attract if cekim else None)
    rapor = actuator.last_seating_report or {}
    await actuator.set_winch(HOOK_WINCH_RETRACT_M)
    tutucu.hedef(tutucu.n, tutucu.e, -1.5)
    await asyncio.sleep(5.0)
    return {"seated": seated, "rapor": rapor}


def ozet(ad, sonuc):
    if not sonuc:
        return f"{ad}: OLCULEMEDI"
    r = sonuc["rapor"]
    tr = r.get("seat_trace") or []
    lats = [s[2] for s in tr if len(s) > 2 and s[2] is not None]
    ma = r.get("magnet_attract") or {}
    if not lats:
        return f"{ad}: seated={sonuc['seated']} -- seat_trace bos"
    return (f"{ad}: seated={sonuc['seated']}  ornek={len(lats)}  "
            f"yanal ilk={lats[0]:.1f} son={lats[-1]:.1f} min={min(lats):.1f} "
            f"medyan={statistics.median(lats):.1f} mm  "
            f"17.5mm_alti={sum(1 for v in lats if v <= 17.5)}/{len(lats)}  "
            f"cekim={ma.get('engaged')} adim={ma.get('steps')}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="udp://:14540")
    ap.add_argument("--lateral-mm", type=float, default=41.0)
    ap.add_argument("--timeout", type=float, default=25.0)
    args = ap.parse_args()

    monitor = GzPoseMonitor()
    await monitor.start()
    actuator = GzPayloadActuator("/v34/set_payload_state", pose_monitor=monitor)

    drone = System()
    await drone.connect(system_address=args.url)
    async for st in drone.core.connection_state():
        if st.is_connected:
            break
    async for h in drone.telemetry.health():
        if h.is_global_position_ok and h.is_home_position_ok:
            break
    log("baglandi")

    await drone.action.set_takeoff_altitude(2.0)
    await drone.action.arm()
    await drone.action.takeoff()
    async for p in drone.telemetry.position():
        if p.relative_altitude_m >= 1.8:
            break
    await asyncio.sleep(3.0)
    log("2 m'de")

    tutucu = Tutucu(drone)
    pv = await drone.telemetry.position_velocity_ned().__aiter__().__anext__()
    await drone.offboard.set_position_ned(
        PositionNedYaw(pv.position.north_m, pv.position.east_m, -2.0, YAW))
    try:
        await drone.offboard.start()
    except OffboardError as e:
        log(f"offboard baslatilamadi: {e}")
        return 1
    await tutucu.basla(pv.position.north_m, pv.position.east_m, -0.55)
    await asyncio.sleep(8.0)
    log("0.55 m'de -- yuk birakiliyor")
    await actuator.release_payload_at_kirmizi_ucgen()
    await asyncio.sleep(4.0)
    tutucu.hedef(tutucu.n, tutucu.e, -1.5)
    await asyncio.sleep(5.0)
    yuk = monitor.get(PAYLOAD_MODEL % RENK)
    log(f"yuk yerde: {yuk}")

    lateral = args.lateral_mm / 1000.0
    kontrol = cekimli = None
    try:
        kontrol = await pencere(actuator, drone, tutucu, monitor, lateral, False, args.timeout)
        log(ozet("KONTROL", kontrol))
        cekimli = await pencere(actuator, drone, tutucu, monitor, lateral, True, args.timeout)
        log(ozet("CEKIM  ", cekimli))
    finally:
        # VINC HER HALUKARDA TOPLANIR. Bu satirin yoklugu 2026-09-05'te
        # Gazebo'yu cokerttti: probe ucus ortasinda oldurulunce arac
        # offboard'da setpoint'siz kalip failsafe ile indi, VINC ACIKTI ve
        # kanca inis takimindan once yere degip prizmatik eklemi ezdi ->
        # kisitlama infilaki -> "ODE INTERNAL ERROR 1: assertion aabbBound
        # ... failed in collide()". Ayni sebep gercek gorevde de gecerli:
        # inisden once vinc toplanmali.
        try:
            await actuator.set_winch(HOOK_WINCH_RETRACT_M)
            log("vinc toplandi (finally)")
        except Exception:  # noqa: BLE001
            pass

    print("\n================ SONUC ================", flush=True)
    print(ozet("KONTROL (cekim yok)", kontrol), flush=True)
    print(ozet("CEKIM   (5 cm menzil)", cekimli), flush=True)

    await tutucu.dur()
    try:
        await drone.offboard.stop()
    except OffboardError:
        pass
    await drone.action.land()
    await monitor.stop()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
