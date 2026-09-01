#!/usr/bin/env python3
"""KURSAD40 -- tek yarışma alanı üreticisi (default.sdf).

NEDEN VAR
---------
Yarışma TEK bir parkurda geçiyor: 30 m (X) x 100 m (Y), siyah/nötr bir
çerçeveyle sınırlı, içinde DÖRT hedefin tamamı aynı anda:

    Mavi Altıgen (2 m köşe-köşe)   Kırmızı Üçgen (1 m)
    Kırmızı Kare (1 m)             Mavi Kare (2 m)

Bu script, SITL her açılışında `safe_sitl_launcher.sh` tarafından
OTOMATİK çalıştırılır ve dört şekli her seferinde yeniden, rastgele
konumlandırır. Elle çalıştırmak gerekmez (ama `--dry-run` ile denetlenebilir).

ÖNCEKİ İKİ-LANE SİSTEMİNİN YERİNİ ALDI. Lane A (X merkez 0) ve Lane B
(X merkez 50) ayrımı, `_b` sonekli model instance'ları ve
KURSAD_LANE_A/B_START/END blokları tamamen kaldırıldı.

EKSEN KURALI
------------
Y ekseni = Kuzey = drone'un ileri (+N) ekseni; X ekseni = Doğu. px4-gz
bridge PX4'ün local-NED north_m'sini bu world'ün Y eksenine eşliyor, X'e
değil. 2026-08-13'te gerçek bir MAVSDK Offboard uçuşuyla ölçülüp
kanıtlandı. TAM KANIT METNİ (orijinal İngilizce, değiştirilmeden):

  "BUG FIX (runtime investigation, 2026-08-13): this used to be
  '15 0 0.05 0 0 0' [blue_hexagon] / '40 0 0.05 0 0 0' [red_triangle].
  Gazebo's world frame is ENU (X=East, Y=North), and the px4-gz bridge
  maps PX4's local-NED north_m to this world's Y axis, not X. '15 0'
  (blue_hexagon) / '40 0' (red_triangle) therefore placed the model
  15m/40m EAST of the drone, not in front on the +N centerline the
  comment above (and the file header) explicitly call for - proven via
  a live MAVSDK Offboard flight: commanding north=15 put the vehicle at
  world (0,15), 21m from the actual prop at (15,0), while commanding
  east=15 landed it exactly on top of the prop with a clean,
  correctly-classified MAVI_ALTIGEN detection dead-center in frame.
  Swapping X/Y puts the prop on the +N centerline as intended."

YERLEŞİM KURALLARI
------------------
1. Mavi Altıgen ile Kırmızı Üçgen arası mesafe **EN AZ 25 m**. ÜST SINIR
   YOK. (Önceki iki-lane sisteminde 20-25 m'lik bir ARALIK vardı ve
   kutupsal "annulus sampling" ile üretiliyordu; o kalktı. Artık iki nokta
   da alan içinde bağımsız-uniform seçilip mesafe < 25 m ise reddediliyor.)

   ÖLÇÜLDÜ (2M örnekli Monte Carlo, 24 x 94 m örnekleme dikdörtgeninde):
   kabul olasılığı 0.5742. MAX_SAMPLE_ATTEMPTS=200 ile hiç bulamama
   olasılığı 7e-75. Kısıtın sonucu: hedefler ortalama 47.7 m ayrık düşüyor
   (medyan 44.8, p10 28.4, p90 72.2, max 96.5) -- eski kuraldaki sabit
   ~22.5 m'nin 2.1 katı. Köşegen 97.02 m olduğu için üst sınırsızlık
   tanımlı kalıyor.

2. İki kare, önceden yerleşmiş HER şekilden en az MIN_SHAPE_SEPARATION_M
   uzakta (reject-sampling). Bu kural önceki sistemden AYNEN korundu.

3. Tüm şekiller alan sınırlarından EDGE_MARGIN_M içeride.

NE YAZAR
--------
İKİ şeye dokunur, başka hiçbir şeye:

  a) KURSAD_COMPETITION_AREA_START/END blokları arasındaki dört
     <include> -- silinip yeniden yazılır.
  b) payload_red / payload_blue modellerinin <pose> satırları -- araç
     spawn noktasına göre yeniden hesaplanır.

(b) NEDEN BURADA: iki payload dünya SDF'sinde SABİT dünya koordinatlarıyla
duruyor, araç ise `px4-rc.gzsim`'in PX4_GZ_MODEL_POSE'tan ürettiği AYRI bir
include ile doğuyor. İkisi ayrı yerlerden geldiği için sessizce ayrışabilir
-- ve ayrıştı: payload'lar X=0'da kalırken araç X=25'e taşınınca aradaki
DetachableJoint 25 m'lik yere çakılı bir halata döndü. 2026-08-30 ölçümü:
araç 4.90 m'ye tırmanıp 2.7 saniyede yere geri çekildi, sonra 483 saniye
boyunca MISSION modunda yerde kaldı (medyan irtifa -0.02 m).

Spawn `safe_sitl_launcher.sh`'ten OKUNUR, burada tekrarlanmaz. Böylece
"spawn değişti, payload unutuldu" hatası yapısal olarak imkânsız hale gelir.

Fizik, ışık, zemin, GPS origin, sınır çerçevesi include'u ve dosyanın geri
kalanına HİÇ dokunulmaz.

KULLANIM
--------
    python3 generate_competition_area.py --dry-run       # yazmaz, raporlar
    python3 generate_competition_area.py --seed 1        # deterministik
    python3 generate_competition_area.py                 # her sefer farklı
"""
import argparse
import datetime
import math
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
WORLD_FILE = HERE / "default.sdf"

# Payload pose'lari HANGI dunyalarda sabitlenecek.
#
# Sekil yerlesimi yalnizca default.sdf'te uretilir (KURSAD_COMPETITION_AREA
# marker'lari yalnizca orada var). Ama payload/spawn eslesmesi dunyaya ozgu
# DEGIL: PX4_GZ_MODEL_POSE tek ve dunyadan bagimsiz, dolayisiyla hangi dunya
# acilirsa acilsin payload'lar o spawn'da olmali. Kardes dunyalar bu listeye
# 2026-08-31'de eklendi: o tarihe kadar orijinde kalmislardi ve bu dunyalardan
# biri yeni spawn ile acilsaydi ayni 25 m'lik halat hatasini verirdi.
PAYLOAD_WORLDS = [WORLD_FILE,
                  HERE / "competition_day.sdf",
                  HERE / "competition_overcast.sdf"]
# Repo kökü: worlds -> gz -> simulation -> Tools -> <repo>
LAUNCHER_FILE = HERE.parent.parent.parent.parent / "safe_sitl_launcher.sh"

# --- alan geometrisi ---------------------------------------------------
AREA_WIDTH_M = 30.0      # X ekseni
AREA_LENGTH_M = 100.0    # Y ekseni
AREA_CENTER_X = 0.0
EDGE_MARGIN_M = 3.0      # şekiller alan kenarlarından bu kadar içeride kalır

# --- yerleşim kısıtları ------------------------------------------------
HEX_TRI_MIN_DIST_M = 25.0      # ALT SINIR; üst sınır YOK
MIN_SHAPE_SEPARATION_M = 5.0   # karelerin diğer TÜM şekillerden min mesafesi
MAX_SAMPLE_ATTEMPTS = 200

# --- payload montaj ofsetleri (GÖVDE/FLU çerçevesi: +X ileri, +Y SOL) ---
# ÖLÇÜLMÜŞ DEĞERLER, keyfi değil. F2 (2026-08-17) yükleri 0.20 m'den
# gövde merkezine yakın bu konuma taşıdı: iniş takımı skid'i |y| araliginda
# [0.1245, 0.1395], yükler |y| <= 0.06 -- tamamen içeride, yani "eklem
# çözülünce DART iç içe geçmiş çifti görüp payload'ı fırlatıyor" tuzağına
# girilmiyor. z = 0.035 = yük yüksekliğinin yarısı (yerde duruş yüksekliği).
# payload_red SAĞ (-y), payload_blue SOL (+y) monte edilir.
#
# BUNLAR GÖVDE ÇERÇEVESİNDEDİR, DÜNYA ÇERÇEVESİNDE DEĞİL. Araç yaw ile
# doğduğu için (spawn yaw = pi/2, kuzeye bakar) dünya pozisyonu bu ofsetin
# yaw kadar DÖNDÜRÜLMÜŞ halidir:
#
#     dunya = spawn + R_z(yaw) . (0, dy)
#           = (spawn_x - dy*sin(yaw),  spawn_y + dy*cos(yaw))
#
# ve payload'un kendi pose'una da yaw yazılır ki 0.14 m'lik uzun ekseni
# gövdenin ileri ekseniyle hizalı kalsın.
#
# BUNU KAÇIRMAK SESSİZ BİR HATADIR: dy doğrudan dünya Y'sine eklenirse
# yaw=pi/2'de kırmızı yük gövdenin 3.5 cm ARKASINA, mavi 3.5 cm ÖNÜNE
# düşer -- ikisi de merkez hattında, sağ/sol ayrımı yok olur ve kutular
# 90 derece dönük bağlanır. O durumda parameters.py'deki
# PAYLOAD_MOUNT_OFFSET_BODY_M = {"MAVI_ALTIGEN": (0.0, 0.035),
# "KIRMIZI_UCGEN": (0.0, -0.035)} FRD telafisi yanlış eksene nişan alır.
# (Eski spawn "25,0,0,0,0,0" yaw=0 olduğu için gövde Y == dünya Y idi ve
# bu ayrım görünmüyordu.)
PAYLOAD_RED_DY = -0.035
PAYLOAD_BLUE_DY = +0.035
PAYLOAD_Z = 0.035

# --- şekillerin dünya z'si (mevcut sistemle aynı) ----------------------
SHAPE_Z = 0.003

# Bu script her SITL acilisinda calisir; tutulacak yedek sayisi.
BACKUP_KEEP = 5

MARKER_START = "<!-- KURSAD_COMPETITION_AREA_START -->"
MARKER_END = "<!-- KURSAD_COMPETITION_AREA_END -->"
INDENT = "    "


class AreaGenerationError(RuntimeError):
    """Reject-sampling MAX_SAMPLE_ATTEMPTS içinde geçerli bir yerleşim
    bulamadığında yükselir -- sessizce çakışan bir yerleşim üretmektense
    açıkça başarısız olmak tercih edilir (launcher bunu görüp SITL'i hiç
    başlatmaz)."""


# ======================================================================
# Örnekleme
# ======================================================================
def _x_bounds() -> tuple:
    half = AREA_WIDTH_M / 2.0 - EDGE_MARGIN_M
    return AREA_CENTER_X - half, AREA_CENTER_X + half


def _y_bounds() -> tuple:
    return EDGE_MARGIN_M, AREA_LENGTH_M - EDGE_MARGIN_M


def _random_point(rng: random.Random) -> tuple:
    x_lo, x_hi = _x_bounds()
    y_lo, y_hi = _y_bounds()
    return rng.uniform(x_lo, x_hi), rng.uniform(y_lo, y_hi)


def sample_hex_and_triangle(rng: random.Random) -> tuple:
    """Altıgen ve Üçgeni alan içinde BAĞIMSIZ-uniform seçer, aralarındaki
    mesafe HEX_TRI_MIN_DIST_M'den küçükse reddeder.

    Eski annulus (kutupsal) örnekleme kaldırıldı: üst sınır olmayınca
    yarıçap örneklemenin bir anlamı kalmıyor ve iki-uniform + reddet hem
    daha basit hem de dağılımı doğru (annulus, merkez noktayı uniform
    seçse bile ikinciyi yarıçapta uniform seçtiği için alan-uniform
    DEĞİLDİ)."""
    for _ in range(MAX_SAMPLE_ATTEMPTS):
        hx, hy = _random_point(rng)
        tx, ty = _random_point(rng)
        if math.hypot(hx - tx, hy - ty) >= HEX_TRI_MIN_DIST_M:
            return (hx, hy), (tx, ty)
    raise AreaGenerationError(
        f"{MAX_SAMPLE_ATTEMPTS} denemede alan sınırları içinde en az "
        f"{HEX_TRI_MIN_DIST_M} m ayrık bir Altıgen/Üçgen çifti bulunamadı.")


def sample_point_far_from(rng: random.Random, existing_points: list,
                          min_sep: float = MIN_SHAPE_SEPARATION_M) -> tuple:
    """Alan içinde, `existing_points` listesindeki HER noktadan en az
    `min_sep` uzakta, tam bağımsız rastgele bir nokta seçer."""
    for _ in range(MAX_SAMPLE_ATTEMPTS):
        x, y = _random_point(rng)
        if all(math.hypot(x - ex, y - ey) >= min_sep for ex, ey in existing_points):
            return x, y
    raise AreaGenerationError(
        f"{MAX_SAMPLE_ATTEMPTS} denemede min {min_sep} m ayrık bir nokta "
        f"bulunamadı ({len(existing_points)} mevcut nokta).")


def build_area(rng: random.Random) -> tuple:
    (hx, hy), (tx, ty) = sample_hex_and_triangle(rng)
    placed = [(hx, hy), (tx, ty)]
    rx, ry = sample_point_far_from(rng, placed)
    placed.append((rx, ry))
    bx, by = sample_point_far_from(rng, placed)
    placed.append((bx, by))

    body = "\n\n".join([
        _make_include("blue_hexagon", "blue_hexagon", hx, hy),
        _make_include("red_triangle", "red_triangle", tx, ty),
        _make_include("red_square", "red_square", rx, ry),
        _make_include("blue_square", "blue_square", bx, by),
    ])
    positions = {
        "blue_hexagon": (hx, hy),
        "red_triangle": (tx, ty),
        "red_square": (rx, ry),
        "blue_square": (bx, by),
    }
    return body, positions, math.hypot(hx - tx, hy - ty)


def _make_include(model_uri: str, instance_name: str, x: float, y: float) -> str:
    return (f"{INDENT}<include>\n"
            f"{INDENT}  <uri>model://{model_uri}</uri>\n"
            f"{INDENT}  <name>{instance_name}</name>\n"
            f"{INDENT}  <pose>{x:.3f} {y:.3f} {SHAPE_Z} 0 0 0</pose>\n"
            f"{INDENT}</include>")


# ======================================================================
# Doğrulama
# ======================================================================
def check_all_pairwise(positions: dict) -> list:
    """Tüm çift-mesafe kısıtlarını kontrol eder, ihlalleri döner."""
    violations = []
    hex_tri = {"blue_hexagon", "red_triangle"}
    names = list(positions)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            n1, n2 = names[i], names[j]
            (x1, y1), (x2, y2) = positions[n1], positions[n2]
            dist = math.hypot(x1 - x2, y1 - y2)
            if {n1, n2} == hex_tri:
                # ALT SINIR yalnizca -- ust sinir kasitli olarak yok.
                if dist < HEX_TRI_MIN_DIST_M - 1e-6:
                    violations.append(f"  ! {n1} <-> {n2}: {dist:.3f} m "
                                      f"(min {HEX_TRI_MIN_DIST_M} m ihlali)")
            elif dist < MIN_SHAPE_SEPARATION_M - 1e-6:
                violations.append(f"  ! {n1} <-> {n2}: {dist:.3f} m "
                                  f"(min {MIN_SHAPE_SEPARATION_M} m ihlali)")
    x_lo, x_hi = _x_bounds()
    y_lo, y_hi = _y_bounds()
    for name, (x, y) in positions.items():
        if not (x_lo - 1e-6 <= x <= x_hi + 1e-6 and y_lo - 1e-6 <= y <= y_hi + 1e-6):
            violations.append(f"  ! {name}: ({x:.3f}, {y:.3f}) alan sınırları "
                              f"X[{x_lo},{x_hi}] Y[{y_lo},{y_hi}] dışında")
    return violations


# ======================================================================
# safe_sitl_launcher.sh'ten spawn okuma
# ======================================================================
_SPAWN_RE = re.compile(r'PX4_GZ_MODEL_POSE\s*=\s*"([^"]+)"')


def parse_spawn(path: Path = LAUNCHER_FILE) -> tuple:
    """PX4_GZ_MODEL_POSE="x,y,z,roll,pitch,yaw" -> (x, y, yaw).

    Spawn'ın tek doğruluk kaynağı launcher'dır, burada tekrarlanmaz.

    YAW ZORUNLU OLARAK OKUNUR: payload montaj ofsetleri gövde
    çerçevesindedir, dünya çerçevesine çevirmek için yaw gerekir (bkz.
    PAYLOAD_RED_DY yorumu). Yaw alanı yoksa 0.0 varsayılır -- bu Gazebo'nun
    kendi varsayılanıyla aynıdır, sessiz bir tahmin değildir."""
    m = _SPAWN_RE.search(path.read_text())
    if not m:
        raise AreaGenerationError(f"PX4_GZ_MODEL_POSE bulunamadı: {path}")
    parts = [float(v) for v in m.group(1).split(",")]
    if len(parts) < 2:
        raise AreaGenerationError(f"PX4_GZ_MODEL_POSE bozuk: {m.group(1)!r}")
    yaw = parts[5] if len(parts) >= 6 else 0.0
    return parts[0], parts[1], yaw


# ======================================================================
# default.sdf'e idempotent yazma
# ======================================================================
def _find_marker_block_span(text: str):
    i = text.find(MARKER_START)
    if i < 0:
        return None
    j = text.find(MARKER_END, i)
    if j < 0:
        raise AreaGenerationError(
            f"{MARKER_START} var ama {MARKER_END} yok -- default.sdf bozuk.")
    return i, j + len(MARKER_END)


def render_shapes(text: str, body: str) -> str:
    span = _find_marker_block_span(text)
    if span is None:
        raise AreaGenerationError(
            f"default.sdf içinde {MARKER_START} bulunamadı. Bu script yalnızca "
            f"marker'lar arasını yeniden yazar; blok bir kez elle kurulmalıdır.")
    block = f"{MARKER_START}\n{body}\n{INDENT}{MARKER_END}"
    return text[:span[0]] + block + text[span[1]:]


_PAYLOAD_POSE_RE_TMPL = (
    r'(<model name="{name}">\s*\n\s*<pose>)[^<]*(</pose>)'
)


def render_payload_poses(text: str, spawn_x: float, spawn_y: float,
                         spawn_yaw: float) -> tuple:
    """payload_red / payload_blue <pose>'unu spawn'a göre yeniden yazar.

    Gövde ofseti (0, dy) yaw kadar döndürülüp dünya çerçevesine taşınır ve
    yaw payload'un kendi pose'una da yazılır. 6 ondalık: ofsetler 35 mm
    mertebesinde ve tests/sdf_geometry.py bunları 1e-9 toleransla geri
    okuyor, 3 ondalık orada gürültü üretirdi."""
    out, applied = text, {}
    cy, sy = math.cos(spawn_yaw), math.sin(spawn_yaw)
    for name, dy in (("payload_red", PAYLOAD_RED_DY), ("payload_blue", PAYLOAD_BLUE_DY)):
        wx = spawn_x - dy * sy
        wy = spawn_y + dy * cy
        pose = (f"{wx:.6f} {wy:.6f} {PAYLOAD_Z} 0 0 {spawn_yaw:.10f}")
        pat = re.compile(_PAYLOAD_POSE_RE_TMPL.format(name=re.escape(name)))
        out, n = pat.subn(lambda m: m.group(1) + pose + m.group(2), out, count=1)
        if n != 1:
            raise AreaGenerationError(
                f'default.sdf içinde <model name="{name}"> pose satırı bulunamadı.')
        applied[name] = pose
    return out, applied


# ======================================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=None,
                        help="Deterministik üretim için tohum. Verilmezse her "
                             "çalıştırma farklı sonuç üretir.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Hiçbir dosyaya yazmaz; üretilecek koordinatları "
                             "ve kısıt kontrollerini stdout'a raporlar.")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    try:
        spawn_x, spawn_y, spawn_yaw = parse_spawn()
        body, positions, hex_tri_dist = build_area(rng)
    except AreaGenerationError as e:
        print(f"HATA: {e}", file=sys.stderr)
        return 1

    x_lo, x_hi = _x_bounds()
    y_lo, y_hi = _y_bounds()
    print(f"=== Yarışma alanı (merkez X={AREA_CENTER_X:g}, "
          f"{AREA_WIDTH_M:g} x {AREA_LENGTH_M:g} m) ===")
    print(f"  örnekleme sınırları: X[{x_lo:g}, {x_hi:g}]  Y[{y_lo:g}, {y_hi:g}]")
    for name, (x, y) in positions.items():
        print(f"  {name:16s} x={x:8.3f}  y={y:8.3f}")
    print(f"  Altıgen<->Üçgen mesafe: {hex_tri_dist:.3f} m "
          f"(min {HEX_TRI_MIN_DIST_M:g} m, üst sınır yok)")
    print(f"  araç spawn (launcher'dan): x={spawn_x:g}  y={spawn_y:g}  "
          f"yaw={spawn_yaw:.7f} rad ({math.degrees(spawn_yaw):.1f} deg)")

    violations = check_all_pairwise(positions)
    print("\n=== Kısıt kontrolleri ===")
    if violations:
        print("\n".join(violations))
        print(f"\n{len(violations)} ihlal -- YAZMA İPTAL.", file=sys.stderr)
        return 1
    print("  Tüm kısıtlar sağlanıyor (ihlal yok).")

    original = WORLD_FILE.read_text()
    try:
        new_text = render_shapes(original, body)
        new_text, payload_poses = render_payload_poses(new_text, spawn_x, spawn_y, spawn_yaw)
    except AreaGenerationError as e:
        print(f"HATA: {e}", file=sys.stderr)
        return 1

    # Kardes dunyalar: yalnizca payload pose'lari. Sekillere, isiga, hicbir
    # seye dokunulmaz. DEGISMEDIYSE YAZILMAZ -- her SITL acilisinda gereksiz
    # dosya yazmamak ve mtime kirletmemek icin.
    sibling_updates = {}
    for wf in PAYLOAD_WORLDS[1:]:
        if not wf.is_file():
            continue
        try:
            txt = wf.read_text()
            fixed, _ = render_payload_poses(txt, spawn_x, spawn_y, spawn_yaw)
        except AreaGenerationError as e:
            print(f"UYARI: {wf.name} payload pose'lari guncellenemedi: {e}", file=sys.stderr)
            continue
        sibling_updates[wf] = (fixed, fixed != txt)

    print("\n=== Payload pose'ları (spawn'a + yaw'a kilitli) ===")
    for name, dy in (("payload_red", PAYLOAD_RED_DY), ("payload_blue", PAYLOAD_BLUE_DY)):
        print(f"  {name:14s} <pose>{payload_poses[name]}</pose>"
              f"   (gövde ofseti: sol {dy:+.3f} m)")

    print("\n=== Kardeş dünyalar (yalnızca payload pose'ları) ===")
    if not sibling_updates:
        print("  (yok)")
    for wf, (_, changed) in sibling_updates.items():
        print(f"  {wf.name:28s} {'guncellenecek' if changed else 'zaten guncel'}")

    if args.dry_run:
        print("\n--dry-run: hiçbir dosyaya YAZMA yapılmadı.")
        return 0

    # Yedek ONCE yazilir: yazma ortasinda cokme olursa kurtarilabilir bir
    # kopya kalir. Ardindan BUDANIR -- bu script her SITL acilisinda
    # calisiyor, budama olmadan gunde 50-100 tane ~28 KB'lik, birbirinden
    # yalnizca dort koordinatta ayrilan dosya birikir ve yedek bir kurtarma
    # araci olmaktan cikar (operator hangisinin istedigi oldugunu ayirt
    # edemez).
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = WORLD_FILE.with_name(f"{WORLD_FILE.name}.bak.{timestamp}")
    backup.write_text(original)
    WORLD_FILE.write_text(new_text)

    olds = sorted(WORLD_FILE.parent.glob(f"{WORLD_FILE.name}.bak.*"))
    for stale in olds[:-BACKUP_KEEP]:
        try:
            stale.unlink()
        except OSError:
            pass          # budama bir kolaylik; basarisiz olmasi yazmayi bozmaz
    if len(olds) > BACKUP_KEEP:
        print(f"Eski yedekler budandi: {len(olds) - BACKUP_KEEP} silindi, "
              f"{BACKUP_KEEP} tutuldu")
    print(f"\nYedek: {backup.name}")
    print(f"default.sdf güncellendi: {WORLD_FILE}")

    for wf, (fixed, changed) in sibling_updates.items():
        if changed:
            wf.write_text(fixed)
            print(f"{wf.name} payload pose'ları güncellendi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
