#!/usr/bin/env python3
"""KURSAD40 -- iki-lane yarışma test ortamı üreticisi (default.sdf).

NEDEN VAR
---------
İki farklı yarışma lane'i aynı dünyada (default.sdf) test edilecek:

  Lane A (X merkez 0):  Mavi Altıgen (2m) + Kırmızı Üçgen (1m)
                        -- mevcut V33 Faz 1 tarama hedefleri, referans/kontrol.
  Lane B (X merkez 50): Lane A'nın aynısı + Kırmızı Kare (1m) + Mavi Kare (2m)
                        -- Görev 3'ün kare payload hedeflerini de aynı dünyada
                        uçtan uca test edebilmek için.

Her lane 30m (X) x 100m (Y). Y ekseni = Kuzey = drone'un ileri ekseni
(px4-gz bridge PX4'ün NED north_m'sini bu world'ün Y'sine eşliyor, X'e
değil -- default.sdf'teki blue_hexagon/red_triangle include'larının
2026-08-13 tarihli bug-fix yorumlarında ölçülüp kanıtlanmıştı).

BU KANITIN TAM METNİ (2026-08-29 migrasyonunda default.sdf'teki
blue_hexagon/red_triangle <include> bloklarından kaldırıldı -- bu
script onları HER ÇALIŞTIRMADA sildiği için orada kalıcı olamazdı;
bu docstring artık tek kalıcı yeri, orijinal İngilizce metniyle,
değiştirilmeden):

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

Kısa referans: default.sdf'in en üstünde (<world> açılışının hemen
altında, bu script'in hiç dokunmadığı bir yerde) bu docstring'e işaret
eden kalıcı bir not var.

Mavi Altıgen ile Kırmızı Üçgen arası mesafe HER ÇALIŞTIRMADA 20-25m
aralığında rastgele (annulus-sampling): önce Altıgen lane sınırları
içinde rastgele seçilir, sonra Üçgen, Altıgen'in etrafında yarıçapı
[20,25]m olan bir halka içinde -- yine lane sınırları içinde kalacak
şekilde -- rastgele seçilir (reject-sampling, MAX_ATTEMPTS'e kadar).

Lane B'nin Kırmızı Kare / Mavi Kare'si TAMAMEN bağımsız rastgele
konumlandırılır (X ve Y'de), tek kısıt: önceden yerleşmiş HER şekilden
en az MIN_SHAPE_SEPARATION_M uzakta olmaları (reject-sampling).

NASIL YAZAR (idempotent)
-------------------------
default.sdf'te iki XML yorum-bloğu sınırı kullanılır:

    <!-- KURSAD_LANE_A_START --> ... <!-- KURSAD_LANE_A_END -->
    <!-- KURSAD_LANE_B_START --> ... <!-- KURSAD_LANE_B_END -->

Bu script HER ÇALIŞTIĞINDA sadece bu iki blok arasındaki içeriği silip
yeniden yazar -- dosyanın geri kalanına (fizik, ışık, zemin, GPS home,
payload_red/payload_blue vb.) HİÇ dokunmaz.

İLK ÇALIŞTIRMA (marker'lar henüz yoksa): default.sdf'te zaten var olan,
marker'sız blue_hexagon/red_triangle <include> bloklarını (uri bazlı,
yorum metnine bağımlı olmayan bir regex ile) bulup bunları
KURSAD_LANE_A_START/END bloğuna dönüştürür (migrasyon); KURSAD_LANE_B
bloğu ise dosyada hiç yoksa </world> kapanışından hemen önce eklenir.

KULLANIM
--------
    python3 generate_test_lanes.py --seed 1 --dry-run
    python3 generate_test_lanes.py --seed 1

--dry-run: HİÇBİR dosyaya yazmaz. Üretilecek tüm koordinatları, ölçülen
Altıgen-Üçgen mesafesini ve tüm çift-mesafe kısıtlarının sağlandığını
stdout'a raporlar.

--seed: verilmezse zamana dayalı (her çalıştırmada farklı) rastgelelik;
verilirse deterministik (tekrarlanabilir) üretim.

Gerçek yazma (--dry-run OLMADAN) önce default.sdf'in zaman damgalı bir
yedeğini (`default.sdf.bak.<UTC-ISO>`) alır.
"""
import argparse
import datetime
import math
import random
import re
import sys
from pathlib import Path

WORLD_FILE = Path(__file__).parent / "default.sdf"

# --- Lane geometrisi ---------------------------------------------------
LANE_WIDTH_M = 30.0     # X ekseni
LANE_LENGTH_M = 100.0   # Y ekseni
EDGE_MARGIN_M = 3.0     # şekiller lane kenarlarından bu kadar içeride kalır

LANE_A_CENTER_X = 0.0
LANE_B_CENTER_X = 50.0

# --- Mesafe kısıtları ----------------------------------------------------
HEX_TRI_MIN_DIST_M = 20.0
HEX_TRI_MAX_DIST_M = 25.0
MIN_SHAPE_SEPARATION_M = 5.0   # Lane B karelerinin diğer TÜM şekillerden min mesafesi
MAX_SAMPLE_ATTEMPTS = 200

MARKER_A_START = "<!-- KURSAD_LANE_A_START -->"
MARKER_A_END = "<!-- KURSAD_LANE_A_END -->"
MARKER_B_START = "<!-- KURSAD_LANE_B_START -->"
MARKER_B_END = "<!-- KURSAD_LANE_B_END -->"

INDENT = "    "


class LaneGenerationError(RuntimeError):
    """Reject-sampling MAX_SAMPLE_ATTEMPTS içinde geçerli bir yerleşim
    bulamadığında yükselir -- sessizce yanlış/çakışan bir yerleşim
    üretmektense açıkça başarısız olmak tercih edilir."""


def _lane_x_bounds(center_x: float) -> tuple:
    half = LANE_WIDTH_M / 2.0 - EDGE_MARGIN_M
    return center_x - half, center_x + half


def _lane_y_bounds() -> tuple:
    return EDGE_MARGIN_M, LANE_LENGTH_M - EDGE_MARGIN_M


def _in_lane(x: float, y: float, center_x: float) -> bool:
    x_lo, x_hi = _lane_x_bounds(center_x)
    y_lo, y_hi = _lane_y_bounds()
    return x_lo <= x <= x_hi and y_lo <= y <= y_hi


def _random_point_in_lane(rng: random.Random, center_x: float) -> tuple:
    x_lo, x_hi = _lane_x_bounds(center_x)
    y_lo, y_hi = _lane_y_bounds()
    return rng.uniform(x_lo, x_hi), rng.uniform(y_lo, y_hi)


def sample_hex_and_triangle(rng: random.Random, center_x: float) -> tuple:
    """Altıgeni lane içinde rastgele seçer, Üçgeni Altıgen etrafında
    [HEX_TRI_MIN_DIST_M, HEX_TRI_MAX_DIST_M] yarıçaplı bir halka (annulus)
    içinde -- yine lane sınırları içinde kalacak şekilde -- rastgele seçer.
    Reject-sampling: MAX_SAMPLE_ATTEMPTS'e kadar dener."""
    for _ in range(MAX_SAMPLE_ATTEMPTS):
        hx, hy = _random_point_in_lane(rng, center_x)
        dist = rng.uniform(HEX_TRI_MIN_DIST_M, HEX_TRI_MAX_DIST_M)
        angle = rng.uniform(0.0, 2.0 * math.pi)
        tx = hx + dist * math.cos(angle)
        ty = hy + dist * math.sin(angle)
        if _in_lane(tx, ty, center_x):
            return (hx, hy), (tx, ty)
    raise LaneGenerationError(
        f"{MAX_SAMPLE_ATTEMPTS} denemede lane sınırları içinde "
        f"{HEX_TRI_MIN_DIST_M}-{HEX_TRI_MAX_DIST_M}m aralığında bir "
        f"Altıgen/Üçgen çifti bulunamadı (center_x={center_x}).")


def sample_point_far_from(rng: random.Random, center_x: float,
                          existing_points: list, min_sep: float = MIN_SHAPE_SEPARATION_M) -> tuple:
    """Lane içinde, `existing_points` listesindeki HER noktadan en az
    `min_sep` uzakta, tam bağımsız rastgele bir nokta seçer."""
    for _ in range(MAX_SAMPLE_ATTEMPTS):
        x, y = _random_point_in_lane(rng, center_x)
        if all(math.hypot(x - ex, y - ey) >= min_sep for ex, ey in existing_points):
            return x, y
    raise LaneGenerationError(
        f"{MAX_SAMPLE_ATTEMPTS} denemede min {min_sep}m ayrık bir nokta "
        f"bulunamadı (center_x={center_x}, {len(existing_points)} mevcut nokta).")


def _make_include(model_uri: str, instance_name: str, x: float, y: float) -> str:
    return (f"{INDENT}<include>\n"
            f"{INDENT}  <uri>model://{model_uri}</uri>\n"
            f"{INDENT}  <name>{instance_name}</name>\n"
            f"{INDENT}  <pose>{x:.3f} {y:.3f} 0.003 0 0 0</pose>\n"
            f"{INDENT}</include>")


def build_lane_a(rng: random.Random) -> tuple:
    (hx, hy), (tx, ty) = sample_hex_and_triangle(rng, LANE_A_CENTER_X)
    body = "\n\n".join([
        _make_include("blue_hexagon", "blue_hexagon", hx, hy),
        _make_include("red_triangle", "red_triangle", tx, ty),
    ])
    positions = {
        "blue_hexagon": (hx, hy),
        "red_triangle": (tx, ty),
    }
    hex_tri_dist = math.hypot(hx - tx, hy - ty)
    return body, positions, hex_tri_dist


def build_lane_b(rng: random.Random) -> tuple:
    (hx, hy), (tx, ty) = sample_hex_and_triangle(rng, LANE_B_CENTER_X)
    placed = [(hx, hy), (tx, ty)]
    rx, ry = sample_point_far_from(rng, LANE_B_CENTER_X, placed)
    placed.append((rx, ry))
    bx, by = sample_point_far_from(rng, LANE_B_CENTER_X, placed)
    placed.append((bx, by))

    body = "\n\n".join([
        _make_include("blue_hexagon", "blue_hexagon_b", hx, hy),
        _make_include("red_triangle", "red_triangle_b", tx, ty),
        _make_include("red_square", "red_square_b", rx, ry),
        _make_include("blue_square", "blue_square_b", bx, by),
    ])
    positions = {
        "blue_hexagon_b": (hx, hy),
        "red_triangle_b": (tx, ty),
        "red_square_b": (rx, ry),
        "blue_square_b": (bx, by),
    }
    hex_tri_dist = math.hypot(hx - tx, hy - ty)
    return body, positions, hex_tri_dist


def _wrap(start_marker: str, end_marker: str, body: str) -> str:
    return f"{INDENT}{start_marker}\n{body}\n{INDENT}{end_marker}"


# --- default.sdf'e idempotent yazma -------------------------------------

_LEGACY_INCLUDE_RE = re.compile(r"<include>.*?</include>", re.DOTALL)


def _find_marker_block_span(text: str, start_marker: str, end_marker: str):
    """(start_idx, end_idx) döner -- start_marker'ın başlangıcından
    end_marker'ın bitişine kadar (dahil). Yoksa None."""
    start_idx = text.find(start_marker)
    if start_idx == -1:
        return None
    end_idx = text.find(end_marker, start_idx)
    if end_idx == -1:
        raise LaneGenerationError(
            f"{start_marker} bulundu ama {end_marker} bulunamadı -- "
            f"default.sdf bozuk/elle kısmi düzenlenmiş olabilir.")
    return start_idx, end_idx + len(end_marker)


def _find_legacy_lane_a_span(text: str):
    """Marker'sız ilk-çalıştırma durumu: mevcut blue_hexagon ve
    red_triangle <include> bloklarının ikisini birden kapsayan span'ı
    (aralarındaki yorum/whitespace dahil) bulur. Sıraya bağımlı değildir."""
    spans = []
    for m in _LEGACY_INCLUDE_RE.finditer(text):
        block = m.group(0)
        if "model://blue_hexagon" in block or "model://red_triangle" in block:
            spans.append((m.start(), m.end()))
    if not spans:
        return None
    if len(spans) != 2:
        raise LaneGenerationError(
            f"Lane A migrasyonu: blue_hexagon/red_triangle icin 2 <include> "
            f"bekleniyordu, {len(spans)} bulundu -- elle inceleyin.")
    return min(s[0] for s in spans), max(s[1] for s in spans)


def render_world_text(original_text: str, lane_a_body: str, lane_b_body: str) -> str:
    text = original_text
    lane_a_block = _wrap(MARKER_A_START, MARKER_A_END, lane_a_body)
    lane_b_block = _wrap(MARKER_B_START, MARKER_B_END, lane_b_body)

    span_a = _find_marker_block_span(text, MARKER_A_START, MARKER_A_END)
    if span_a is not None:
        text = text[:span_a[0]] + lane_a_block + text[span_a[1]:]
    else:
        legacy_span = _find_legacy_lane_a_span(text)
        if legacy_span is None:
            raise LaneGenerationError(
                "Ne KURSAD_LANE_A marker'ı ne de eski blue_hexagon/"
                "red_triangle include'ları bulundu -- default.sdf beklenenden "
                "farklı yapıda, elle inceleyin.")
        text = text[:legacy_span[0]] + lane_a_block + text[legacy_span[1]:]

    span_b = _find_marker_block_span(text, MARKER_B_START, MARKER_B_END)
    if span_b is not None:
        text = text[:span_b[0]] + lane_b_block + text[span_b[1]:]
    else:
        world_close_idx = text.rfind("</world>")
        if world_close_idx == -1:
            raise LaneGenerationError("</world> kapanışı bulunamadı.")
        text = (text[:world_close_idx] + lane_b_block + "\n\n"
                + text[world_close_idx:])

    return text


def _check_all_pairwise(positions: dict, hex_tri_pairs: list) -> list:
    """Tüm çiftler arası mesafeyi kontrol eder, ihlalleri döner (boşsa temiz)."""
    violations = []
    names = list(positions.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            n1, n2 = names[i], names[j]
            p1, p2 = positions[n1], positions[n2]
            dist = math.hypot(p1[0] - p2[0], p1[1] - p2[1])
            is_hex_tri_pair = {n1, n2} in [set(pair) for pair in hex_tri_pairs]
            if is_hex_tri_pair:
                if not (HEX_TRI_MIN_DIST_M - 1e-6 <= dist <= HEX_TRI_MAX_DIST_M + 1e-6):
                    violations.append(
                        f"  ! {n1} <-> {n2}: {dist:.3f}m (beklenen "
                        f"[{HEX_TRI_MIN_DIST_M},{HEX_TRI_MAX_DIST_M}]m)")
            elif dist < MIN_SHAPE_SEPARATION_M - 1e-6:
                violations.append(
                    f"  ! {n1} <-> {n2}: {dist:.3f}m (min {MIN_SHAPE_SEPARATION_M}m ihlali)")
    return violations


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=None,
                       help="Deterministik üretim için rastgelelik tohumu. "
                            "Verilmezse her çalıştırma farklı sonuç üretir.")
    parser.add_argument("--dry-run", action="store_true",
                       help="Hiçbir dosyaya yazmaz; üretilecek koordinatları "
                            "ve mesafe kontrollerini stdout'a raporlar.")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    lane_a_body, lane_a_positions, lane_a_hex_tri_dist = build_lane_a(rng)
    lane_b_body, lane_b_positions, lane_b_hex_tri_dist = build_lane_b(rng)

    all_positions = {}
    all_positions.update(lane_a_positions)
    all_positions.update(lane_b_positions)

    print(f"=== Lane A (X merkez={LANE_A_CENTER_X}) ===")
    for name, (x, y) in lane_a_positions.items():
        print(f"  {name:20s} x={x:8.3f}  y={y:8.3f}")
    print(f"  Altıgen<->Üçgen mesafe: {lane_a_hex_tri_dist:.3f} m "
          f"(beklenen [{HEX_TRI_MIN_DIST_M},{HEX_TRI_MAX_DIST_M}]m)")

    print(f"\n=== Lane B (X merkez={LANE_B_CENTER_X}) ===")
    for name, (x, y) in lane_b_positions.items():
        print(f"  {name:20s} x={x:8.3f}  y={y:8.3f}")
    print(f"  Altıgen<->Üçgen mesafe: {lane_b_hex_tri_dist:.3f} m "
          f"(beklenen [{HEX_TRI_MIN_DIST_M},{HEX_TRI_MAX_DIST_M}]m)")

    hex_tri_pairs = [
        {"blue_hexagon", "red_triangle"},
        {"blue_hexagon_b", "red_triangle_b"},
    ]
    violations = _check_all_pairwise(all_positions, hex_tri_pairs)
    print("\n=== Tüm çift-mesafe kısıtları ===")
    if violations:
        print("\n".join(violations))
        print(f"\n{len(violations)} ihlal bulundu -- YAZMA İPTAL.")
        sys.exit(1)
    else:
        print("  Tüm çiftler kısıtları sağlıyor (ihlal yok).")

    if args.dry_run:
        print("\n--dry-run: default.sdf'e HİÇBİR YAZMA yapılmadı.")
        return

    original_text = WORLD_FILE.read_text()
    new_text = render_world_text(original_text, lane_a_body, lane_b_body)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = WORLD_FILE.with_name(f"{WORLD_FILE.name}.bak.{timestamp}")
    backup_path.write_text(original_text)
    print(f"\nYedek yazıldı: {backup_path}")

    WORLD_FILE.write_text(new_text)
    print(f"default.sdf güncellendi: {WORLD_FILE}")


if __name__ == "__main__":
    main()
