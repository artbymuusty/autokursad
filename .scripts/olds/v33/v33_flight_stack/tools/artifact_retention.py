#!/usr/bin/env python3
"""Test History & Artifact Retention -- ham test ciktilarinin yasam dongusu.

TEMEL PRENSIP
-------------
    RAW DATA -> ANALYZE -> SUMMARIZE -> VERIFY -> ARCHIVE -> PURGE

Hicbir ham test verisi, kendisinden turetilen ozet DOGRULANMADAN silinemez.
Ham cikti geciciDIR; ondan cikarilan bilgi docs/test-history/ altinda kalici,
kucuk ve okunabilir Markdown olarak yasar.

BU ARAC NEYI YAPAR (VE NEYI YAPMAZ)
-----------------------------------
YAPAR   : artifact'leri kesfeder, yasam dongusu durumunu KANITTAN hesaplar,
          esik kontrolu yapar, arsivleme/silme PLANI uretir, plani --apply ile
          yurutur ve her yurutmeyi denetim kaydina yazar.
YAPMAZ  : ozet YAZMAZ. Bir phase'in ne anlama geldigine karar vermek insan/agent
          isidir. Arac yalnizca "bu artifact'i temsil eden dogrulanmis bir ozet
          VAR MI" sorusunu cevaplar. Bu, tools/calibrate_real_servos.py'nin
          "veri uretir, kalibrasyon karari senin" disipliniyle ayni.

DURUM SAKLANMAZ, TURETILIR
--------------------------
Yasam dongusu durumu icin ayri bir state dosyasi TUTULMUYOR. Her durum, o an
diskteki kanittan hesaplaniyor:

    ACTIVE       : bir surec dosyayi acik tutuyor VEYA mtime active_grace icinde
    COMPLETED    : aktif degil (yazim bitmis)
    ANALYZED     : bir ozetin raw_artifacts listesi bu dosyayi kapsiyor
    SUMMARIZED   : o ozet dosyasi gercekten var ve ayristirilabiliyor
    VERIFIED     : o ozet zorunlu alan dogrulamasindan geciyor
    ARCHIVABLE   : VERIFIED + recent-retention penceresinin disinda
    PURGED       : arsivi de kaldirilmis (yalnizca denetim kaydinda yasar)

Bozulacak/bayatlayacak bir state dosyasi yok; kanit kaybolursa durum kendiliginden
geriye duser ve arac muhafazakar davranir.

FAIL-CLOSED
-----------
Bir artifact'in kullanimda olup olmadigi BELIRLENEMEZSE (ornegin lsof yoksa veya
hata verirse) artifact DOKUNULMAZ sayilir. "Bilmiyorum" asla "silinebilir" degildir.
Bu, deponun .claude/hooks/guard.py dosyasindaki ayni ilkeyle uyumludur.

GECICI ALAN != PROJE HAFIZASI
-----------------------------
Claude'un /tmp session scratchpad'i `ephemeral` kok olarak izlenir: temizlik
kapsamindadir ama ORAYA HICBIR SEY YAZILMAZ ve orasi asla ozet barindiramaz.
Proje gecmisi yalnizca docs/test-history/ altinda yasar.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

# --- Yasam dongusu durumlari (spec sirasi korunur) ---------------------------
ACTIVE = "ACTIVE"
COMPLETED = "COMPLETED"
ANALYZED = "ANALYZED"
SUMMARIZED = "SUMMARIZED"
VERIFIED = "VERIFIED"
ARCHIVABLE = "ARCHIVABLE"
PURGED = "PURGED"

STATE_ORDER = [ACTIVE, COMPLETED, ANALYZED, SUMMARIZED, VERIFIED, ARCHIVABLE, PURGED]

# --- Plan eylemleri ----------------------------------------------------------
KEEP = "KEEP"
ARCHIVE = "ARCHIVE"
PURGE = "PURGE"

# --- Esik seviyeleri ---------------------------------------------------------
OK = "OK"
WARNING = "WARNING"
CRITICAL = "CRITICAL"

GB = 1024 ** 3

# Ozetin frontmatter'inda ZORUNLU anahtarlar. Kullanicinin istedigi alan
# listesinin makine tarafindan dogrulanabilen yarisi.
REQUIRED_META = ("phase_id", "date", "raw_artifacts")

# Ozetin govdesinde ZORUNLU H2 basliklari. Prose tarafi; ev tarzi (KNOWN_ISSUES.md,
# SPEC_SAPMALARI.md) numarali/baslikli Markdown oldugu icin ayni bicim korunuyor.
REQUIRED_SECTIONS = (
    "Amaç",
    "Değişiklikler",
    "Test sonucu",
    "Başarısızlıklar",
    "Kök neden",
    "Uygulanan çözüm",
    "Doğrulama",
    "Önemli metrikler",
    "İlgili commit",
    "Sonraki adım",
)

# Bir bolumun "doldurulmus" sayilmasi icin gereken en az anlamli karakter.
# Baslik altinda tek satirlik "-" veya "TODO" birakip artifact silmeyi engeller.
MIN_SECTION_CHARS = 12

# Bilerek bos birakilabilecek bolumler: her testin basarisizligi olmaz. Ama
# "yok" demek de bilincli bir beyandir, bos birakmak degil.
EMPTY_ALLOWED_MARKERS = ("yok", "yok.", "-", "n/a", "yok — ", "yok - ")

DEFAULT_CONFIG_NAME = "retention.config.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def human(n: int) -> str:
    """Bayti insan okunur birime cevirir."""
    f = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(f) < 1024.0 or unit == "TB":
            return f"{f:.1f} {unit}" if unit != "B" else f"{int(f)} B"
        f /= 1024.0
    return f"{f:.1f} TB"


# =============================================================================
# Konfigurasyon
# =============================================================================

@dataclass(frozen=True)
class Root:
    """Izlenen bir artifact koku.

    kind="project"  : proje icindeki calisma ciktilari (v33/logs gibi)
    kind="ephemeral": ajanin gecici alani (Claude scratchpad gibi) -- buraya
                      ASLA yazilmaz, burasi ASLA ozet barindiramaz.
    """
    path: str
    kind: str = "project"
    patterns: tuple = ("*",)

    @property
    def is_ephemeral(self) -> bool:
        return self.kind == "ephemeral"


@dataclass(frozen=True)
class Config:
    roots: tuple = ()
    history_dir: str = "docs/test-history"
    archive_dir: str = "docs/test-history/_archive"
    warning_bytes: int = 10 * GB
    critical_bytes: int = 15 * GB
    # RECENT RETENTION: ikisi de gecerlidir, hangisi daha korumaciysa o kazanir.
    recent_keep_days: int = 3
    recent_keep_runs: int = 5
    # Bir dosya son bu kadar saniye icinde degistiyse hala yaziliyor olabilir.
    active_grace_seconds: int = 900
    # Arsiv bu yastan sonra "yalnizca ozet" katmanina duser (PURGE).
    purge_archive_after_days: int = 90
    min_artifact_bytes: int = 0

    @staticmethod
    def defaults(repo_root: str) -> "Config":
        return Config(roots=(Root(path="logs", kind="project"),))


def _coerce_bytes(value) -> int:
    """10, "10GB", "10 GB", "500MB" kabul eder."""
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().upper().replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(B|KB|MB|GB|TB)?", s)
    if not m:
        raise ValueError(f"boyut ayristirilamadi: {value!r}")
    mult = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": GB, "TB": 1024 ** 4}
    return int(float(m.group(1)) * mult.get(m.group(2) or "B", 1))


def load_config(path: str | None, repo_root: str) -> Config:
    """Modul varsayilanlarini istege bagli JSON dosyasiyla ezer.

    Esikler SABIT KODLANMAZ: hepsi bu dosyadan degistirilebilir. Dosya yoksa
    varsayilanlar kullanilir ve bu bir hata degildir.
    """
    cfg = Config.defaults(repo_root)
    if not path or not os.path.isfile(path):
        return cfg
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    roots = []
    for r in raw.get("roots", []):
        roots.append(Root(
            path=r["path"],
            kind=r.get("kind", "project"),
            patterns=tuple(r.get("patterns", ["*"])),
        ))
    fields = {}
    if roots:
        fields["roots"] = tuple(roots)
    for key in ("history_dir", "archive_dir"):
        if key in raw:
            fields[key] = raw[key]
    for key in ("warning_bytes", "critical_bytes", "min_artifact_bytes"):
        if key in raw:
            fields[key] = _coerce_bytes(raw[key])
    for key in ("recent_keep_days", "recent_keep_runs",
                "active_grace_seconds", "purge_archive_after_days"):
        if key in raw:
            fields[key] = int(raw[key])
    cfg = replace(cfg, **fields)
    if cfg.warning_bytes > cfg.critical_bytes:
        raise ValueError("warning_bytes, critical_bytes'tan buyuk olamaz")
    return cfg


# =============================================================================
# Kesif
# =============================================================================

@dataclass
class Artifact:
    path: str
    size: int
    mtime: float
    root_kind: str
    state: str = COMPLETED
    summary: str | None = None       # bu artifact'i temsil eden ozet dosyasi
    reason: str = ""                 # durumun NEDEN bu oldugu (rapor icin)
    action: str = KEEP

    @property
    def is_ephemeral(self) -> bool:
        return self.root_kind == "ephemeral"


def discover(cfg: Config, repo_root: str) -> list:
    """Izlenen koklerdeki artifact'leri toplar. Hicbir sey yazmaz."""
    found = []
    seen = set()
    for root in cfg.roots:
        base = root.path if os.path.isabs(root.path) else os.path.join(repo_root, root.path)
        base = os.path.realpath(base)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            # Arsiv dizinini artifact olarak sayma -- o zaten cikti.
            dirnames[:] = [d for d in dirnames if d != "_archive"]
            for name in filenames:
                if not any(fnmatch.fnmatch(name, p) for p in root.patterns):
                    continue
                full = os.path.join(dirpath, name)
                real = os.path.realpath(full)
                if real in seen or not os.path.isfile(real):
                    continue
                try:
                    st = os.stat(real)
                except OSError:
                    continue
                if st.st_size < cfg.min_artifact_bytes:
                    continue
                seen.add(real)
                found.append(Artifact(path=real, size=st.st_size,
                                      mtime=st.st_mtime, root_kind=root.kind))
    found.sort(key=lambda a: a.size, reverse=True)
    return found


def open_paths() -> set:
    """Su an bir surec tarafindan acik tutulan dosya yollari.

    FAIL-CLOSED: lsof yoksa veya hata verirse ValueError firlatir; cagiran
    tarafta bu "hicbir seye dokunma" anlamina gelir.
    """
    exe = shutil.which("lsof")
    if not exe:
        raise ValueError("lsof bulunamadi -- kullanimda olan dosyalar belirlenemiyor")
    try:
        proc = subprocess.run([exe, "-Fn", "-w"], capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise ValueError(f"lsof calistirilamadi: {e}") from e
    # lsof acik dosyasi olmayan surecler icin sifir disi kod dondurebilir;
    # cikti geldiyse kullanilabilir sayiyoruz.
    if not proc.stdout and proc.returncode not in (0, 1):
        raise ValueError(f"lsof beklenmedik sekilde bitti (rc={proc.returncode})")
    out = set()
    for line in proc.stdout.splitlines():
        if line.startswith("n/"):
            out.add(os.path.realpath(line[1:]))
    return out


# =============================================================================
# Ozetler: ayristirma ve DOGRULAMA
# =============================================================================

@dataclass
class Summary:
    path: str
    meta: dict = field(default_factory=dict)
    sections: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)

    @property
    def phase_id(self) -> str:
        return str(self.meta.get("phase_id", "")).strip()

    @property
    def is_valid(self) -> bool:
        return not self.problems


_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> dict:
    """YAML frontmatter'i ayristirir.

    pyyaml projenin ilan edilmis bagimliligi (pyproject.toml) ve config
    dosyalari zaten YAML; ayri bir mini-ayristirici yazmak gereksiz
    abstraction olurdu.
    """
    m = _FRONTMATTER.match(text)
    if not m:
        return {}
    import yaml  # tembel: arac yaml olmadan da --help verebilsin
    data = yaml.safe_load(m.group(1))
    return data if isinstance(data, dict) else {}


def _parse_sections(text: str) -> dict:
    """H2 basliklarini ve altlarindaki govdeyi toplar."""
    body = _FRONTMATTER.sub("", text, count=1)
    out = {}
    current = None
    buf = []
    for line in body.splitlines():
        m = re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            if current is not None:
                out[current] = "\n".join(buf).strip()
            current = m.group(1).strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        out[current] = "\n".join(buf).strip()
    return out


def _section_is_filled(name: str, value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    if v.lower() in EMPTY_ALLOWED_MARKERS:
        # "Yok" bilincli bir beyandir; ama tek basina "-" degildir.
        return v.lower().startswith("yok")
    if re.fullmatch(r"(?i)(todo|tbd|xxx|\.\.\.|-{1,3})", v):
        return False
    return len(v) >= MIN_SECTION_CHARS


def parse_summary(path: str) -> Summary:
    """Bir ozet dosyasini okur ve ZORUNLU alanlari dogrular.

    Bu, 'summary'nin gerekli bilgileri icerdigi dogrulanmali' guvenlik
    sartinin makine tarafindaki karsiligi. Basarisiz olan ozet, temsil ettigi
    artifact'i ASLA silinebilir yapmaz.
    """
    s = Summary(path=path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as e:
        s.problems.append(f"okunamadi: {e}")
        return s
    try:
        s.meta = _parse_frontmatter(text)
    except Exception as e:            # bozuk YAML ozeti gecersiz kilar
        s.problems.append(f"frontmatter ayristirilamadi: {e}")
        return s
    s.sections = _parse_sections(text)

    for key in REQUIRED_META:
        val = s.meta.get(key)
        if val is None or (isinstance(val, str) and not val.strip()) or (
                isinstance(val, list) and not val):
            s.problems.append(f"frontmatter eksik/bos: {key}")
    for name in REQUIRED_SECTIONS:
        if name not in s.sections:
            s.problems.append(f"bolum yok: ## {name}")
        elif not _section_is_filled(name, s.sections[name]):
            s.problems.append(f"bolum doldurulmamis: ## {name}")
    return s


def load_summaries(history_dir: str) -> list:
    if not os.path.isdir(history_dir):
        return []
    out = []
    for name in sorted(os.listdir(history_dir)):
        if not name.endswith(".md"):
            continue
        # Index, sablon ve denetim kaydi birer ozet degildir.
        if name in ("README.md", "TEMPLATE.md", "cleanup-history.md"):
            continue
        out.append(parse_summary(os.path.join(history_dir, name)))
    return out


def _summary_globs(summary: Summary, repo_root: str) -> list:
    raw = summary.meta.get("raw_artifacts") or []
    if isinstance(raw, str):
        raw = [raw]
    out = []
    for item in raw:
        pat = str(item).strip()
        if not pat:
            continue
        out.append(pat if os.path.isabs(pat) else os.path.join(repo_root, pat))
    return out


def build_coverage(summaries: list, repo_root: str) -> list:
    """(glob, Summary) ciftleri -- hangi ozet hangi ham veriyi temsil ediyor."""
    pairs = []
    for s in summaries:
        for g in _summary_globs(s, repo_root):
            pairs.append((os.path.realpath(g) if "*" not in g and "?" not in g else g, s))
    return pairs


# =============================================================================
# Siniflandirma -- durum KANITTAN hesaplanir
# =============================================================================

def _matches(path: str, pattern: str) -> bool:
    if "*" in pattern or "?" in pattern or "[" in pattern:
        return fnmatch.fnmatch(path, pattern)
    return os.path.realpath(pattern) == path


def classify(artifacts: list, coverage: list, cfg: Config,
             busy: set, now: float) -> list:
    """Her artifact'e yasam dongusu durumu atar.

    `busy` = su an acik tutulan yollar. Bos kume 'hicbiri acik degil' demektir;
    'bilinmiyor' durumu cagiran tarafta ele alinir (bkz. build_plan).
    """
    # RECENT RETENTION penceresi: son N gun VE son N kosu -- hangisi daha
    # koruyucuysa o kazanir, yani ikisinden biri koruyorsa artifact kalir.
    day_cut = now - cfg.recent_keep_days * 86400
    by_recent = sorted(artifacts, key=lambda a: a.mtime, reverse=True)
    recent_paths = {a.path for a in by_recent[:cfg.recent_keep_runs]}

    for a in artifacts:
        if a.path in busy:
            a.state, a.reason = ACTIVE, "bir surec dosyayi acik tutuyor"
            continue
        if now - a.mtime < cfg.active_grace_seconds:
            a.state, a.reason = ACTIVE, (
                f"son {cfg.active_grace_seconds}s icinde degisti, hala yaziliyor olabilir")
            continue

        a.state, a.reason = COMPLETED, "yazim bitmis, ozet yok"
        match = None
        for pattern, summary in coverage:
            if _matches(a.path, pattern):
                match = summary
                break
        if match is None:
            continue

        a.summary = match.path
        if not os.path.isfile(match.path):
            a.state, a.reason = ANALYZED, "ozet dosyasi bulunamadi"
            continue
        a.state, a.reason = SUMMARIZED, "ozet var, dogrulama bekliyor"
        if not match.is_valid:
            a.reason = "ozet ZORUNLU alan dogrulamasindan GECMEDI: " + \
                       "; ".join(match.problems[:3])
            continue

        a.state, a.reason = VERIFIED, f"dogrulanmis ozet: {os.path.basename(match.path)}"
        if a.path in recent_paths:
            a.reason += f" | recent-retention: son {cfg.recent_keep_runs} kosudan biri"
            continue
        if a.mtime >= day_cut:
            a.reason += f" | recent-retention: son {cfg.recent_keep_days} gun icinde"
            continue
        a.state = ARCHIVABLE
        a.reason = f"dogrulanmis ozet ({os.path.basename(match.path)}) + pencere disinda"
    return artifacts


# =============================================================================
# Esik ve plan
# =============================================================================

def threshold_level(total: int, cfg: Config) -> str:
    if total >= cfg.critical_bytes:
        return CRITICAL
    if total >= cfg.warning_bytes:
        return WARNING
    return OK


@dataclass
class Plan:
    level: str
    total_before: int
    artifacts: list = field(default_factory=list)
    blocked: list = field(default_factory=list)   # (Artifact, sebep)
    notes: list = field(default_factory=list)

    @property
    def to_archive(self) -> list:
        return [a for a in self.artifacts if a.action == ARCHIVE]

    @property
    def to_purge(self) -> list:
        return [a for a in self.artifacts if a.action == PURGE]

    @property
    def reclaimable(self) -> int:
        return sum(a.size for a in self.artifacts if a.action in (ARCHIVE, PURGE))


def build_plan(artifacts: list, cfg: Config, busy_known: bool,
               level: str, total: int) -> Plan:
    """Siniflandirilmis artifact'lerden bir temizlik plani uretir.

    ALTI GUVENLIK SARTI burada uygulanir:
      1. test tamamlanmis  -> state ACTIVE degil
      2. analiz edilmis    -> bir ozet kapsiyor
      3. ozet olusmus      -> ozet dosyasi mevcut
      4. ozet dogrulanmis  -> zorunlu alanlar dolu (state >= VERIFIED)
      5. temsil kaydi      -> a.summary doldurulmus, denetim kaydina yazilir
      6. kullanimda degil  -> busy kumesi + active_grace
    """
    plan = Plan(level=level, total_before=total)
    if not busy_known:
        plan.notes.append(
            "FAIL-CLOSED: kullanimdaki dosyalar belirlenemedi (lsof yok/hata). "
            "Hicbir artifact islenmeyecek.")
        for a in artifacts:
            a.action = KEEP
            plan.blocked.append((a, "kullanim durumu belirlenemedi"))
        return plan

    if level == OK:
        plan.notes.append(
            f"Esik altinda ({human(total)} < WARNING {human(cfg.warning_bytes)}). "
            "Otomatik arsivleme tetiklenmez; ARCHIVABLE olanlar aday olarak listelenir.")

    for a in artifacts:
        if a.state == ARCHIVABLE:
            # Esik OK ise adaydir ama plana ALINMAZ (kucuk/aktif testler normal tutulur).
            if level == OK:
                a.action = KEEP
                plan.blocked.append((a, "aday, ama esik altinda -- otomatik islem yok"))
            else:
                a.action = ARCHIVE
                plan.artifacts.append(a)
        else:
            a.action = KEEP
            plan.blocked.append((a, f"{a.state}: {a.reason}"))

    # CRITICAL'de bile guvenlik sartlari gevsetilmez; yalnizca daha fazlasi
    # islenmeye calisilmaz. Esigi asmak sartlari atlamanin gerekcesi degildir.
    if level == CRITICAL and not plan.artifacts:
        plan.notes.append(
            "CRITICAL esik asildi ama guvenlik sartlarini gecen artifact YOK. "
            "Silme yapilmadi -- once ilgili phase ozetlerini yazip dogrulayin.")
    return plan


# =============================================================================
# Yurutme -- arsivle, DOGRULA, sonra sil (kismi hataya karsi guvenli)
# =============================================================================

@dataclass
class ApplyResult:
    archived: list = field(default_factory=list)   # (artifact, arsiv yolu)
    purged: list = field(default_factory=list)
    freed: int = 0
    error: str | None = None
    stopped_at: str | None = None
    unprocessed: list = field(default_factory=list)


def _archive_one(a: Artifact, archive_dir: str, repo_root: str) -> str:
    """Tek artifact'i .tar.gz'e alir ve arsivi GERI OKUYARAK dogrular.

    Dogrulama gecmezse arsiv silinir ve hata firlatilir -- ham veri korunur.
    """
    os.makedirs(archive_dir, exist_ok=True)
    base = os.path.basename(a.path)
    stamp = datetime.fromtimestamp(a.mtime, timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = os.path.join(archive_dir, f"{stamp}__{base}.tar.gz")
    n = 1
    while os.path.exists(out):
        out = os.path.join(archive_dir, f"{stamp}__{base}.{n}.tar.gz")
        n += 1
    with tarfile.open(out, "w:gz") as tf:
        tf.add(a.path, arcname=base)
    # GERI OKUMA DOGRULAMASI: uye var mi ve boyutu birebir tutuyor mu?
    try:
        with tarfile.open(out, "r:gz") as tf:
            member = tf.getmember(base)
            if member.size != a.size:
                raise ValueError(
                    f"arsiv boyutu tutmuyor: {member.size} != {a.size}")
            fh = tf.extractfile(member)
            if fh is None:
                raise ValueError("arsiv uyesi okunamadi")
            fh.read(1)
    except Exception:
        if os.path.exists(out):
            os.unlink(out)
        raise
    return out


def apply_plan(plan: Plan, cfg: Config, repo_root: str, dry_run: bool) -> ApplyResult:
    """Plani yurutur. HERHANGI bir adim hata verirse ANINDA durur.

    Durdugunda: ne islendigi, nerede durdugu ve neyin islenmedigi kaydedilir.
    Ham veri yalnizca dogrulanmis bir arsiv OLUSTUKTAN SONRA silinir; yani
    kismi hata durumunda veri kaybi olmaz.
    """
    res = ApplyResult()
    archive_dir = cfg.archive_dir if os.path.isabs(cfg.archive_dir) \
        else os.path.join(repo_root, cfg.archive_dir)
    queue = list(plan.to_archive) + list(plan.to_purge)

    for i, a in enumerate(queue):
        try:
            if a.action == ARCHIVE:
                if dry_run:
                    res.archived.append((a, "(dry-run: arsiv yazilmadi)"))
                else:
                    dest = _archive_one(a, archive_dir, repo_root)
                    os.unlink(a.path)       # yalnizca dogrulanmis arsivden SONRA
                    res.archived.append((a, dest))
                res.freed += a.size
            elif a.action == PURGE:
                if not dry_run:
                    os.unlink(a.path)
                res.purged.append(a)
                res.freed += a.size
        except Exception as e:              # noqa: BLE001 -- her hatada dur
            res.error = f"{type(e).__name__}: {e}"
            res.stopped_at = a.path
            res.unprocessed = [x.path for x in queue[i:]]
            return res
    return res


# =============================================================================
# Denetim kaydi (cleanup-history.md)
# =============================================================================

AUDIT_HEADER = """# Cleanup History — temizlik denetim kaydı

Bu dosyayı `tools/artifact_retention.py apply` üretir. Elle düzenlenmez.
Her giriş bir temizlik çalıştırmasını temsil eder; PURGED artifact'ler yalnızca
burada ve kendilerini temsil eden phase özetinde yaşar.
"""


def append_audit(audit_path: str, cfg: Config, plan: Plan, res: ApplyResult,
                 total_after: int, dry_run: bool, when: datetime) -> str:
    os.makedirs(os.path.dirname(audit_path), exist_ok=True)
    if not os.path.exists(audit_path):
        with open(audit_path, "w", encoding="utf-8") as fh:
            fh.write(AUDIT_HEADER)

    ts = when.strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [
        "",
        f"## {ts}" + ("  *(dry-run)*" if dry_run else ""),
        "",
        f"- **Eşik durumu:** {plan.level} "
        f"(WARNING {human(cfg.warning_bytes)} / CRITICAL {human(cfg.critical_bytes)})",
        f"- **Önceki boyut:** {human(plan.total_before)}",
        f"- **Sonraki boyut:** {human(total_after)}",
        f"- **Kazanılan alan:** {human(res.freed)}",
        f"- **İşlenen artifact:** {len(res.archived) + len(res.purged)}",
        f"- **Arşivlenen:** {len(res.archived)}",
        f"- **Silinen (purge):** {len(res.purged)}",
        f"- **Dokunulmayan:** {len(plan.blocked)}",
    ]
    if res.error:
        lines += [
            "",
            "### ⚠️ KISMİ BAŞARISIZLIK — işlem durduruldu",
            "",
            f"- **Hata:** `{res.error}`",
            f"- **Durduğu artifact:** `{res.stopped_at}`",
            f"- **İşlenmeyen ({len(res.unprocessed)}):**",
        ]
        lines += [f"  - `{p}`" for p in res.unprocessed[:20]]
        if len(res.unprocessed) > 20:
            lines.append(f"  - … +{len(res.unprocessed) - 20} tane daha")

    if res.archived:
        lines += ["", "### Arşivlenenler (ham → sıkıştırılmış)", "",
                  "| artifact | boyut | temsil eden özet | arşiv |",
                  "|---|---|---|---|"]
        for a, dest in res.archived:
            lines.append(
                f"| `{os.path.basename(a.path)}` | {human(a.size)} | "
                f"`{os.path.basename(a.summary or '?')}` | `{os.path.basename(str(dest))}` |")
    if res.purged:
        lines += ["", "### Silinenler (yalnızca özet katmanı)", "",
                  "| artifact | boyut | temsil eden özet |", "|---|---|---|"]
        for a in res.purged:
            lines.append(f"| `{os.path.basename(a.path)}` | {human(a.size)} | "
                         f"`{os.path.basename(a.summary or '?')}` |")
    if plan.notes:
        lines += ["", "### Notlar", ""] + [f"- {n}" for n in plan.notes]
    lines.append("")

    entry = "\n".join(lines)
    with open(audit_path, "a", encoding="utf-8") as fh:
        fh.write(entry)
    return entry


# =============================================================================
# Raporlama
# =============================================================================

def _bar(level: str) -> str:
    return {OK: "OK", WARNING: "!! WARNING", CRITICAL: "!!! CRITICAL"}[level]


def report_scan(artifacts: list, cfg: Config, total: int, level: str,
                busy_known: bool, out) -> None:
    p = lambda s="": print(s, file=out)
    p(f"=== ARTIFACT TARAMASI ===")
    p(f"toplam: {human(total)}   durum: {_bar(level)}   "
      f"(WARNING {human(cfg.warning_bytes)} / CRITICAL {human(cfg.critical_bytes)})")
    if not busy_known:
        p("UYARI: kullanimdaki dosyalar belirlenemedi -- FAIL-CLOSED, hicbiri islenemez.")
    p()
    counts = {}
    sizes = {}
    for a in artifacts:
        counts[a.state] = counts.get(a.state, 0) + 1
        sizes[a.state] = sizes.get(a.state, 0) + a.size
    p("durum dagilimi:")
    for st in STATE_ORDER:
        if st in counts:
            p(f"  {st:<12} {counts[st]:>4} dosya   {human(sizes[st]):>10}")
    p()
    p("en buyuk 15 artifact:")
    p(f"  {'durum':<12} {'boyut':>10}  {'kok':<10} dosya")
    for a in artifacts[:15]:
        kind = "EPHEMERAL" if a.is_ephemeral else "project"
        p(f"  {a.state:<12} {human(a.size):>10}  {kind:<10} {os.path.basename(a.path)}")
        p(f"  {'':<12} {'':>10}  {'':<10}   -> {a.reason}")


def report_plan(plan: Plan, cfg: Config, out) -> None:
    p = lambda s="": print(s, file=out)
    p("=== TEMIZLIK PLANI ===")
    p(f"esik durumu : {_bar(plan.level)}")
    p(f"onceki boyut: {human(plan.total_before)}")
    p(f"kazanilacak : {human(plan.reclaimable)}")
    p(f"arsivlenecek: {len(plan.to_archive)}   silinecek: {len(plan.to_purge)}   "
      f"dokunulmayacak: {len(plan.blocked)}")
    for n in plan.notes:
        p(f"NOT: {n}")
    if plan.artifacts:
        p()
        p("ISLENECEKLER:")
        for a in plan.artifacts:
            p(f"  [{a.action}] {human(a.size):>10}  {os.path.basename(a.path)}")
            p(f"           temsil eden ozet: {os.path.basename(a.summary or '?')}")
    if plan.blocked:
        p()
        p("DOKUNULMAYACAKLAR (ilk 15):")
        for a, why in plan.blocked[:15]:
            p(f"  [KEEP] {human(a.size):>10}  {os.path.basename(a.path)}")
            p(f"           {why}")
        if len(plan.blocked) > 15:
            p(f"  ... +{len(plan.blocked) - 15} tane daha")


def report_verify(summaries: list, out) -> int:
    p = lambda s="": print(s, file=out)
    p("=== OZET DOGRULAMA ===")
    if not summaries:
        p("hic ozet yok.")
        return 0
    bad = 0
    for s in summaries:
        if s.is_valid:
            p(f"  GECTI    {os.path.basename(s.path)}  (phase={s.phase_id})")
        else:
            bad += 1
            p(f"  GECMEDI  {os.path.basename(s.path)}")
            for prob in s.problems:
                p(f"             - {prob}")
    p()
    p(f"{len(summaries) - bad}/{len(summaries)} ozet gecerli.")
    return bad


# =============================================================================
# CLI
# =============================================================================

def _repo_root(args) -> str:
    return os.path.realpath(args.repo_root or os.getcwd())


def _gather(args):
    """Ortak yol: config yukle, kesfet, ozetleri dogrula, siniflandir."""
    repo = _repo_root(args)
    cfg_path = args.config or os.path.join(repo, "docs", "test-history", DEFAULT_CONFIG_NAME)
    cfg = load_config(cfg_path, repo)
    history = cfg.history_dir if os.path.isabs(cfg.history_dir) \
        else os.path.join(repo, cfg.history_dir)

    artifacts = discover(cfg, repo)
    total = sum(a.size for a in artifacts)
    level = threshold_level(total, cfg)

    summaries = load_summaries(history)
    coverage = build_coverage(summaries, repo)

    busy_known = True
    busy = set()
    try:
        busy = open_paths()
    except ValueError:
        busy_known = False

    now = args.now if getattr(args, "now", None) else time.time()
    classify(artifacts, coverage, cfg, busy, now)
    return repo, cfg, history, artifacts, total, level, summaries, busy_known, now


def cmd_scan(args, out=sys.stdout) -> int:
    _, cfg, _, artifacts, total, level, _, busy_known, _ = _gather(args)
    report_scan(artifacts, cfg, total, level, busy_known, out)
    return 0


def cmd_verify(args, out=sys.stdout) -> int:
    _, _, history, _, _, _, summaries, _, _ = _gather(args)
    print(f"(dizin: {history})", file=out)
    return 1 if report_verify(summaries, out) else 0


def cmd_plan(args, out=sys.stdout) -> int:
    _, cfg, _, artifacts, total, level, _, busy_known, _ = _gather(args)
    plan = build_plan(artifacts, cfg, busy_known, level, total)
    report_plan(plan, cfg, out)
    return 0


def cmd_apply(args, out=sys.stdout) -> int:
    repo, cfg, history, artifacts, total, level, _, busy_known, _ = _gather(args)
    plan = build_plan(artifacts, cfg, busy_known, level, total)
    report_plan(plan, cfg, out)

    if not plan.artifacts:
        print("\nIslenecek artifact yok -- hicbir sey yapilmadi.", file=out)
        return 0
    if not args.yes:
        print("\n--yes verilmedi: hicbir sey yapilmadi. Plani onaylamak icin "
              "'apply --yes' calistirin.", file=out)
        return 0

    res = apply_plan(plan, cfg, repo, args.dry_run)
    total_after = total - res.freed
    entry = append_audit(os.path.join(history, "cleanup-history.md"),
                         cfg, plan, res, total_after, args.dry_run, _utcnow())

    print("\n=== YURUTME ===", file=out)
    print(f"arsivlenen: {len(res.archived)}   silinen: {len(res.purged)}   "
          f"kazanilan: {human(res.freed)}", file=out)
    if res.error:
        print(f"\n!!! DURDURULDU: {res.error}", file=out)
        print(f"    durdugu yer : {res.stopped_at}", file=out)
        print(f"    islenmeyen  : {len(res.unprocessed)} artifact (SILINMEDI)", file=out)
        print("    Ham veri kaybi YOK -- silme yalnizca dogrulanmis arsivden sonra yapilir.",
              file=out)
    print(f"\ndenetim kaydi guncellendi: {os.path.join(history, 'cleanup-history.md')}",
          file=out)
    if args.dry_run:
        print("(dry-run: diskte hicbir artifact degismedi)", file=out)
    return 2 if res.error else 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="artifact_retention",
        description="Test History & Artifact Retention -- ham veri gecici, bilgi kalici.")
    ap.add_argument("--repo-root", default=None,
                    help="proje koku (varsayilan: cwd)")
    ap.add_argument("--config", default=None,
                    help=f"config JSON (varsayilan: docs/test-history/{DEFAULT_CONFIG_NAME})")
    ap.add_argument("--now", type=float, default=None,
                    help="test icin: 'simdi'yi epoch saniye olarak sabitle")
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="artifact'leri kesfet ve durumlarini goster (yazma yok)")
    sub.add_parser("verify", help="phase ozetlerini zorunlu alanlara karsi dogrula")
    sub.add_parser("plan", help="temizlik planini goster (yazma yok)")

    ap_apply = sub.add_parser("apply", help="plani yurut (arsivle/sil) ve denetime yaz")
    ap_apply.add_argument("--yes", action="store_true",
                          help="ONAY: bu bayrak olmadan hicbir sey silinmez")
    ap_apply.add_argument("--dry-run", action="store_true",
                          help="ne yapilacagini yaz, diske dokunma")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"scan": cmd_scan, "verify": cmd_verify,
                "plan": cmd_plan, "apply": cmd_apply}
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
