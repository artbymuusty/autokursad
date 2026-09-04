#!/usr/bin/env python3
"""GOREV J: sarkac periyodu olcumu icin KONTROLLU YANAL ADIM ucusu.

NEDEN VAR: MAGNET_DWELL_S olculen sarkac periyodundan turetiliyor. Eski
0.831 s degeri "6 m yanal adim" kabul testinden gelmisti (hook_seating.py:195).
Kanca 25 -> 31 cm olunca o olcum gecersiz; ayni uyarani tekrar uretmek icin
bu arac araci 3 m'ye kaldirir, salinim sonene kadar bekler, sonra TEK BIR
6 m yanal adim komutu verir ve kancanin serbest salinmasi icin bekler.

Olcumu bu arac YAPMAZ -- paralel calisan tools/measure_hook_pendulum.py
kaydeder. Burasi yalnizca uyarani uretir, zaman damgalarini basar.

    python3 tools/pendulum_step_flight.py --alt 3.0 --step 6.0 --settle 12 --hold 30
"""
import argparse
import asyncio
import sys
import time

from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw


def damga(msg: str) -> None:
    print(f"[ADIM {time.time():.3f}] {msg}", flush=True)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="udp://:14540")
    ap.add_argument("--alt", type=float, default=3.0)
    ap.add_argument("--step", type=float, default=6.0)
    ap.add_argument("--settle", type=float, default=12.0, help="adimdan ONCE sakinlesme")
    ap.add_argument("--hold", type=float, default=30.0, help="adimdan SONRA kayit suresi")
    args = ap.parse_args()

    drone = System()
    await drone.connect(system_address=args.url)
    damga("baglaniyor...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            break
    damga("baglandi")

    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            break
    damga("konum saglikli")

    await drone.action.set_takeoff_altitude(args.alt)
    await drone.action.arm()
    damga("arm")
    await drone.action.takeoff()
    damga(f"takeoff -> {args.alt} m")

    # irtifaya ulasmayi bekle
    async for pos in drone.telemetry.position():
        if pos.relative_altitude_m >= args.alt * 0.92:
            break
    damga(f"irtifa tamam ({args.alt} m)")

    # kalkis salinimi sonsun
    await asyncio.sleep(args.settle)
    damga("sakinlesme bitti")

    await drone.offboard.set_position_ned(PositionNedYaw(0.0, 0.0, -args.alt, 0.0))
    try:
        await drone.offboard.start()
    except OffboardError as e:
        damga(f"offboard baslatilamadi: {e._result.result}")
        await drone.action.land()
        return 1
    damga("offboard basladi (0,0)")
    await asyncio.sleep(3.0)

    damga(f"ADIM KOMUTU: kuzey {args.step} m  >>> SALINIM BASLANGICI")
    t_step = time.time()
    await drone.offboard.set_position_ned(PositionNedYaw(args.step, 0.0, -args.alt, 0.0))

    await asyncio.sleep(args.hold)
    damga(f"kayit penceresi bitti ({args.hold:.0f} s, adim t={t_step:.3f})")

    try:
        await drone.offboard.stop()
    except OffboardError:
        pass
    await drone.action.land()
    damga("inis komutu verildi")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
