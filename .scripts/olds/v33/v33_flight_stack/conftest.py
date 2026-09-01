"""Proje koku conftest -- YALNIZCA oturum sonu kosu kaydi kancasi.

Neden burada: `pytest_sessionfinish` bir OTURUM kancasidir. tests/conftest.py
yalnizca tests/ altindaki toplama sirasinda yuklendigi icin, `pytest
tools/tests/` gibi kismi kosularda tetiklenmezdi. Kok conftest her zaman
yuklenir.

Bu dosya sys.path'e DOKUNMAZ ve fixture TANIMLAMAZ -- mevcut test davranisini
degistirmemesi kasitlidir (referans: 697 passed, 2026-08-25).
"""
import os
import time

_START = {}


def pytest_sessionstart(session):
    _START["t"] = time.time()


def pytest_sessionfinish(session, exitstatus):
    """Kosu kaydi uretir. HICBIR KOSULDA test sonucunu etkilemez."""
    if os.environ.get("KURSAD40_NO_RUN_RECORD"):
        return
    try:
        import sys
        root = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, os.path.join(root, "tools"))
        try:
            import run_record
        finally:
            sys.path.pop(0)

        tr = session.config.pluginmanager.get_plugin("terminalreporter")
        stats = getattr(tr, "stats", {}) or {}
        counts = {k: len(v) for k, v in stats.items()
                  if k in ("passed", "failed", "error", "skipped",
                           "xfailed", "xpassed")}
        failures = []
        for key in ("failed", "error"):
            for rep in stats.get(key, []):
                nodeid = getattr(rep, "nodeid", "?")
                msg = getattr(rep, "longreprtext", "") or str(getattr(rep, "longrepr", ""))
                failures.append((nodeid, msg))

        started = _START.get("t", time.time())
        run_id = "pytest_" + time.strftime("%Y%m%d_%H%M%S", time.localtime(started))
        rec = run_record.build_pytest_record(
            run_id=run_id, exit_status=int(exitstatus),
            duration_s=time.time() - started, counts=counts, failures=failures,
            start_ts=started)
        out = run_record.write_record(rec, root,
                                      os.path.join(root, "docs", "test-history"))
        print(f"\n[RUN_RECORD] {os.path.relpath(out, root)}")
    except Exception as e:  # noqa: BLE001 -- kayit uretimi testleri ASLA dusurmez
        print(f"\n[RUN_RECORD] kayit uretilemedi ({type(e).__name__}: {e})")
