#!/usr/bin/env python3
"""SITL'in gercekten UCUSA HAZIR oldugunu bekler -- surec var olmasi yetmez.

`make px4_sitl gz_x500_mono_cam_down` donduginde PX4 surec olarak ayaktadir
ama EKF henuz yakinsamamis, global pozisyon yoktur; o anda rota yuklemek ya
da gorev baslatmak sessizce reddedilir. Demo bu yuzden uc kosulu ayri ayri
bekler ve HANGISINDE takildigini yazar -- "sadece calismadi" cikti degil,
teshis ciktisi uretir.

  1. MAVLink baglantisi (heartbeat)
  2. global pozisyon + home pozisyon kilidi (EKF yakinsamasi)
  3. is_armable

Exit: 0 = hazir, 1 = timeout (hangi asamada takildigi stdout'ta).
"""
import asyncio
import sys
import time

from mavsdk import System

CONNECTION = "udp://:14540"
DEFAULT_TIMEOUT_S = 180.0


def _log(msg: str) -> None:
    print(f"[WAIT] {msg}", flush=True)


async def main() -> int:
    timeout = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TIMEOUT_S
    t0 = time.time()
    drone = System()
    await drone.connect(system_address=CONNECTION)

    async def _connected():
        async for st in drone.core.connection_state():
            if st.is_connected:
                return

    async def _ekf():
        async for h in drone.telemetry.health():
            if h.is_global_position_ok and h.is_home_position_ok:
                return

    async def _armable():
        async for h in drone.telemetry.health():
            if h.is_armable:
                return

    for label, coro in (("1/3 MAVLink heartbeat", _connected()),
                        ("2/3 global+home pozisyon (EKF)", _ekf()),
                        ("3/3 is_armable", _armable())):
        remaining = timeout - (time.time() - t0)
        if remaining <= 0:
            _log(f"TIMEOUT: {label} asamasina hic sira gelmedi")
            return 1
        _log(f"bekleniyor: {label} (kalan {remaining:.0f}s)")
        try:
            await asyncio.wait_for(coro, timeout=remaining)
        except asyncio.TimeoutError:
            _log(f"TIMEOUT: {label} saglanamadi ({timeout:.0f}s)")
            return 1
        _log(f"  -> OK ({time.time() - t0:.1f}s)")

    _log(f"arac ucusa hazir ({time.time() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
