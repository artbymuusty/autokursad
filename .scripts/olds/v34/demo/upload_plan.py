#!/usr/bin/env python3
"""Bir QGroundControl .plan dosyasini araca yukler ve GERI OKUYARAK dogrular.

NEDEN AYRI BIR ARAC
-------------------
Gorev 2 rotayi KENDISI uretmez: `Gorev2Orchestrator` yalnizca aracin uzerinde
HAZIR bir rota olup olmadigini `confirm_existing_mission()` ile teyit eder
(bkz. core/mission/phase.py MISSION_ROUTE_CONFIRM yorumu). Rotayi yuklemek
operatorun QGroundControl'deki isidir. Demo'da operator yok, o yuzden bu
script QGC'nin TEK bu isini yapar -- baska hicbir seye dokunmaz:
yuklemez-baslatmaz, arm etmez, mod degistirmez.

DOGRULAMA
---------
Yukleme "ack" almasi yetmez: PX4'e giden ile .plan'da yazan ayni mi, geri
indirip item item karsilastirilir. Uyusmazlik exit 1'dir -- demo o plana
gorev kosmadan durur, cunku yanlis rotayla ucan bir gorev "gorev testi"
degildir.

Exit: 0 = yuklendi ve dogrulandi, 1 = hata.
"""
import asyncio
import json
import math
import sys
from pathlib import Path

from mavsdk import System

CONNECTION = "udp://:14540"
CONNECT_TIMEOUT_S = 30.0


def _log(msg: str) -> None:
    print(f"[UPLOAD] {msg}", flush=True)


def _plan_items(plan_path: Path) -> list[dict]:
    d = json.loads(plan_path.read_text())
    return d.get("mission", {}).get("items", [])


async def main() -> int:
    if len(sys.argv) < 2:
        _log("kullanim: upload_plan.py <plan.plan>")
        return 1
    plan = Path(sys.argv[1]).expanduser().resolve()
    if not plan.is_file():
        _log(f"HATA: plan dosyasi yok: {plan}")
        return 1

    expected = _plan_items(plan)
    _log(f"plan: {plan.name}  ({len(expected)} item, dosyadan okundu)")

    drone = System()
    await drone.connect(system_address=CONNECTION)

    _log(f"baglaniliyor: {CONNECTION} (timeout {CONNECT_TIMEOUT_S:.0f}s)")
    try:
        async def _wait():
            async for st in drone.core.connection_state():
                if st.is_connected:
                    return
        await asyncio.wait_for(_wait(), timeout=CONNECT_TIMEOUT_S)
    except asyncio.TimeoutError:
        _log("HATA: arac bulunamadi -- SITL calisiyor mu?")
        return 1
    _log("arac bagli")

    # import -> clear -> upload. clear'i import'tan SONRA yapiyoruz ki
    # import basarisiz olursa aracin uzerindeki mevcut rota silinmis olmasin.
    try:
        imported = await drone.mission_raw.import_qgroundcontrol_mission(str(plan))
    except Exception as e:
        _log(f"HATA: .plan ayristirilamadi: {e}")
        return 1
    items = list(imported.mission_items)
    _log(f"ayristirildi: {len(items)} raw MAVLink item")

    try:
        await drone.mission_raw.clear_mission()
        _log("aractaki eski rota silindi")
        await drone.mission_raw.upload_mission(items)
        _log("yukleme ack alindi")
    except Exception as e:
        _log(f"HATA: yukleme basarisiz: {e}")
        return 1

    # --- geri okuyup dogrula -------------------------------------------
    try:
        result = await drone.mission_raw.download_mission()
    except Exception as e:
        _log(f"HATA: geri okuma basarisiz: {e}")
        return 1
    back = list(result[0] if isinstance(result, tuple) else result)

    if len(back) != len(items):
        _log(f"HATA: item sayisi uyusmuyor -- yuklenen {len(items)}, okunan {len(back)}")
        return 1

    mismatch = 0
    for a, b in zip(items, back):
        if a.command != b.command:
            mismatch += 1
            continue
        # lat/lon int7 (1e-7 derece) olarak tasinir; z float metredir.
        if a.x != b.x or a.y != b.y or not math.isclose(a.z, b.z, abs_tol=0.01):
            mismatch += 1

    _log(f"geri okundu: {len(back)} item, {mismatch} uyusmazlik")
    for it in back:
        _log(f"  seq={it.seq:<3} cmd={it.command:<4} lat={it.x/1e7:.7f} lon={it.y/1e7:.7f} alt={it.z:.1f}")

    if mismatch:
        _log("HATA: aractaki rota .plan ile ayni degil")
        return 1

    _log("DOGRULANDI: aractaki rota .plan ile birebir ayni")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
