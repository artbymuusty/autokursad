"""tools/run_record.py testleri.

EN ONEMLI SOZLESME: kosu kaydi YALNIZCA olgu icerir. Insan yargisi gerektiren
sekiz alani (phase_id, Amac, Degisiklikler, Kok neden, Uygulanan cozum,
Dogrulama, Ilgili commit, Sonraki adim) BOS BASLIK OLARAK BILE tasimaz --
yanlis doldurulma yuzeyi hic olusmasin diye.

Ikinci sozlesme: bir kosu kaydi ASLA dogrulanmis ozet sayilamaz, dolayisiyla
hicbir ham veriyi silinebilir yapamaz.
"""
import importlib.util
import json
import os
import sys
import time

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.dirname(_HERE)
_REPO = os.path.dirname(_TOOLS)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load("run_record_under_test", os.path.join(_TOOLS, "run_record.py"))
retention = _load("artifact_retention_for_rr",
                  os.path.join(_TOOLS, "artifact_retention.py"))

# TEMPLATE.md'nin INSAN alanlari -- kosu kaydinda GORUNMEMELI
FORBIDDEN_SECTIONS = ("Amaç", "Değişiklikler", "Kök neden", "Uygulanan çözüm",
                      "Doğrulama", "Sonraki adım", "İlgili commit")
FORBIDDEN_META = ("phase_id:", "commit:")

T0 = 1_700_000_000.0


def _ev(code, ts_off, **kw):
    e = {"code": code, "subsystem": kw.pop("subsystem", "X"),
         "message": kw.pop("message", ""), "severity": kw.pop("severity", "DEBUG"),
         "mission_id": kw.pop("mission_id", "abc123"), "ts": T0 + ts_off,
         "data": kw.pop("data", {})}
    e.update(kw)
    return e


def _write_jsonl(tmp_path, events, mission_id="abc123"):
    log_dir = tmp_path / "logs"
    log_dir.mkdir(exist_ok=True)
    p = log_dir / f"mission_{mission_id}.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")
    return str(p), str(log_dir)


DEFAULT_EVENTS = [
    _ev("MISSION_STARTED", 0.0, message="mission_id=abc123"),
    _ev("MISSION_PHASE_CHANGED", 1.0, message="MISSION_INIT -> CONNECTING",
        data={"from_phase": "MISSION_INIT", "to_phase": "CONNECTING"}),
    _ev("MISSION_PHASE_CHANGED", 2.0,
        message="CONNECTING -> TAKEOFF (target=15.0m)",
        data={"from_phase": "CONNECTING", "to_phase": "TAKEOFF"}),
    _ev("HEALTH_STATE_CHANGED", 3.0, subsystem="Gorev2Orchestrator.vision",
        data={"state": "HEALTHY"}),
    _ev("VISION_FRAME_PROCESSED", 3.5, data={"shapes": ["MAVI_ALTIGEN"]}),
    _ev("CENTERING_CONVERGED", 4.0, data={"shape_type": "MAVI_ALTIGEN",
                                          "altitude_m": 3.0}),
    _ev("SOMETHING_BAD", 5.0, severity="CRITICAL",
        message="line one\nline two\n\tline three"),
]


# =============================================================================
# ASIL SOZLESME: yorum alani YOK
# =============================================================================

def test_kayit_INSAN_alanlarini_ICERMEZ(tmp_path):
    jsonl, log_dir = _write_jsonl(tmp_path, DEFAULT_EVENTS)
    rec = mod.build_mission_record(jsonl, log_dir, exit_code=0)
    text = mod.render(rec, str(tmp_path))
    for name in FORBIDDEN_SECTIONS:
        assert f"## {name}" not in text, f"yasak bolum uretildi: {name}"
    for key in FORBIDDEN_META:
        assert not any(l.startswith(key) for l in text.splitlines()), \
            f"yasak frontmatter anahtari: {key}"


def test_kayit_makine_uretimi_oldugunu_BEYAN_EDER(tmp_path):
    jsonl, log_dir = _write_jsonl(tmp_path, DEFAULT_EVENTS)
    text = mod.render(mod.build_mission_record(jsonl, log_dir), str(tmp_path))
    assert "machine_generated: true" in text
    assert "generator: tools/run_record.py" in text
    assert "doğrulanmış bir özet **değildir**" in text


def test_pytest_kaydi_da_insan_alani_ICERMEZ():
    rec = mod.build_pytest_record("pytest_x", 1, 3.2,
                                  {"passed": 5, "failed": 2},
                                  [("t.py::a", "assert 1 == 2")], start_ts=T0)
    text = mod.render(rec, "/tmp")
    for name in FORBIDDEN_SECTIONS:
        assert f"## {name}" not in text
    assert "t.py::a" in text          # olgu VAR


# =============================================================================
# GUVENLIK: kosu kaydi ozet SAYILAMAZ
# =============================================================================

def test_kosu_kaydi_ASLA_dogrulanmis_ozet_sayilmaz(tmp_path):
    """runs/ alt dizin; load_summaries os.listdir ile yalnizca ust seviyeyi okur."""
    history = tmp_path / "docs" / "test-history"
    history.mkdir(parents=True)
    jsonl, log_dir = _write_jsonl(tmp_path, DEFAULT_EVENTS)
    rec = mod.build_mission_record(jsonl, log_dir)
    out = mod.write_record(rec, str(tmp_path), str(history))

    assert os.path.dirname(out).endswith(os.path.join("docs", "test-history", "runs"))
    summaries = retention.load_summaries(str(history))
    assert summaries == [], "kosu kaydi ozet listesine SIZDI"


def test_kosu_kaydi_ham_veriyi_ARCHIVABLE_yapmaz(tmp_path):
    """Uctan uca: kayit varken bile artifact ozetsiz sayilmali."""
    history = tmp_path / "docs" / "test-history"
    history.mkdir(parents=True)
    jsonl, log_dir = _write_jsonl(tmp_path, DEFAULT_EVENTS)
    old = time.time() - 40 * 86400
    os.utime(jsonl, (old, old))
    mod.write_record(mod.build_mission_record(jsonl, log_dir),
                     str(tmp_path), str(history))

    cfg = retention.Config(
        roots=(retention.Root(path=str(log_dir), kind="project",
                              patterns=("*.jsonl",)),),
        history_dir=str(history), recent_keep_days=0, recent_keep_runs=0,
        active_grace_seconds=1)
    arts = retention.discover(cfg, str(tmp_path))
    cov = retention.build_coverage(retention.load_summaries(str(history)), str(tmp_path))
    retention.classify(arts, cov, cfg, busy=set(), now=time.time())
    assert arts and all(a.state == retention.COMPLETED for a in arts)
    assert all(a.summary is None for a in arts)


# =============================================================================
# Olgu cikarimi
# =============================================================================

def test_faz_zinciri_ve_terminal_faz(tmp_path):
    jsonl, log_dir = _write_jsonl(tmp_path, DEFAULT_EVENTS)
    rec = mod.build_mission_record(jsonl, log_dir)
    assert rec["terminal_phase"] == "TAKEOFF"
    assert [p[1] for p in rec["phases"]] == ["MISSION_INIT", "CONNECTING"]


def test_health_ve_kritik_olaylar_yakalanir(tmp_path):
    jsonl, log_dir = _write_jsonl(tmp_path, DEFAULT_EVENTS)
    rec = mod.build_mission_record(jsonl, log_dir)
    assert ("Gorev2Orchestrator.vision", "HEALTHY") == (rec["health"][0][1],
                                                        rec["health"][0][2])
    assert len(rec["notable"]) == 1
    assert rec["notable"][0][1] == "CRITICAL"


def test_cok_satirli_mesaj_tek_satira_indirilir(tmp_path):
    jsonl, log_dir = _write_jsonl(tmp_path, DEFAULT_EVENTS)
    text = mod.render(mod.build_mission_record(jsonl, log_dir), str(tmp_path))
    bad = [l for l in text.splitlines() if l.startswith("- ") and "SOMETHING_BAD" in l]
    assert len(bad) == 1
    assert "line one line two line three" in bad[0]


def test_faz_mesajindaki_tekrar_atilir_ek_bilgi_KALIR(tmp_path):
    jsonl, log_dir = _write_jsonl(tmp_path, DEFAULT_EVENTS)
    text = mod.render(mod.build_mission_record(jsonl, log_dir), str(tmp_path))
    assert "`CONNECTING` → `TAKEOFF`  — (target=15.0m)" in text
    assert "— MISSION_INIT -> CONNECTING" not in text   # tekrar yok


def test_tespit_edilen_sekiller_sayilir(tmp_path):
    jsonl, log_dir = _write_jsonl(tmp_path, DEFAULT_EVENTS)
    rec = mod.build_mission_record(jsonl, log_dir)
    assert rec["shapes"]["MAVI_ALTIGEN"] == 1


def test_exit_code_kaydedilir(tmp_path):
    jsonl, log_dir = _write_jsonl(tmp_path, DEFAULT_EVENTS)
    text = mod.render(mod.build_mission_record(jsonl, log_dir, exit_code=143),
                      str(tmp_path))
    assert "exit_code: 143" in text


def test_bozuk_satirlar_SESSIZCE_atlanmaz(tmp_path):
    log_dir = tmp_path / "logs"; log_dir.mkdir()
    p = log_dir / "mission_abc123.jsonl"
    p.write_text(json.dumps(DEFAULT_EVENTS[0]) + "\n{bozuk\n", encoding="utf-8")
    rec = mod.build_mission_record(str(p), str(log_dir))
    assert rec["broken_lines"] == 1
    assert "broken_lines: 1" in mod.render(rec, str(tmp_path))


# =============================================================================
# Konsol log eslesmesi (heuristik, durustce isaretlenir)
# =============================================================================

def _touch_console(log_dir, stamp):
    p = os.path.join(log_dir, f"mission_{stamp}.log")
    open(p, "w").close()
    return p


def test_pencere_icindeki_konsol_logu_eslesir(tmp_path):
    jsonl, log_dir = _write_jsonl(tmp_path, DEFAULT_EVENTS)
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(T0 + 0.5))
    _touch_console(log_dir, stamp)
    rec = mod.build_mission_record(jsonl, log_dir)
    assert rec["console_log_matched"] is True


def test_pencere_disindaki_konsol_logu_ESLESMEZ_ve_belirtilir(tmp_path):
    jsonl, log_dir = _write_jsonl(tmp_path, DEFAULT_EVENTS)
    _touch_console(log_dir, time.strftime("%Y%m%d_%H%M%S",
                                          time.localtime(T0 - 10_000)))
    rec = mod.build_mission_record(jsonl, log_dir)
    assert rec["console_log_matched"] is False
    assert "eşleştirilemedi" in mod.render(rec, str(tmp_path))


# =============================================================================
# Hata izolasyonu: kayit uretimi kosuyu ASLA dusurmez
# =============================================================================

def test_olay_kaydi_yoksa_hata_vermez(tmp_path, capsys):
    rc = mod.main(["--repo-root", str(tmp_path), "--log-dir", str(tmp_path),
                   "--latest"])
    assert rc == 0
    assert "bulunamadi" in capsys.readouterr().out


def test_bos_olay_kaydi_kosuyu_dusurmez(tmp_path, capsys):
    log_dir = tmp_path / "logs"; log_dir.mkdir()
    (log_dir / "mission_x.jsonl").write_text("", encoding="utf-8")
    rc = mod.main(["--repo-root", str(tmp_path), "--log-dir", str(log_dir),
                   "--history-dir", str(tmp_path / "h"), "--latest"])
    assert rc == 0
    assert "uretilemedi" in capsys.readouterr().out


def test_yazilamayan_hedef_kosuyu_dusurmez(tmp_path, monkeypatch, capsys):
    jsonl, log_dir = _write_jsonl(tmp_path, DEFAULT_EVENTS)
    monkeypatch.setattr(mod, "write_record",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk dolu")))
    rc = mod.main(["--repo-root", str(tmp_path), "--log-dir", str(log_dir),
                   "--jsonl", jsonl])
    assert rc == 0
    assert "disk dolu" in capsys.readouterr().out


# =============================================================================
# BACKFILL: kayit gec olusabilir, ASLA kaybolmaz
# =============================================================================

def _repo_with_runs(tmp_path, ids):
    history = tmp_path / "docs" / "test-history"
    (history / mod.RUNS_DIRNAME).mkdir(parents=True)
    log_dir = tmp_path / "logs"
    log_dir.mkdir(exist_ok=True)
    for mid in ids:
        _write_jsonl(tmp_path, DEFAULT_EVENTS, mission_id=mid)
    return str(history), str(log_dir)


def test_backfill_eksik_kayitlari_uretir(tmp_path, capsys):
    history, log_dir = _repo_with_runs(tmp_path, ["aaa", "bbb", "ccc"])
    rc = mod.main(["--repo-root", str(tmp_path), "--log-dir", log_dir,
                   "--history-dir", history, "--backfill"])
    assert rc == 0
    made = sorted(os.listdir(os.path.join(history, mod.RUNS_DIRNAME)))
    assert made == ["aaa.md", "bbb.md", "ccc.md"]
    assert "3 eksik kayit" in capsys.readouterr().out


def test_backfill_IDEMPOTENT(tmp_path, capsys):
    history, log_dir = _repo_with_runs(tmp_path, ["aaa"])
    mod.main(["--repo-root", str(tmp_path), "--log-dir", log_dir,
              "--history-dir", history, "--backfill"])
    stamp = os.path.getmtime(os.path.join(history, mod.RUNS_DIRNAME, "aaa.md"))
    capsys.readouterr()
    mod.main(["--repo-root", str(tmp_path), "--log-dir", log_dir,
              "--history-dir", history, "--backfill"])
    assert os.path.getmtime(os.path.join(history, mod.RUNS_DIRNAME, "aaa.md")) == stamp
    assert "eksik kayit" not in capsys.readouterr().out


def test_backfill_bozuk_kaydi_atlar_DIGERLERINI_URETIR(tmp_path, capsys):
    """Tek bozuk olay kaydi butun backfill'i dusurmemeli."""
    history, log_dir = _repo_with_runs(tmp_path, ["iyi1", "iyi2"])
    (tmp_path / "logs" / "mission_bozuk.jsonl").write_text("", encoding="utf-8")
    rc = mod.main(["--repo-root", str(tmp_path), "--log-dir", log_dir,
                   "--history-dir", history, "--backfill"])
    assert rc == 0
    made = sorted(os.listdir(os.path.join(history, mod.RUNS_DIRNAME)))
    assert made == ["iyi1.md", "iyi2.md"]
    assert "atlandi" in capsys.readouterr().out


def test_unrecorded_kaydi_olani_DISLAR(tmp_path):
    history, log_dir = _repo_with_runs(tmp_path, ["aaa", "bbb"])
    open(os.path.join(history, mod.RUNS_DIRNAME, "aaa.md"), "w").close()
    missing = mod.unrecorded_jsonls(log_dir, history)
    assert [os.path.basename(p) for p in missing] == ["mission_bbb.jsonl"]


def test_run_id_DOSYA_ADINDAN_gelir_backfill_YAKINSAR(tmp_path, capsys):
    """Olay govdesindeki mission_id dosya adiyla celisse bile backfill biter.

    Iki kaynak ayrisirsa (elle yeniden adlandirilmis .jsonl) eski davranista
    kayit <olay-id>.md diye yazilir, backfill ise <dosya-id>.md arardi --
    bulamaz, HER cagride yeniden uretirdi.
    """
    history, log_dir = _repo_with_runs(tmp_path, [])
    # dosya adi 'zzz', olaylarin icindeki mission_id 'abc123'
    _write_jsonl(tmp_path, DEFAULT_EVENTS, mission_id="zzz")
    mod.main(["--repo-root", str(tmp_path), "--log-dir", log_dir,
              "--history-dir", history, "--backfill"])
    assert os.listdir(os.path.join(history, mod.RUNS_DIRNAME)) == ["zzz.md"]
    capsys.readouterr()
    mod.main(["--repo-root", str(tmp_path), "--log-dir", log_dir,
              "--history-dir", history, "--backfill"])
    assert "eksik kayit" not in capsys.readouterr().out   # yakinsadi
