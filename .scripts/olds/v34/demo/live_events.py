#!/usr/bin/env python3
"""Calisan gorevin ONEMLI olaylarini canli olarak stdout'a yazar.

Olay akisi (logs/mission_<id>.jsonl) EventStore tarafindan satir satir
yazildigi icin, dosyayi takip edip yalnizca operatorun izlerken gormek
istedigi kodlari basmak yeterli -- 10 Hz akan VISION_FRAME_PROCESSED /
VEHICLE_TELEMETRY / WATCHDOG_UPDATED gurultusu disarida kalir.

Gorev daha baslamadan calistirilabilir: yeni bir mission_*.jsonl belirene
kadar bekler, sonra ona baglanir. Salt okunur.
"""
import glob
import json
import os
import sys
import time

LOG_DIR = sys.argv[1] if len(sys.argv) > 1 else "logs"
SINCE = time.time() - 5

KEY = {
    "MISSION_STARTED", "CONNECTED", "ARMED", "DISARMED", "ALTITUDE_REACHED",
    "CHECKPOINT_SAVED", "MISSION_ROUTE_CONFIRMED", "MISSION_ROUTE_MISSING",
    "MISSION_CURRENT_ITEM_SET", "MISSION_STARTED_ONBOARD", "MISSION_ROUTE_RESUMED",
    "TARGET_ACQUIRED", "TARGET_LOCKED", "TRACK_READY", "CENTERING_CONVERGED",
    "OFFBOARD_STARTED", "GPS_SAVED", "PAYLOAD_RELEASED", "PAYLOAD_RELEASE_CONFIRMED",
    "SEARCH_COMPLETE", "GOREV2_COMPLETE", "GOREV3_START", "GOREV3_COMPLETE",
    "GOREV3_PHASE_FAILED", "HOOK_LOCKED", "RECEIVER_DETECTED",
    "MISSION_ABORT_REQUESTED", "WATCHDOG_FIRED", "LANDED", "MISSION_COMPLETE",
}
LOUD = {"WARNING", "ERROR", "CRITICAL"}


def newest():
    fs = [f for f in glob.glob(os.path.join(LOG_DIR, "mission_*.jsonl"))
          if os.path.getmtime(f) > SINCE]
    return max(fs, key=os.path.getmtime) if fs else None


def main():
    path = None
    while path is None:
        path = newest()
        if path is None:
            time.sleep(1)
    print(f">>> gorev olay akisi: {os.path.basename(path)}", flush=True)

    t0 = None
    with open(path, "r", errors="replace") as fh:
        idle = 0
        while True:
            line = fh.readline()
            if not line:
                idle += 1
                if idle > 900:          # 90 s sessizlik -> gorev bitmis
                    break
                time.sleep(0.1)
                continue
            idle = 0
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if t0 is None:
                t0 = e["ts"]
            code = e.get("code")
            sev = e.get("severity")
            phase = code == "MISSION_PHASE_CHANGED"
            if not (phase or code in KEY or sev in LOUD):
                continue
            t = e["ts"] - t0
            msg = (e.get("message") or "").strip()
            if phase:
                to = (e.get("data") or {}).get("to_phase", "")
                print(f"  t+{t:6.1f}s  >> FAZ: {to}", flush=True)
            else:
                mark = "!! " if sev in LOUD else "   "
                print(f"  t+{t:6.1f}s  {mark}{code}{('  ' + msg[:90]) if msg else ''}", flush=True)
            if code == "MISSION_PHASE_CHANGED" and (e.get("data") or {}).get("to_phase") in (
                    "MISSION_COMPLETE", "MISSION_FAILED", "MISSION_ABORTED", "MISSION_TIMEOUT"):
                pass
    print(">>> olay akisi sona erdi", flush=True)


if __name__ == "__main__":
    main()
