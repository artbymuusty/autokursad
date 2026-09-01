"""tools/artifact_retention.py testleri.

ODAK: aracin ne YAPTIGI degil, ne YAPMADIGI. Bu bir SILME aracidir; degerli
testler "su kosulda silmez" diyenlerdir.

Script'i importlib ile yukluyoruz -- tools/ bir paket degil ve oyle olmasi
icin bir sebep yok (tools/tests/test_calibrate_real_servos.py ile ayni desen).
"""
import importlib.util
import io
import json
import os
import sys
import tarfile
import time

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(os.path.dirname(_HERE), "artifact_retention.py")

_spec = importlib.util.spec_from_file_location("artifact_retention", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
# sys.modules'a ONCE kaydet: @dataclass, string annotation'lari cozmek icin
# sys.modules[cls.__module__] arar; kayitsiz modulde bu None doner ve
# dataclass olusturma AttributeError ile patlar.
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)


# --- yardimcilar -------------------------------------------------------------

GOOD_META = {
    "phase_id": "PH-TEST",
    "date": "2026-08-25",
    "raw_artifacts": ["logs/*.log"],
}


def _summary_text(meta=None, skip=(), blank=(), extra_body=""):
    meta = dict(GOOD_META if meta is None else meta)
    lines = ["---"]
    for k, v in meta.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            lines += [f"  - \"{item}\"" for item in v]
        else:
            lines.append(f"{k}: {v}")
    lines += ["---", "", "# Baslik", ""]
    for name in mod.REQUIRED_SECTIONS:
        if name in skip:
            continue
        lines.append(f"## {name}")
        lines.append("" if name in blank else
                     f"{name} icin yeterince uzun gercek bir icerik metni.")
        lines.append("")
    lines.append(extra_body)
    return "\n".join(lines)


def _repo(tmp_path, artifacts=None, cfg_extra=None, summary=None):
    """Gecici bir sahte proje kokup dondurur."""
    hist = tmp_path / "docs" / "test-history"
    hist.mkdir(parents=True)
    logs = tmp_path / "logs"
    logs.mkdir()
    for name, size, age_days in (artifacts or []):
        f = logs / name
        f.write_bytes(b"x" * size)
        t = time.time() - age_days * 86400
        os.utime(f, (t, t))
    cfg = {
        "roots": [{"path": "logs", "kind": "project", "patterns": ["*.log"]}],
        "history_dir": "docs/test-history",
        "archive_dir": "docs/test-history/_archive",
        "warning_bytes": "1KB",
        "critical_bytes": "2KB",
        "recent_keep_days": 1,
        "recent_keep_runs": 0,
        "active_grace_seconds": 60,
        "min_artifact_bytes": 0,
    }
    cfg.update(cfg_extra or {})
    cfg_path = hist / mod.DEFAULT_CONFIG_NAME
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    if summary is not None:
        (hist / "PH-TEST-x.md").write_text(summary, encoding="utf-8")
    return str(tmp_path), str(cfg_path), str(hist), str(logs)


class _Args:
    def __init__(self, repo_root, config, now=None, yes=False, dry_run=False):
        self.repo_root = repo_root
        self.config = config
        self.now = now
        self.yes = yes
        self.dry_run = dry_run


def _no_lsof(monkeypatch, busy=()):
    monkeypatch.setattr(mod, "open_paths", lambda: set(busy))


# =============================================================================
# Konfigurasyon
# =============================================================================

@pytest.mark.parametrize("text,expected", [
    (10, 10), ("10GB", 10 * mod.GB), ("10 GB", 10 * mod.GB),
    ("512MB", 512 * 1024 ** 2), ("64KB", 65536), ("1TB", 1024 ** 4),
])
def test_size_parsing(text, expected):
    assert mod._coerce_bytes(text) == expected


def test_esikler_sabit_kodlanmamis(tmp_path):
    repo, cfg_path, _, _ = _repo(tmp_path, cfg_extra={
        "warning_bytes": "7GB", "critical_bytes": "9GB"})
    cfg = mod.load_config(cfg_path, repo)
    assert cfg.warning_bytes == 7 * mod.GB
    assert cfg.critical_bytes == 9 * mod.GB


def test_warning_criticalden_buyuk_olamaz(tmp_path):
    repo, cfg_path, _, _ = _repo(tmp_path, cfg_extra={
        "warning_bytes": "9GB", "critical_bytes": "7GB"})
    with pytest.raises(ValueError):
        mod.load_config(cfg_path, repo)


def test_config_yoksa_varsayilanlar_kullanilir(tmp_path):
    cfg = mod.load_config(str(tmp_path / "yok.json"), str(tmp_path))
    assert cfg.warning_bytes == 10 * mod.GB
    assert cfg.critical_bytes == 15 * mod.GB


@pytest.mark.parametrize("total,level", [
    (0, mod.OK), (9 * mod.GB, mod.OK), (10 * mod.GB, mod.WARNING),
    (14 * mod.GB, mod.WARNING), (15 * mod.GB, mod.CRITICAL),
    (40 * mod.GB, mod.CRITICAL),
])
def test_esik_seviyeleri(total, level):
    cfg = mod.Config()
    assert mod.threshold_level(total, cfg) == level


# =============================================================================
# Ozet dogrulama -- 4. guvenlik sarti
# =============================================================================

def test_tam_ozet_gecerli(tmp_path):
    p = tmp_path / "s.md"
    p.write_text(_summary_text(), encoding="utf-8")
    assert mod.parse_summary(str(p)).is_valid


@pytest.mark.parametrize("missing", list(mod.REQUIRED_SECTIONS))
def test_eksik_bolum_ozeti_gecersiz_kilar(tmp_path, missing):
    p = tmp_path / "s.md"
    p.write_text(_summary_text(skip=(missing,)), encoding="utf-8")
    s = mod.parse_summary(str(p))
    assert not s.is_valid
    assert any(missing in prob for prob in s.problems)


@pytest.mark.parametrize("key", list(mod.REQUIRED_META))
def test_eksik_frontmatter_ozeti_gecersiz_kilar(tmp_path, key):
    meta = dict(GOOD_META)
    del meta[key]
    p = tmp_path / "s.md"
    p.write_text(_summary_text(meta=meta), encoding="utf-8")
    assert not mod.parse_summary(str(p)).is_valid


def test_bos_bolum_ozeti_gecersiz_kilar(tmp_path):
    p = tmp_path / "s.md"
    p.write_text(_summary_text(blank=("Kök neden",)), encoding="utf-8")
    assert not mod.parse_summary(str(p)).is_valid


@pytest.mark.parametrize("filler", ["TODO", "TBD", "-", "...", "xxx"])
def test_yer_tutucu_dolgu_kabul_edilmez(tmp_path, filler):
    text = _summary_text().replace(
        "Kök neden icin yeterince uzun gercek bir icerik metni.", filler)
    p = tmp_path / "s.md"
    p.write_text(text, encoding="utf-8")
    assert not mod.parse_summary(str(p)).is_valid


def test_yok_bilincli_beyan_olarak_kabul_edilir(tmp_path):
    text = _summary_text().replace(
        "Başarısızlıklar icin yeterince uzun gercek bir icerik metni.", "Yok.")
    p = tmp_path / "s.md"
    p.write_text(text, encoding="utf-8")
    assert mod.parse_summary(str(p)).is_valid


def test_bozuk_frontmatter_ozeti_gecersiz_kilar(tmp_path):
    p = tmp_path / "s.md"
    p.write_text("---\nphase_id: [bozuk\n---\n\n## Amaç\nbir seyler\n",
                 encoding="utf-8")
    assert not mod.parse_summary(str(p)).is_valid


def test_index_sablon_ve_denetim_ozet_sayilmaz(tmp_path):
    hist = tmp_path / "h"
    hist.mkdir()
    for name in ("README.md", "TEMPLATE.md", "cleanup-history.md"):
        (hist / name).write_text("# x\n", encoding="utf-8")
    assert mod.load_summaries(str(hist)) == []


# =============================================================================
# Siniflandirma -- 1., 2., 3., 6. guvenlik sartlari
# =============================================================================

def test_acik_dosya_ACTIVE_kalir(tmp_path, monkeypatch):
    repo, cfg_path, hist, logs = _repo(
        tmp_path, [("a.log", 100, 30)], summary=_summary_text())
    target = os.path.realpath(os.path.join(logs, "a.log"))
    _no_lsof(monkeypatch, busy={target})
    _, _, _, arts, _, _, _, _, _ = mod._gather(_Args(repo, cfg_path))
    assert arts[0].state == mod.ACTIVE


def test_yeni_degismis_dosya_ACTIVE_kalir(tmp_path, monkeypatch):
    # 30 gun eski ama grace 100 gun -> hala yaziliyor olabilir
    repo, cfg_path, _, _ = _repo(
        tmp_path, [("a.log", 100, 30)], summary=_summary_text(),
        cfg_extra={"active_grace_seconds": 100 * 86400})
    _no_lsof(monkeypatch)
    _, _, _, arts, _, _, _, _, _ = mod._gather(_Args(repo, cfg_path))
    assert arts[0].state == mod.ACTIVE


def test_ozetsiz_dosya_COMPLETED_kalir(tmp_path, monkeypatch):
    repo, cfg_path, _, _ = _repo(tmp_path, [("a.log", 100, 30)])
    _no_lsof(monkeypatch)
    _, _, _, arts, _, _, _, _, _ = mod._gather(_Args(repo, cfg_path))
    assert arts[0].state == mod.COMPLETED
    assert arts[0].summary is None


def test_gecersiz_ozet_ARCHIVABLE_URETMEZ(tmp_path, monkeypatch):
    """4. sart: ozet dogrulanmadan artifact silinemez."""
    repo, cfg_path, _, _ = _repo(
        tmp_path, [("a.log", 100, 30)],
        summary=_summary_text(blank=("Doğrulama",)))
    _no_lsof(monkeypatch)
    _, _, _, arts, _, _, _, _, _ = mod._gather(_Args(repo, cfg_path))
    assert arts[0].state == mod.SUMMARIZED
    assert arts[0].state != mod.ARCHIVABLE
    assert "GECMEDI" in arts[0].reason


def test_gecerli_ozet_eski_dosya_ARCHIVABLE(tmp_path, monkeypatch):
    repo, cfg_path, _, _ = _repo(
        tmp_path, [("a.log", 100, 30)], summary=_summary_text())
    _no_lsof(monkeypatch)
    _, _, _, arts, _, _, _, _, _ = mod._gather(_Args(repo, cfg_path))
    assert arts[0].state == mod.ARCHIVABLE
    assert arts[0].summary.endswith("PH-TEST-x.md")


def test_recent_retention_gun_penceresi_korur(tmp_path, monkeypatch):
    # 1 gun eski: active_grace'i (60s) asiyor ama 3 gunluk pencerenin icinde.
    # 0 gun verilseydi dosya hakli olarak ACTIVE sayilirdi.
    repo, cfg_path, _, _ = _repo(
        tmp_path, [("a.log", 100, 1)], summary=_summary_text(),
        cfg_extra={"recent_keep_days": 3})
    _no_lsof(monkeypatch)
    _, _, _, arts, _, _, _, _, _ = mod._gather(_Args(repo, cfg_path))
    assert arts[0].state == mod.VERIFIED
    assert "recent-retention" in arts[0].reason


def test_recent_retention_kosu_sayisi_korur(tmp_path, monkeypatch):
    """En yeni N kosu, gun penceresi disinda olsa bile korunur."""
    repo, cfg_path, _, _ = _repo(
        tmp_path, [("eski.log", 100, 40), ("yeni.log", 100, 30)],
        summary=_summary_text(), cfg_extra={"recent_keep_runs": 1})
    _no_lsof(monkeypatch)
    _, _, _, arts, _, _, _, _, _ = mod._gather(_Args(repo, cfg_path))
    by = {os.path.basename(a.path): a for a in arts}
    assert by["yeni.log"].state == mod.VERIFIED      # korundu
    assert by["eski.log"].state == mod.ARCHIVABLE    # pencere disi


# =============================================================================
# FAIL-CLOSED ve plan
# =============================================================================

def test_lsof_yoksa_HICBIR_SEY_islenmez(tmp_path, monkeypatch):
    repo, cfg_path, _, _ = _repo(
        tmp_path, [("a.log", 5000, 30)], summary=_summary_text())

    def boom():
        raise ValueError("lsof yok")
    monkeypatch.setattr(mod, "open_paths", boom)

    _, cfg, _, arts, total, level, _, busy_known, _ = mod._gather(_Args(repo, cfg_path))
    assert busy_known is False
    plan = mod.build_plan(arts, cfg, busy_known, level, total)
    assert plan.artifacts == []
    assert plan.reclaimable == 0
    assert any("FAIL-CLOSED" in n for n in plan.notes)


def test_esik_altinda_otomatik_islem_yok(tmp_path, monkeypatch):
    repo, cfg_path, _, _ = _repo(
        tmp_path, [("a.log", 100, 30)], summary=_summary_text(),
        cfg_extra={"warning_bytes": "1GB", "critical_bytes": "2GB"})
    _no_lsof(monkeypatch)
    _, cfg, _, arts, total, level, _, bk, _ = mod._gather(_Args(repo, cfg_path))
    assert level == mod.OK
    plan = mod.build_plan(arts, cfg, bk, level, total)
    assert plan.artifacts == []           # aday var ama otomatik islem yok
    assert plan.blocked


def test_CRITICAL_guvenlik_sartlarini_gevsetmez(tmp_path, monkeypatch):
    """Esigi asmak, ozeti olmayan veriyi silmenin gerekcesi degildir."""
    repo, cfg_path, _, _ = _repo(tmp_path, [("a.log", 9000, 30)])  # ozet YOK
    _no_lsof(monkeypatch)
    _, cfg, _, arts, total, level, _, bk, _ = mod._gather(_Args(repo, cfg_path))
    assert level == mod.CRITICAL
    plan = mod.build_plan(arts, cfg, bk, level, total)
    assert plan.artifacts == []
    assert any("guvenlik sartlarini gecen artifact YOK" in n for n in plan.notes)


# =============================================================================
# Yurutme: arsivle -> DOGRULA -> sil
# =============================================================================

def _archivable(tmp_path, monkeypatch, names_sizes):
    repo, cfg_path, hist, logs = _repo(
        tmp_path, [(n, s, 30) for n, s in names_sizes],
        summary=_summary_text())
    _no_lsof(monkeypatch)
    _, cfg, _, arts, total, level, _, bk, _ = mod._gather(_Args(repo, cfg_path))
    plan = mod.build_plan(arts, cfg, bk, level, total)
    return repo, cfg, hist, logs, plan


def test_arsivleme_ham_veriyi_kaldirir_ama_once_arsiv_dogrulanir(tmp_path, monkeypatch):
    repo, cfg, hist, logs, plan = _archivable(tmp_path, monkeypatch, [("a.log", 5000)])
    assert len(plan.to_archive) == 1
    res = mod.apply_plan(plan, cfg, repo, dry_run=False)
    assert res.error is None
    assert not os.path.exists(os.path.join(logs, "a.log"))     # ham veri gitti
    dest = res.archived[0][1]
    assert os.path.exists(dest)
    with tarfile.open(dest, "r:gz") as tf:                      # arsiv okunabilir
        assert tf.getmember("a.log").size == 5000


def test_arsiv_dogrulamasi_basarisizsa_HAM_VERI_KORUNUR(tmp_path, monkeypatch):
    repo, cfg, hist, logs, plan = _archivable(tmp_path, monkeypatch, [("a.log", 5000)])
    real_open = tarfile.open

    def sabotaj(name, mode="r", *a, **k):
        if mode.startswith("r"):
            raise OSError("arsiv okunamadi")
        return real_open(name, mode, *a, **k)
    monkeypatch.setattr(mod.tarfile, "open", sabotaj)

    res = mod.apply_plan(plan, cfg, repo, dry_run=False)
    assert res.error is not None
    assert os.path.exists(os.path.join(logs, "a.log"))          # HAM VERI DURUYOR
    arch = os.path.join(repo, "docs", "test-history", "_archive")
    assert not os.path.isdir(arch) or not os.listdir(arch)      # bozuk arsiv de silindi


def test_dry_run_diske_dokunmaz(tmp_path, monkeypatch):
    repo, cfg, hist, logs, plan = _archivable(tmp_path, monkeypatch, [("a.log", 5000)])
    res = mod.apply_plan(plan, cfg, repo, dry_run=True)
    assert res.error is None
    assert os.path.exists(os.path.join(logs, "a.log"))
    assert not os.path.isdir(os.path.join(repo, "docs", "test-history", "_archive"))
    assert res.freed == 5000                                    # raporlar ama yapmaz


def test_kismi_hata_ANINDA_durur_ve_kalani_SILMEZ(tmp_path, monkeypatch):
    repo, cfg, hist, logs, plan = _archivable(
        tmp_path, monkeypatch, [("a.log", 5000), ("b.log", 4000), ("c.log", 3000)])
    assert len(plan.to_archive) == 3
    calls = {"n": 0}
    real = mod._archive_one

    def patlat(a, archive_dir, repo_root):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk doldu")
        return real(a, archive_dir, repo_root)
    monkeypatch.setattr(mod, "_archive_one", patlat)

    res = mod.apply_plan(plan, cfg, repo, dry_run=False)
    assert res.error is not None and "disk doldu" in res.error
    assert len(res.archived) == 1                    # yalnizca ilki islendi
    assert len(res.unprocessed) == 2                 # duran + kalan
    kalan = [os.path.basename(p) for p in res.unprocessed]
    for name in kalan:
        assert os.path.exists(os.path.join(logs, name))   # HICBIRI SILINMEDI


def test_hicbir_artifact_yoksa_apply_hata_vermez(tmp_path, monkeypatch):
    repo, cfg_path, _, _ = _repo(tmp_path, [("a.log", 100, 30)])   # ozet yok
    _no_lsof(monkeypatch)
    out = io.StringIO()
    rc = mod.cmd_apply(_Args(repo, cfg_path, yes=True), out=out)
    assert rc == 0
    assert "Islenecek artifact yok" in out.getvalue()


def test_yes_verilmezse_hicbir_sey_yapilmaz(tmp_path, monkeypatch):
    repo, cfg_path, _, logs = _repo(
        tmp_path, [("a.log", 5000, 30)], summary=_summary_text())
    _no_lsof(monkeypatch)
    out = io.StringIO()
    rc = mod.cmd_apply(_Args(repo, cfg_path, yes=False), out=out)
    assert rc == 0
    assert "--yes verilmedi" in out.getvalue()
    assert os.path.exists(os.path.join(logs, "a.log"))


# =============================================================================
# Denetim kaydi
# =============================================================================

def test_denetim_kaydi_zorunlu_alanlari_icerir(tmp_path, monkeypatch):
    repo, cfg_path, hist, _ = _repo(
        tmp_path, [("a.log", 5000, 30)], summary=_summary_text())
    _no_lsof(monkeypatch)
    mod.cmd_apply(_Args(repo, cfg_path, yes=True), out=io.StringIO())
    text = (tmp_path / "docs" / "test-history" / "cleanup-history.md").read_text()
    for beklenen in ("Eşik durumu", "Önceki boyut", "Sonraki boyut",
                     "Kazanılan alan", "İşlenen artifact", "Arşivlenen",
                     "Silinen", "Dokunulmayan", "temsil eden özet"):
        assert beklenen in text, f"denetim kaydinda yok: {beklenen}"


def test_denetim_kaydi_kismi_hatayi_yazar(tmp_path, monkeypatch):
    repo, cfg, hist, logs, plan = _archivable(
        tmp_path, monkeypatch, [("a.log", 5000), ("b.log", 4000)])
    monkeypatch.setattr(mod, "_archive_one",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("bozuk")))
    res = mod.apply_plan(plan, cfg, repo, dry_run=False)
    entry = mod.append_audit(os.path.join(hist, "cleanup-history.md"),
                             cfg, plan, res, plan.total_before, False, mod._utcnow())
    assert "KISMİ BAŞARISIZLIK" in entry
    assert "İşlenmeyen" in entry
    assert "bozuk" in entry


def test_denetim_kaydi_eklenir_uzerine_yazilmaz(tmp_path, monkeypatch):
    repo, cfg_path, hist, _ = _repo(
        tmp_path, [("a.log", 5000, 30)], summary=_summary_text())
    _no_lsof(monkeypatch)
    audit = os.path.join(hist, "cleanup-history.md")
    cfg = mod.load_config(cfg_path, repo)
    plan = mod.Plan(level=mod.OK, total_before=0)
    for _ in range(3):
        mod.append_audit(audit, cfg, plan, mod.ApplyResult(), 0, True, mod._utcnow())
    assert open(audit, encoding="utf-8").read().count("## ") >= 3


# =============================================================================
# Gecici alan != proje hafizasi
# =============================================================================

def test_ephemeral_kok_ozet_barindiramaz(tmp_path, monkeypatch):
    """Ozetler YALNIZCA history_dir'den okunur; ephemeral kokten asla."""
    repo, cfg_path, hist, logs = _repo(tmp_path, [("a.log", 100, 30)])
    sahte = tmp_path / "logs" / "PH-SAHTE.md"
    sahte.write_text(_summary_text(), encoding="utf-8")
    _no_lsof(monkeypatch)
    _, _, _, arts, _, _, summaries, _, _ = mod._gather(_Args(repo, cfg_path))
    assert all(not s.path.startswith(str(tmp_path / "logs")) for s in summaries)
    assert arts[0].state == mod.COMPLETED       # sahte ozet islem gormedi


def test_ephemeral_bayragi_kokten_gelir(tmp_path):
    r = mod.Root(path="/tmp/x", kind="ephemeral")
    assert r.is_ephemeral
    assert not mod.Root(path="logs").is_ephemeral
