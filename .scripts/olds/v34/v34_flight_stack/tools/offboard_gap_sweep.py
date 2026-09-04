#!/usr/bin/env python3
"""MAVSDK Offboard geçiş hatası: pause→start bekleme süresi taraması.

NEDEN VAR (kök neden, docs/gorevF1-offboard-start-kok-neden.md)
--------------------------------------------------------------
MAVSDK v3.17.2'de `CommandIdentification` DO_SET_MODE (176) için komut
PARAMETRELERINI icermiyor (maybe_param1/2 yalnizca REQUEST_MESSAGE ve
SET_MESSAGE_INTERVAL icin doldurulur). Dolayisiyla:

    mission.pause_mission()  -> DO_SET_MODE 176, main=4 (AUTO/LOITER)
    offboard.start()         -> DO_SET_MODE 176, main=6 (OFFBOARD)

ikisinin kimligi BIREBIR AYNI: {0, 0, 176, 1, 1}. pause'un ACK'i hala
yoldayken start() kendi is kalemini kuyruga koyarsa, gelen ACK offboard
kalemine ATFEDILIP onu Success ile coziyor -- offboard komutu HIC
GONDERILMEDEN. Olculen: %41.7 sessiz basarisizlik.

Bu arac, iki 176 komutu arasina konan beklemenin hangi degerde cakisma
penceresini kapattigini olcer.

SALT TANI: gorev koduna hic dokunmaz, kendi MAVSDK baglantisini kurar.
SITL'in ZATEN CALISIYOR olmasi gerekir.

    python3 tools/offboard_gap_sweep.py --gaps 0,0.05,0.1,0.2 --n 25

Cikti: bekleme basina basarisizlik orani + start() sure dagilimi.
3.4 ms civari bir start() suresi "sahte basari" imzasidir (pause ACK'inin
kalan yolu); gercek gonderim ~11-14 ms round-trip ister.
"""
import argparse, asyncio, statistics, sys, time

from mavsdk import System
from mavsdk.offboard import VelocityBodyYawspeed


async def flight_mode(drone):
    async for m in drone.telemetry.flight_mode():
        return str(m)


async def one_attempt(drone, gap_s, settle_s):
    """pause -> [bekleme] -> setpoint -> start -> 3 s mod yoklamasi."""
    await drone.mission.pause_mission()
    if gap_s:
        await asyncio.sleep(gap_s)
    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
    t0 = time.monotonic()
    err = None
    try:
        await drone.offboard.start()
    except Exception as e:                      # noqa: BLE001
        err = repr(e)
    dur = time.monotonic() - t0

    ok = False
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if await flight_mode(drone) == "OFFBOARD":
            ok = True
            break
        await asyncio.sleep(0.2)

    try:
        await drone.offboard.stop()
    except Exception:                            # noqa: BLE001
        pass
    try:
        await drone.mission.start_mission()
    except Exception:                            # noqa: BLE001
        pass
    await asyncio.sleep(settle_s)
    return ok, dur, err


async def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gaps", default="0,0.05,0.1,0.2",
                    help="virgulle ayrilmis bekleme sureleri (saniye)")
    ap.add_argument("--n", type=int, default=25, help="bekleme basina deneme")
    ap.add_argument("--settle", type=float, default=2.0, help="denemeler arasi bekleme")
    ap.add_argument("--url", default="udp://:14540")
    args = ap.parse_args()
    gaps = [float(g) for g in args.gaps.split(",")]

    drone = System()
    print(f"[SWEEP] baglaniliyor: {args.url}", flush=True)
    await drone.connect(system_address=args.url)
    async for st in drone.core.connection_state():
        if st.is_connected:
            break
    async for h in drone.telemetry.health():
        if h.is_global_position_ok and h.is_home_position_ok:
            break
    print("[SWEEP] arm + takeoff", flush=True)
    await drone.action.set_takeoff_altitude(15.0)
    await drone.action.arm()
    await drone.action.takeoff()
    await asyncio.sleep(18)
    try:
        await drone.mission.start_mission()
    except Exception as e:                       # noqa: BLE001
        print(f"[SWEEP] start_mission: {e}", flush=True)
    await asyncio.sleep(5)

    results = {}
    for gap in gaps:
        oks, durs, fails = 0, [], []
        for i in range(1, args.n + 1):
            ok, dur, err = await one_attempt(drone, gap, args.settle)
            durs.append(dur * 1000.0)
            oks += 1 if ok else 0
            if not ok:
                fails.append(round(dur * 1000.0, 1))
            print(f"[SWEEP] gap={gap*1000:5.0f}ms  {i:3d}/{args.n}  "
                  f"{'OK  ' if ok else 'FAIL'}  start={dur*1000:6.2f} ms  err={err}",
                  flush=True)
        results[gap] = (oks, args.n, durs, fails)

    print("\n=========== OZET ===========", flush=True)
    print(f"{'bekleme':>9} {'basarisiz':>12} {'oran':>7} "
          f"{'start() ms: min/ortanca/max':>30}  basarisizlarin sureleri", flush=True)
    for gap, (oks, n, durs, fails) in results.items():
        nf = n - oks
        print(f"{gap*1000:7.0f}ms {nf:6d}/{n:<5d} {100.0*nf/n:6.1f}% "
              f"{min(durs):9.1f}/{statistics.median(durs):.1f}/{max(durs):.1f}   {fails}",
              flush=True)


asyncio.run(main())
