#!/usr/bin/env python3
"""FAZ 4 / ADIM 3 -- payload halat hatasinin gerçekten bittiğinin KANITI.

NEDEN AYRI BIR ARAC
-------------------
"generator payload'i spawn'a kilitliyor" demek yetmez. 2026-08-30'da
olculen hata sunun gibiydi (mission_d098c1884509, lane_A_1way_gorev):

    t+ 8.3s  alt= 0.47 m   TAKEOFF
    t+10.7s  alt= 3.09 m   TAKEOFF
    t+12.5s  alt= 4.90 m   TAKEOFF   <- ZIRVE
    t+15.2s  alt=-0.35 m   TAKEOFF   <- 2.7 saniyede yere geri
    t>60s    medyan -0.02 m  (763 ornek, 483 s boyunca)

Yani arac 4.90 m'ye cikip geri cekilmisti: X=0'daki payload'lar X=25'teki
araca DetachableJoint ile bagliydi, yani 25 m'lik yere cakili bir halat.

Bu script AYNI olcumu yapar ve gecme/kalma kriterini ONCEDEN sabitler:

  P1  zirve irtifa       >= 14.0 m           (hedef 15 m, 1 m tolerans)
  P2  15 m civarinda kalis  >= 10 s kesintisiz, alt >= 14.0 m
  P3  GERI CEKILME YOK   : 4 m'yi asmis bir ucusta irtifa bir daha
                           2 m'nin altina DUSMEMELI (eski hatanin imzasi)
  P4  yatay surukleme yok: spawn'dan yatay sapma < 5 m

Ucus sonunda iner ve disarm eder. Ham zaman serisi JSON olarak yazilir.

Exit: 0 = TUM KRITERLER PASS, 1 = en az biri FAIL / baglanti yok.
"""
import asyncio
import json
import math
import sys
import time
from pathlib import Path

from mavsdk import System

CONNECTION = "udp://:14540"
TARGET_ALT_M = 15.0
CONNECT_TIMEOUT_S = 60.0
CLIMB_TIMEOUT_S = float(__import__("os").environ.get("TAKEOFF_CLIMB_TIMEOUT_S", 90.0))
HOLD_REQUIRED_S = 10.0
SAMPLE_HZ = 5.0

P1_PEAK_MIN_M = 14.0
P2_HOLD_MIN_M = 14.0
P3_TRIGGER_M = 4.0      # bunu astiktan sonra
P3_FLOOR_M = 2.0        # bunun altina bir daha dusmemeli
P4_MAX_DRIFT_M = 5.0


def log(m): print(f"[TAKEOFF] {m}", flush=True)


async def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("takeoff_proof.json")

    drone = System()
    await drone.connect(system_address=CONNECTION)
    log(f"baglaniliyor: {CONNECTION}")
    try:
        async def _c():
            async for st in drone.core.connection_state():
                if st.is_connected:
                    return
        await asyncio.wait_for(_c(), timeout=CONNECT_TIMEOUT_S)
    except asyncio.TimeoutError:
        log("HATA: arac yok"); return 1
    log("arac bagli")

    try:
        async def _h():
            async for h in drone.telemetry.health():
                if h.is_armable and h.is_global_position_ok and h.is_home_position_ok:
                    return
        await asyncio.wait_for(_h(), timeout=CONNECT_TIMEOUT_S)
    except asyncio.TimeoutError:
        log("HATA: arac armable olmadi"); return 1
    log("arac armable")

    async for p in drone.telemetry.position():
        home_lat, home_lon = p.latitude_deg, p.longitude_deg
        break
    log(f"home: {home_lat:.7f}, {home_lon:.7f}")

    await drone.action.set_takeoff_altitude(TARGET_ALT_M)
    await drone.action.arm()
    log("ARM edildi")
    await drone.action.takeoff()
    log(f"TAKEOFF komutu verildi (hedef {TARGET_ALT_M:.1f} m)")

    # --- ornekleme -------------------------------------------------------
    t0 = time.monotonic()
    series = []
    hold_start = None
    hold_best = 0.0
    deadline = t0 + CLIMB_TIMEOUT_S
    async for p in drone.telemetry.position():
        t = time.monotonic() - t0
        alt = p.relative_altitude_m
        dn = math.radians(p.latitude_deg - home_lat) * 6378137.0
        de = math.radians(p.longitude_deg - home_lon) * 6378137.0 * math.cos(math.radians(home_lat))
        series.append({"t": round(t, 2), "alt": round(alt, 3),
                       "north": round(dn, 3), "east": round(de, 3)})
        if alt >= P2_HOLD_MIN_M:
            hold_start = t if hold_start is None else hold_start
            hold_best = max(hold_best, t - hold_start)
        else:
            hold_start = None
        if len(series) % int(SAMPLE_HZ * 5) == 0:
            log(f"  t+{t:5.1f}s  alt={alt:6.2f} m  yatay={math.hypot(dn, de):5.2f} m")
        if hold_best >= HOLD_REQUIRED_S or time.monotonic() > deadline:
            break
        await asyncio.sleep(1.0 / SAMPLE_HZ)

    # --- kriterler -------------------------------------------------------
    alts = [s["alt"] for s in series]
    peak = max(alts) if alts else 0.0
    drift = max((math.hypot(s["north"], s["east"]) for s in series), default=0.0)

    p3_ok, p3_detail = True, "4 m hic asilmadi"
    seen4 = False
    for s in series:
        if s["alt"] >= P3_TRIGGER_M:
            seen4 = True; p3_detail = "4 m asildi, bir daha 2 m altina dusmedi"
        elif seen4 and s["alt"] < P3_FLOOR_M:
            p3_ok = False
            p3_detail = f"GERI CEKILME: t+{s['t']}s'de {s['alt']:.2f} m (eski hatanin imzasi)"
            break

    res = {
        "P1_peak_altitude_m": {"value": round(peak, 3), "min": P1_PEAK_MIN_M, "pass": peak >= P1_PEAK_MIN_M},
        "P2_hold_s_at_or_above_14m": {"value": round(hold_best, 1), "min": HOLD_REQUIRED_S,
                                      "pass": hold_best >= HOLD_REQUIRED_S},
        "P3_no_pullback": {"detail": p3_detail, "pass": p3_ok},
        "P4_horizontal_drift_m": {"value": round(drift, 3), "max": P4_MAX_DRIFT_M,
                                  "pass": drift < P4_MAX_DRIFT_M},
        "samples": len(series),
    }
    ok = all(v["pass"] for k, v in res.items() if isinstance(v, dict) and "pass" in v)

    log("")
    log("=== KRITERLER ===")
    for k, v in res.items():
        if isinstance(v, dict) and "pass" in v:
            log(f"  {'PASS' if v['pass'] else 'FAIL'}  {k}: "
                f"{v.get('value', v.get('detail'))}")
    log(f"SONUC: {'PASS' if ok else 'FAIL'}")

    out.write_text(json.dumps({"result": res, "pass": ok, "series": series}, indent=1))
    log(f"zaman serisi: {out}")

    # --- temiz inis ------------------------------------------------------
    try:
        log("inise geciliyor")
        await drone.action.land()
        for _ in range(60):
            async for a in drone.telemetry.armed():
                armed = a; break
            if not armed:
                break
            await asyncio.sleep(1.0)
        log("indi/disarm")
    except Exception as e:
        log(f"inis sirasinda uyari: {e}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
