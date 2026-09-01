#!/usr/bin/env python3
"""Kosu kaydi uretici -- her mission/test kosusundan OLGU cikarir.

NE URETIR (VE NE URETMEZ)
-------------------------
URETIR : docs/test-history/runs/<id>.md -- kucuk, makine yazimi, YALNIZCA
         olay kaydindan TURETILEBILEN olgular. Faz zinciri, health gecisleri,
         WARN+ olaylar, sayimlar, hangi ham dosyalardan uretildigi.

URETMEZ: phase_id, Amac, Degisiklikler, Kok neden, Uygulanan cozum,
         Dogrulama, Ilgili commit, Sonraki adim. Bu alanlar icin BOS BASLIK
         BILE yazmaz -- yanlis doldurulma yuzeyi hic olusmasin diye.

         NEDEN: bu alanlar insan yargisi gerektirir. 2026-08-25'te S serisinin
         `Error 137` ile bitmesi "12 basarisiz kosu" diye yorumlanacakti; A-F
         kosulariyla karsilastirinca bunun NORMAL teardown imzasi oldugu
         (pkill -9) ortaya cikti. Bir makine bu cikarimi yapamazdi. Ayrica
         `.scripts/olds/v33/` git'te untracked oldugundan "Ilgili commit"
         icin dogru bir deger YOKTUR -- repo HEAD'i yazmak aktif olarak
         yanlis olurdu.

GUVENLIK SOZLESMESI
-------------------
Kosu kayitlari docs/test-history/runs/ ALT DIZININDE yasar.
artifact_retention.py::load_summaries() os.listdir ile YALNIZCA ust seviye
.md dosyalarini okur, alt dizinlere inmez -- yani bir kosu kaydi HICBIR
KOSULDA dogrulanmis ozet sayilamaz ve HICBIR ham veriyi silinebilir yapamaz.
Ham veri hala yalnizca insan yazimi, verify'dan gecmis bir PH-*.md ile
arsivlenebilir. Bu otomasyon kanit kapisini GEVSETMEZ.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

RUNS_DIRNAME = "runs"
NOTABLE = ("WARN", "CRITICAL", "FATAL")
# mission_logger.py dosyayi mission_<YYYYmmdd_HHMMSS>.log diye adlandirir,
# EventStore ise mission_<mission_id>.jsonl diye. Ortak anahtar yok, bu yuzden
# .log dosyasi zaman yakinligiyla eslesir (bkz. _match_console_log).
_LOG_TS = re.compile(r"mission_(\d{8}_\d{6})\.log$")


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _oneline(text, limit: int = 220) -> str:
    """Mesaji tek satira indirir ve kirpar.

    Olay mesajlari cok satirli olabilir (ornegin bir gRPC AioRpcError'in
    tam govdesi). Ham haliyle yazmak Markdown liste/tablo yapisini bozar.
    Kirpma OLGUYU degistirmez -- tam metin her zaman ham .jsonl'de durur ve
    raw_artifacts ona isaret eder.
    """
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[:limit - 1] + "…"


def read_events(jsonl_path: str):
    """Olay kaydini okur. Bozuk satirlar SESSIZCE atlanmaz -- sayilir."""
    events, broken = [], 0
    with open(jsonl_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:  # noqa: BLE001
                broken += 1
    return events, broken


def _match_console_log(log_dir: str, start_ts: float, end_ts: float):
    """Kosuyla ortusen mission_<ts>.log dosyasini bulur.

    HEURISTIK, kesin degil: .log adindaki zaman damgasi dosyanin OLUSTURULMA
    anidir. Kosu penceresine dusen en gec damgayi seceriz. Eslesme
    bulunamazsa None doner ve kayitta bu acikca belirtilir.
    """
    best = None
    for path in glob.glob(os.path.join(log_dir, "mission_*.log")):
        m = _LOG_TS.search(os.path.basename(path))
        if not m:
            continue
        try:
            stamp = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S").timestamp()
        except ValueError:
            continue
        # Log, ilk olaydan biraz ONCE acilir; 120 s tolerans.
        if start_ts - 120 <= stamp <= end_ts:
            if best is None or stamp > best[0]:
                best = (stamp, path)
    return best[1] if best else None


def build_mission_record(jsonl_path: str, log_dir: str, exit_code=None) -> dict:
    events, broken = read_events(jsonl_path)
    if not events:
        raise ValueError(f"olay kaydi bos veya okunamadi: {jsonl_path}")

    ts_all = [e.get("ts", 0.0) for e in events if isinstance(e.get("ts"), (int, float))]
    start_ts, end_ts = min(ts_all), max(ts_all)

    # run_id DOSYA ADINDAN turetilir, olay govdesinden DEGIL.
    #
    # NEDEN: unrecorded_jsonls() eksik kayitlari dosya adiyla arar. Ikisi
    # farkli kaynaklardan turetilirse ve bir gun ayrisirlarsa (elle yeniden
    # adlandirilmis bir .jsonl yeter), backfill aradigini asla bulamaz ve HER
    # kosuda ayni kaydi yeniden uretir. Uretimde ayrisamazlar -- EventStore
    # dosyayi zaten mission_<mission_id>.jsonl diye adlandiriyor -- ama
    # yakinsama tek bir anahtara BAGLI olmali, iki kaynagin uyusmasina degil.
    base = os.path.basename(jsonl_path)
    mission_id = ""
    if base.startswith("mission_") and base.endswith(".jsonl"):
        mission_id = base[len("mission_"):-len(".jsonl")]
    if not mission_id:
        for e in events:
            if e.get("mission_id"):
                mission_id = e["mission_id"]
                break

    phases, health, notable = [], [], []
    centering, payload = [], []
    codes = collections.Counter()
    shapes = collections.Counter()

    for e in events:
        code = e.get("code")
        codes[code] += 1
        ts = e.get("ts", 0.0)
        data = e.get("data") or {}

        if code == "MISSION_PHASE_CHANGED":
            phases.append((ts, data.get("from_phase"), data.get("to_phase"),
                           e.get("message", "")))
        elif code == "HEALTH_STATE_CHANGED":
            health.append((ts, e.get("subsystem"), data.get("state")))
        elif code in ("CENTERING_CONVERGED", "CENTERING_TIMED_OUT"):
            centering.append((ts, code, data.get("shape_type"), data.get("altitude_m")))
        elif code == "PAYLOAD_STATE":
            payload.append((ts, data.get("shape_type"), data.get("payload_index"),
                            e.get("message", "")))
        elif code == "VISION_FRAME_PROCESSED":
            for s in (data.get("shapes") or []):
                shapes[s] += 1

        if e.get("severity") in NOTABLE:
            notable.append((ts, e.get("severity"), code, e.get("subsystem"),
                            (e.get("message") or "").strip()))

    terminal = phases[-1][2] if phases else None

    artifacts = [jsonl_path]
    pos = os.path.join(log_dir, f"mission_positions_{mission_id}.json")
    if os.path.isfile(pos):
        artifacts.append(pos)
    console = _match_console_log(log_dir, start_ts, end_ts)
    if console:
        artifacts.append(console)

    return {
        "kind": "mission_run",
        "run_id": mission_id,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "duration_s": round(end_ts - start_ts, 1),
        "exit_code": exit_code,
        "terminal_phase": terminal,
        "event_count": len(events),
        "broken_lines": broken,
        "phases": phases,
        "health": health,
        "notable": notable,
        "centering": centering,
        "payload": payload,
        "codes": codes,
        "shapes": shapes,
        "artifacts": artifacts,
        "console_log_matched": console is not None,
    }


def build_pytest_record(run_id: str, exit_status: int, duration_s: float,
                        counts: dict, failures: list, start_ts=None) -> dict:
    end_ts = (start_ts + duration_s) if start_ts is not None else None
    return {
        "kind": "pytest_run",
        "run_id": run_id,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "duration_s": round(duration_s, 1),
        "exit_code": exit_status,
        "terminal_phase": None,
        "event_count": sum(counts.values()),
        "broken_lines": 0,
        "phases": [], "health": [], "centering": [], "payload": [],
        "notable": [(None, "FAIL", "TEST_FAILED", nodeid, msg)
                    for nodeid, msg in failures],
        "codes": collections.Counter(counts),
        "shapes": collections.Counter(),
        "artifacts": [],
        "console_log_matched": False,
    }


# =============================================================================
# Render -- YALNIZCA olgu
# =============================================================================

HEADER_NOTE = """> Bu dosya `tools/run_record.py` tarafından üretildi. Yalnızca olay
> kaydından **türetilebilen olguları** içerir: ne olduğunu söyler, ne
> anlama geldiğini **söylemez**. Kök neden, amaç, doğrulama ve sonraki
> adım insan yargısıdır ve phase özetine (`docs/test-history/PH-*.md`)
> aittir. Bu kayıt doğrulanmış bir özet **değildir** ve hiçbir ham veriyi
> silinebilir yapmaz."""


def _rel(path: str, repo_root: str) -> str:
    try:
        return os.path.relpath(path, repo_root)
    except ValueError:
        return path


def render(rec: dict, repo_root: str) -> str:
    L = []
    a = L.append
    a("---")
    a(f"kind: {rec['kind']}")
    a("machine_generated: true")
    a("generator: tools/run_record.py")
    a(f"run_id: {rec['run_id']}")
    if rec["start_ts"]:
        a(f"date: {datetime.fromtimestamp(rec['start_ts'], timezone.utc).strftime('%Y-%m-%d')}")
        a(f"started: {_iso(rec['start_ts'])}")
        a(f"ended: {_iso(rec['end_ts'])}")
    a(f"duration_s: {rec['duration_s']}")
    a(f"exit_code: {rec['exit_code'] if rec['exit_code'] is not None else '~'}")
    if rec["terminal_phase"]:
        a(f"terminal_phase: {rec['terminal_phase']}")
    a(f"event_count: {rec['event_count']}")
    if rec["broken_lines"]:
        a(f"broken_lines: {rec['broken_lines']}")
    a("raw_artifacts:")
    if rec["artifacts"]:
        for p in rec["artifacts"]:
            a(f'  - "{_rel(p, repo_root)}"')
    else:
        a("  []")
    a("---")
    a("")
    a(f"# Koşu kaydı — `{rec['run_id']}`")
    a("")
    a(HEADER_NOTE)
    a("")

    if rec["phases"]:
        a("## Faz zinciri")
        a("")
        t0 = rec["start_ts"]
        for ts, frm, to, msg in rec["phases"]:
            # message zaten "<from> -> <to>" ile basliyor; yalnizca ondan
            # SONRAKI ek bilgiyi goster (ornegin "(target=15.0m)").
            extra = _oneline(msg)
            base = f"{frm} -> {to}"
            if extra.startswith(base):
                extra = extra[len(base):].strip()
            a(f"- `+{ts - t0:6.1f}s`  `{frm}` → `{to}`" + (f"  — {extra}" if extra else ""))
        a("")

    if rec["health"]:
        a("## Health geçişleri")
        a("")
        a("| +s | alt sistem | durum |")
        a("|---|---|---|")
        t0 = rec["start_ts"]
        for ts, sub, state in rec["health"]:
            a(f"| `+{ts - t0:.1f}` | `{sub}` | **{state}** |")
        a("")

    if rec["centering"]:
        a("## Merkezleme sonuçları")
        a("")
        a("| +s | sonuç | şekil | irtifa (m) |")
        a("|---|---|---|---|")
        t0 = rec["start_ts"]
        for ts, code, shape, alt in rec["centering"]:
            a(f"| `+{ts - t0:.1f}` | `{code}` | {shape} | {alt} |")
        a("")

    if rec["payload"]:
        a("## Payload olayları")
        a("")
        t0 = rec["start_ts"]
        for ts, shape, idx, msg in rec["payload"]:
            a(f"- `+{ts - t0:6.1f}s`  şekil={shape} index={idx}"
              + (f" — {_oneline(msg)}" if msg else ""))
        a("")

    a("## WARN ve üzeri olaylar")
    a("")
    a("*Severity'ye göre süzülmüş tek bir liste. Bazı satırlar yukarıdaki*")
    a("*tablolarda da görünür (aynı olayın farklı görünümü, ek olay değil).*")
    a("")
    if rec["notable"]:
        t0 = rec["start_ts"]
        for ts, sev, code, sub, msg in rec["notable"]:
            stamp = f"`+{ts - t0:.1f}s` " if ts and t0 else ""
            a(f"- {stamp}**{sev}** `{code}` ({sub}): {_oneline(msg)}")
    else:
        a("Yok — bu koşuda WARN/CRITICAL/FATAL seviyesinde olay kaydedilmedi.")
    a("")

    if rec["shapes"]:
        a("## Tespit edilen şekiller (kare sayısı)")
        a("")
        for shape, n in rec["shapes"].most_common():
            a(f"- `{shape}`: {n} kare")
        a("")

    a("## Olay sayımları")
    a("")
    a("| kod | adet |")
    a("|---|---|")
    for code, n in rec["codes"].most_common():
        a(f"| `{code}` | {n} |")
    a("")

    if rec["kind"] == "mission_run" and not rec["console_log_matched"]:
        a("## Ham dosya eşleşmesi")
        a("")
        a("Konsol log'u (`mission_<zaman>.log`) bu koşuyla **eşleştirilemedi**. "
          "`.log` zaman damgasıyla, `.jsonl` mission_id ile adlandırıldığı için "
          "eşleme zaman penceresi tahminidir; pencerede aday bulunamadı.")
        a("")
    return "\n".join(L)


def write_record(rec: dict, repo_root: str, history_dir: str) -> str:
    out_dir = os.path.join(history_dir, RUNS_DIRNAME)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{rec['run_id']}.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render(rec, repo_root))
    return out


# =============================================================================
# CLI
# =============================================================================

def latest_jsonl(log_dir: str):
    files = glob.glob(os.path.join(log_dir, "mission_*.jsonl"))
    return max(files, key=os.path.getmtime) if files else None


def unrecorded_jsonls(log_dir: str, history_dir: str, skip=None):
    """Kaydi HENUZ uretilmemis olay kayitlarini dondurur.

    BACKFILL'IN VARLIK SEBEBI (2026-08-25, olculdu): kayit uretimini
    launcher'in son satirina koymak GUVENILIR DEGIL -- launcher'a sinyal
    gonderildiginde (Ctrl-C, kill) script o satira ulasmayabiliyor. Kabuk
    sinyal semantigi tekrarli denemelerde TUTARSIZ davrandi, dolayisiyla
    uzerine guvenilirlik insa edilemez.

    Cozum sinyalden BAGIMSIZ: kayit zaten tamamen diskteki .jsonl'den
    turetiliyor, yani cikis ANINDA uretilmek zorunda degil. Bir sonraki
    kosunun BASINDA eksikler tamamlanir. En kotu durumda kayit gec olusur,
    ASLA kaybolmaz.
    """
    runs = os.path.join(history_dir, RUNS_DIRNAME)
    out = []
    for path in sorted(glob.glob(os.path.join(log_dir, "mission_*.jsonl"))):
        if skip and os.path.realpath(path) == os.path.realpath(skip):
            continue
        mid = os.path.basename(path)[len("mission_"):-len(".jsonl")]
        if not os.path.isfile(os.path.join(runs, f"{mid}.md")):
            out.append(path)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="run_record",
        description="Kosu kaydi uret -- yalnizca olgu, yorum yok.")
    ap.add_argument("--repo-root", default=None, help="proje koku (varsayilan: cwd)")
    ap.add_argument("--log-dir", default=None,
                    help="ham log dizini (varsayilan: <repo>/../logs)")
    ap.add_argument("--history-dir", default=None,
                    help="varsayilan: <repo>/docs/test-history")
    ap.add_argument("--jsonl", default=None, help="belirli bir olay kaydi")
    ap.add_argument("--latest", action="store_true", help="en yeni kosuyu isle")
    ap.add_argument("--backfill", action="store_true",
                    help="kaydi eksik TUM kosulari isle (launcher basinda cagrilir)")
    ap.add_argument("--exit-code", type=int, default=None,
                    help="kosunun cikis kodu (launcher gecer)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    repo = os.path.realpath(args.repo_root or os.getcwd())
    log_dir = args.log_dir or os.path.join(os.path.dirname(repo), "logs")
    history = args.history_dir or os.path.join(repo, "docs", "test-history")

    if args.backfill:
        missing = unrecorded_jsonls(log_dir, history)
        made = 0
        for path in missing:
            try:
                rec = build_mission_record(path, log_dir, None)
                write_record(rec, repo, history)
                made += 1
            except Exception as e:  # noqa: BLE001 -- tek bozuk kayit digerlerini engellemez
                if not args.quiet:
                    print(f"[RUN_RECORD] atlandi {os.path.basename(path)} "
                          f"({type(e).__name__}: {e})")
        if not args.quiet and made:
            print(f"[RUN_RECORD] backfill: {made} eksik kayit uretildi.")
        return 0

    jsonl = args.jsonl
    if not jsonl and args.latest:
        jsonl = latest_jsonl(log_dir)
    if not jsonl:
        # Kosu kaydi URETILEMEMESI bir HATA DEGIL: mission hic olay
        # yazamadan dusmus olabilir. Launcher'i patlatma.
        if not args.quiet:
            print("[RUN_RECORD] islenecek olay kaydi bulunamadi -- kayit uretilmedi.")
        return 0
    try:
        rec = build_mission_record(jsonl, log_dir, args.exit_code)
        out = write_record(rec, repo, history)
    except Exception as e:  # noqa: BLE001
        if not args.quiet:
            print(f"[RUN_RECORD] kayit uretilemedi ({type(e).__name__}: {e})")
        return 0          # kayit uretimi ASLA kosuyu basarisiz gostermez
    if not args.quiet:
        print(f"[RUN_RECORD] {os.path.relpath(out, repo)} "
              f"({rec['event_count']} olay, terminal={rec['terminal_phase']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
