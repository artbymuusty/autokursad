#!/usr/bin/env python3
"""Bir mission_*.jsonl olay akisini insan-okur bir gorev raporuna indirger.

Demo'nun "izlenebilir" kismi: her plan icin ne oldugunu 5000 satirlik ham
akistan degil, faz gecisleri + uyari/hata satirlari uzerinden okuyabilmek.
Hicbir seye yazmaz, yalnizca okur.

Cikti bolumleri:
  BASLIK   mission_id, sure, olay sayisi
  FAZLAR   MISSION_PHASE_CHANGED zinciri (t+saniye)
  KILOMETRE TASLARI  arm/takeoff/rota/tespit/birakma gibi tekil olaylar
  SORUNLAR WARNING ve uzeri her olay
  SONUC    terminal faz (MISSION_COMPLETE/FAILED/ABORTED/TIMEOUT) veya "yarim"

Exit: 0 = MISSION_COMPLETE, 2 = baska bir terminal faz, 3 = terminal faza hic
ulasilmamis (surec disaridan kesilmis), 1 = dosya okunamadi.
"""
import json
import sys
from pathlib import Path

TERMINAL = {"MISSION_COMPLETE", "MISSION_FAILED", "MISSION_ABORTED", "MISSION_TIMEOUT"}

# Tekil, anlamli olaylar -- 10 Hz akan DEBUG gurultusu (VISION_FRAME_PROCESSED,
# VEHICLE_TELEMETRY, WATCHDOG_UPDATED, CENTERING_STEP ...) bilerek disarida.
MILESTONES = {
    "CONNECTED", "ARMED", "DISARMED", "TAKEOFF_COMPLETE",
    "CHECKPOINT_SAVED", "MISSION_ROUTE_CONFIRMED", "MISSION_ROUTE_MISSING",
    "MISSION_STARTED", "MISSION_STARTED_ONBOARD", "MISSION_CURRENT_ITEM_SET",
    "TARGET_ACQUIRED", "TARGET_LOCKED", "TRACK_READY",
    "OFFBOARD_STARTED", "OFFBOARD_STOPPED", "CENTERING_CONVERGED",
    "GPS_SAVED", "PAYLOAD_RELEASED", "PAYLOAD_RELEASE_CONFIRMED",
    "SEARCH_COMPLETE", "GOREV2_COMPLETE", "GOREV3_START", "GOREV3_COMPLETE",
    "RETURN_TO_CHECKPOINT", "LANDED", "MISSION_COMPLETE",
}
LOUD = {"WARNING", "ERROR", "CRITICAL"}


def main() -> int:
    if len(sys.argv) < 2:
        print("kullanim: summarize_mission.py <mission_xxx.jsonl>")
        return 1
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"HATA: olay dosyasi yok: {path}")
        return 1

    events = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # yarim yazilmis son satir (surec kesilmisse normal)

    if not events:
        print(f"HATA: {path.name} icinde ayristirilabilir olay yok")
        return 1

    t0 = events[0]["ts"]
    span = events[-1]["ts"] - t0
    mid = events[0].get("mission_id", "?")

    def rel(e):
        return f"t+{e['ts'] - t0:7.1f}s"

    print(f"  mission_id : {mid}")
    print(f"  sure       : {span:.1f}s  ({len(events)} olay)")
    print(f"  kaynak     : {path}")

    phases = [e for e in events if e.get("code") == "MISSION_PHASE_CHANGED"]
    print(f"\n  FAZLAR ({len(phases)})")
    if not phases:
        print("    (hicbir faz gecisi yok -- gorev baslamadan dusmus)")
    for e in phases:
        to = (e.get("data") or {}).get("to_phase") or e.get("message", "")
        print(f"    {rel(e)}  {to}")

    miles = [e for e in events if e.get("code") in MILESTONES]
    print(f"\n  KILOMETRE TASLARI ({len(miles)})")
    if not miles:
        print("    (yok)")
    for e in miles:
        msg = (e.get("message") or "").strip()
        print(f"    {rel(e)}  {e['code']}{('  -- ' + msg) if msg else ''}")

    loud = [e for e in events if e.get("severity") in LOUD]
    print(f"\n  SORUNLAR ({len(loud)} WARNING+)")
    if not loud:
        print("    (temiz)")
    for e in loud[:60]:
        print(f"    {rel(e)}  [{e['severity']}] {e['code']}: {(e.get('message') or '').strip()}")
    if len(loud) > 60:
        print(f"    ... ve {len(loud) - 60} tane daha (tam liste: {path.name})")

    terminal = None
    for e in reversed(phases):
        to = (e.get("data") or {}).get("to_phase") or ""
        if to in TERMINAL:
            terminal = to
            break

    print()
    if terminal == "MISSION_COMPLETE":
        print("  SONUC: MISSION_COMPLETE")
        return 0
    if terminal:
        print(f"  SONUC: {terminal}")
        return 2
    print("  SONUC: terminal faza ulasilmadi -- surec disaridan kesilmis "
          "(timeout/Ctrl-C) ya da cokmus olabilir")
    return 3


if __name__ == "__main__":
    sys.exit(main())
