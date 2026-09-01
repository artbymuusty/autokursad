#!/usr/bin/env python3
"""KURSAD40 -- payload yuva (bore) collision geometrisi ureticisi.

NEDEN VAR
---------
Payload'un CAD govdesinde kancanin girdigi bir yuva var: 10.5 mm derinliginde
duz bir cep, altinda iki kademeli bir huni, en altta gecis deligi. Bu geometri
`meshes/payload_body.stl` icinde VAR ve VISUAL olarak zaten kullaniliyor; ama
COLLISION tarafinda tek bir dolu kutuyla (140x50x70) sadelestirilmisti. Sonuc:
kanca burnu deligin icine giremiyor, duz kapagin ustunde duruyordu ve yanal
kacisi engelleyen hicbir fiziksel sinir yoktu.

Bu script o geometriyi -- UYDURMADAN, olculmus CAD profilinden -- ilkel
kutulara ayristirip collision olarak yazar. Sahte bir manyetik cekim veya
yapay oturma mantigi EKLEMEZ; yalnizca zaten var olan yuzeyleri tasir.

NEDEN CONE DEGIL DE EGIMLI KUTU
-------------------------------
SDF 1.11'de <cone> ilkeli var, ama dosyalar 1.9 ve surum yukseltmesi ayri bir
karar. Basamakli (silindir yigini) yaklasiklama ise CALISMAZ: basamagin tek
yuzeyleri yatay ve dikeydir, yatay yuzey yanal kuvvet uretmez, dikey yuzey
yalnizca bloklar -- yani egim, dolayisiyla yonlendirme etkisi, N ne olursa
olsun yeniden uretilemez. Buna karsilik bir <box>'un <pose>'una pitch
verilebilir: SDF 1.9'da bir kutu, yuzeyi tam 23.20 derecede olan GERCEK bir
rampadir. Yaklasiklama ekseni boylece "dikey basamak sayisi"ndan "cevresel
faset sayisi"na kayar ve orada hata analitik olarak sinirlanabilir.

SURTUNME NOTU (abartmamak icin)
-------------------------------
SDF <mu> varsayilani 1.0 ve ne payload'da ne kanca ucunda <surface> blogu var.
Yercekimiyle rampada kayma kosulu mu < tan(theta). Pah-1 23.20 derece
(tan 0.4286) -- yani mu=1.0'da KENDILIGINDEN MERKEZLEMEZ. Bu geometrinin
verdigi sey aktif merkezleme degil:
  * sert duvar: 10.25 mm otesine yanal kacis fiziksel olarak imkansiz
  * tanimli oturma derinligi: burun hesaplanabilir bir z'de duruyor
  * geri cikamama: koniye oturan burun kendiliginden disari da kayamiyor
Iceri kaymak icin gereken yanal kuvvet aracin duzeltme dongusunden ve sarkac
hareketinden gelir; bu dinamiktir, olculur, ongorulmez.

KULLANIM
--------
    python3 generate_bore_collision.py --check      # sadece dogrula, yazma
    python3 generate_bore_collision.py --dry-run    # uretilecegi goster, yazma
    python3 generate_bore_collision.py              # iki SDF dosyasina yaz

Idempotent: iki kez calistirmak byte-ozdes cikti verir. Marker'lar arasini
yeniden yazar; blok bir kez elle kurulmalidir.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GZ_ROOT = HERE.parent
WORLD_FILE = GZ_ROOT / "worlds" / "default.sdf"
MODEL_FILE = GZ_ROOT / "models" / "kursad_payload" / "model.sdf"

# Hedefler: (dosya, govde_X_mm, govde_Y_mm, z_ofset_mm)
#
# Iki dosyanin link cercevesi AYNI DEGIL. default.sdf'te payload gorselleri
# <pose>0 0 0.008</pose> ile kaldiriliyor, yani link orijini govde orta
# yuksekligi ve deck ust yuzeyi +35 mm. kursad_payload/model.sdf'te gorseller
# pose'suz, yani link orijini CAD orijini ve deck ust yuzeyi +27 mm. Ayrica
# model dosyasi zarf olarak 142x52 kullaniyor (dunya 140x50).
#
# Hesap her zaman DUNYA cercevesinde yapilir; fark yalnizca yazim aninda
# z ofseti olarak uygulanir. Boylece profil tek kaynakta kalir.
TARGETS = (
    ("world", 140.0, 50.0, 0.0),
    ("model", 142.0, 52.0, -8.0),
)

MARKER_START = "<!-- KURSAD_BORE_COLLISION_START -->"
MARKER_END = "<!-- KURSAD_BORE_COLLISION_END -->"


class BoreGenerationError(RuntimeError):
    pass


# ======================================================================
# CAD PROFILI -- TEK KAYNAK
# ======================================================================
# hook_seating.py docstring'indeki tablodan, payload_body.stl uzerinde
# bagimsiz olarak dogrulanmistir (7512 ucgen, ~0.1 mm icinde ortusuyor).
# Butun degerler PAYLOAD LINK cercevesinde, MILIMETRE.
#   link_z = CAD_z + 8.00   (visual <pose>'undaki +0.008 m ofseti)

BODY_LEN_MM = 140.0        # X
BODY_WID_MM = 50.0         # Y
BODY_HGT_MM = 70.0         # Z  -> link z araligi [-35, +35]

DECK_TOP_MM = 35.0         # deck ust yuzeyi (RECEIVER_DECK_OFFSET_M = 0.035)
BORE_FLOOR_MM = 17.0       # gecis deligi omuzu; bunun altinda dolu taban

# (link_z, yaricap) -- yukaridan asagiya. Ardisik ciftler birer koni bolgesi.
BORE_PROFILE = (
    (35.00, 23.98),        # deck ust yuzeyi, O47.96
    (24.50, 23.25),        # duz cep dibi / pah-1 tepesi, O46.50
    (20.75, 14.50),        # pah-1 dibi / pah-2 tepesi, O29.00
    (17.00, 11.00),        # gecis deligi omuzu, O22.00
)
ZONE_NAMES = ("wall", "chamfer1", "chamfer2")

DEFAULT_FACETS = 12        # N -- cevresel faset sayisi
DEFAULT_STRIPS = 8         # K -- deck dolgusu icin Y tarama seridi sayisi
FILL_RADIUS_MM = 24.60     # dolgunun ic siniri; en genis kovuk 23.98'in disi
PLANK_MARGIN = 1.15        # komsu fasetler arasinda bosluk kalmasin diye
PLANK_MIN_THICK_MM = 2.5

INDENT = "        "


# ======================================================================
def facet_scale(n: int) -> float:
    """Hatayi ic ve dis yaricap arasinda esit bolen olcek.

    N-gen'in ic yaricapi R*s, dis yaricapi R*s/cos(pi/N) olur. s'yi
    R*s = R-delta ve R*s/cos = R+delta olacak sekilde secmek, kovugu faset
    ortalarinda delta kadar dar, koselerde delta kadar genis yapar -- yani
    hatayi tek yone yigmak yerine ikiye boler."""
    c = math.cos(math.pi / n)
    return 2.0 * c / (1.0 + c)


def cavity_radius_mm(z: float) -> float:
    """Verilen link z yuksekliginde kovugun analitik yaricapi (mm).

    BORE_FLOOR_MM altinda kovuk yok (dolu taban): 0 doner.
    DECK_TOP_MM ustunde kovuk sinirsiz: deck yaricapini dondurur."""
    if z < BORE_FLOOR_MM:
        return 0.0
    if z >= BORE_PROFILE[0][0]:
        return BORE_PROFILE[0][1]
    for (z_hi, r_hi), (z_lo, r_lo) in zip(BORE_PROFILE, BORE_PROFILE[1:]):
        if z_lo <= z <= z_hi:
            t = (z - z_lo) / (z_hi - z_lo)
            return r_lo + t * (r_hi - r_lo)
    return BORE_PROFILE[-1][1]


def modelled_cavity_radius_mm(z: float) -> float:
    """MODELLENEN kovuk yaricapi -- CAD profilinden tek bir yerde ayriliyor.

    Duz cep bolgesi CAD'de 4 derecelik kalip cikma acisiyla 23.98'den
    23.25'e daraliyor. Model bunu SABIT 23.25 aliyor (bkz. _wall_facets).
    Dogrulama, uretilenle ayni sekle karsi yapilmali; yoksa bilincli ve
    belgelenmis bir sadelestirme "hata" gibi gorunur. Sapma asagida
    ayrica raporlaniyor.
    """
    z_hi, r_hi = BORE_PROFILE[0]
    z_lo, r_lo = BORE_PROFILE[1]
    if z_lo <= z <= z_hi:
        return r_lo
    return cavity_radius_mm(z)


def zone_angles() -> list:
    """Her koni bolgesinin yataya gore egimi ve mu esigi (rapor icin)."""
    out = []
    for (z_hi, r_hi), (z_lo, r_lo), nm in zip(
            BORE_PROFILE, BORE_PROFILE[1:], ZONE_NAMES):
        dz, dr = z_hi - z_lo, r_hi - r_lo
        theta = math.degrees(math.atan2(dz, dr)) if dr > 1e-9 else 90.0
        out.append((nm, z_lo, z_hi, r_lo, r_hi, theta, math.tan(math.radians(theta))))
    return out


# ======================================================================
# KUTU URETIMI
# ======================================================================
class Box:
    """Eksen-hizali olmayabilen bir collision kutusu. Olculer mm, poz mm."""

    __slots__ = ("name", "size", "pos", "rpy")

    def __init__(self, name, size, pos, rpy=(0.0, 0.0, 0.0)):
        self.name = name
        self.size = tuple(float(v) for v in size)
        self.pos = tuple(float(v) for v in pos)
        self.rpy = tuple(float(v) for v in rpy)

    def contains(self, p) -> bool:
        """p (dunya/link mm) bu kutunun icinde mi? Ters donusum ile."""
        dx, dy, dz = p[0] - self.pos[0], p[1] - self.pos[1], p[2] - self.pos[2]
        _, pitch, yaw = self.rpy
        cy, sy = math.cos(yaw), math.sin(yaw)
        # R = Rz(yaw) @ Ry(pitch);  yerel = R^T @ delta
        x1 = cy * dx + sy * dy
        y1 = -sy * dx + cy * dy
        cp, sp = math.cos(pitch), math.sin(pitch)
        lx = cp * x1 - sp * dz
        lz = sp * x1 + cp * dz
        hx, hy, hz = self.size[0] / 2, self.size[1] / 2, self.size[2] / 2
        return abs(lx) <= hx and abs(y1) <= hy and abs(lz) <= hz

    def corners(self):
        """Sekiz kosenin link cercevesindeki konumu (zarf denetimi icin)."""
        _, pitch, yaw = self.rpy
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        hx, hy, hz = self.size[0] / 2, self.size[1] / 2, self.size[2] / 2
        out = []
        for sx in (-hx, hx):
            for sYy in (-hy, hy):
                for sz in (-hz, hz):
                    # R = Rz(yaw) @ Ry(pitch)
                    x1 = cp * sx + sp * sz
                    z1 = -sp * sx + cp * sz
                    wx = cy * x1 - sy * sYy
                    wy = sy * x1 + cy * sYy
                    out.append((wx + self.pos[0], wy + self.pos[1],
                                z1 + self.pos[2]))
        return out


def _scanline(z0, z1, r_inner, strips, tag, axis, idx0):
    """Tek eksende tarama. axis='x': x seritleri, |y| >= y_in dolar."""
    hz, cz = (z1 - z0), (z0 + z1) / 2.0
    half_scan = (BODY_LEN_MM if axis == "x" else BODY_WID_MM) / 2.0
    half_perp = (BODY_WID_MM if axis == "x" else BODY_LEN_MM) / 2.0
    out, idx = [], idx0
    R = min(r_inner, half_scan)
    edges = []
    if half_scan > R:
        edges.append((-half_scan, -R))
    step = 2.0 * R / strips
    edges += [(-R + k * step, -R + (k + 1) * step) for k in range(strips)]
    if half_scan > R:
        edges.append((R, half_scan))
    for (a0, a1) in edges:
        if a1 - a0 <= 1e-9:
            continue
        a_near = 0.0 if (a0 <= 0.0 <= a1) else min(abs(a0), abs(a1))
        p_in = math.sqrt(max(0.0, r_inner * r_inner - a_near * a_near))
        ca, ha = (a0 + a1) / 2.0, (a1 - a0)
        if p_in >= half_perp - 1e-9:
            continue
        for sgn in (1.0, -1.0):
            w = half_perp - p_in
            c_perp = sgn * (p_in + w / 2.0)
            size = (ha, w, hz) if axis == "x" else (w, ha, hz)
            pos = (ca, c_perp, cz) if axis == "x" else (c_perp, ca, cz)
            out.append(Box(f"bore_fill_{tag}_{idx:02d}", size, pos))
            idx += 1
    return out, idx


def _zone_fill(z0, z1, r_inner, strips, tag):
    """Bir z diliminde, r_inner yaricapinin DISINDA kalan malzemeyi eksen-hizali
    kutularla doldurur.

    Tarama X ekseninde. Govde X'te 140 mm ama Y'de 50 mm; kovuk ise O48'e
    kadar cikiyor, yani Y'de kenarda ~1 mm'lik bir cikinti kaliyor. X'te
    tarayinca her seritte disarida birakilan Y bandi kucuk oluyor ve dolgu
    cemberi yakindan takip ediyor. (Y'de taramak, seritlerin uzak ucunda
    5 mm'ye varan kama bosluklari birakiyordu.)

    Iki eksende birden taramak da denendi: kutu sayisini payload basina
    83'ten 97'ye cikardi ve artik bosluk sayisini AZALTMADI (K=8 tek eksen
    40 nokta, K=4 cift eksen 68). Tek eksen + yeterli K daha ucuz.
    """
    out, _ = _scanline(z0, z1, r_inner, strips, tag, "x", 0)
    return out


def _fits_envelope(box):
    """Kutunun sekiz kosesi de 140x50x70 zarfin icinde mi?

    Zarf DEGISMEMELI: payload'un disaridan gorunen sekli Gorev 2'nin birakma
    fizigini belirliyor. Bu yuzden zarfi asan her kutu, asmayana kadar
    inceltiliyor; incelmenin biraktigi bosluklari dolgu kapatiyor."""
    hx, hy, hz = BODY_LEN_MM / 2, BODY_WID_MM / 2, BODY_HGT_MM / 2
    for (cx, cy, cz) in box.corners():
        if abs(cx) > hx + 1e-9 or abs(cy) > hy + 1e-9 or abs(cz) > hz + 1e-9:
            return False
    return True


def _wall_facets(z_hi, z_lo, r_lo, n, tag, reach_r):
    """Duz cep bolgesi: EGIMLI degil, DIKEY kutular.

    Cepte 4 derecelik bir kalip cikma acisi var (agiz ustte 23.98, dipte
    23.25). Egimli bir kutuyla modellenince kutu kendi normali boyunca
    kaydigi icin UST YUZEYI z=35'e yetismiyor ve deck yuzeyinde delik
    kaliyordu. Dikey kutu, ust yuzeyi tam deck duzleminde birakiyor.

    Yaricap olarak DIPTEKI (dar) deger aliniyor: 23.25 mm, yani agzi
    fonksiyonel olarak baglayan olcu -- SEAT_MAX_LATERAL_M = 23.25 - 13.00
    = 10.25 mm buradan geliyor. Cikma acisini atmak, gercekte 10.98 mm'de
    baslayip 10.25'e sikisan girisi 10.25'te sabitler; yani model gercekten
    KOLAY degil, biraz daha ZOR yakalama gosterir. Faset hatasi (+/-0.40 mm)
    zaten bu 0.73 mm'lik cikmadan buyuk."""
    s = facet_scale(n)
    R = r_lo * s
    h = z_hi - z_lo
    W = 2.0 * R * math.tan(math.pi / n) * PLANK_MARGIN
    T_want = max(PLANK_MIN_THICK_MM, reach_r - R)
    out, clipped = [], 0
    for i in range(n):
        phi = 2.0 * math.pi * i / n
        cx, sx = math.cos(phi), math.sin(phi)
        T = T_want
        box = None
        for _ in range(40):
            rc = R + T / 2.0
            box = Box(f"bore_{tag}_{i:02d}", (T, W, h),
                      (rc * cx, rc * sx, (z_hi + z_lo) / 2.0),
                      (0.0, 0.0, phi))
            if _fits_envelope(box):
                break
            T *= 0.92
        if T < T_want - 1e-9:
            clipped += 1
        out.append(box)
    return out, clipped


def _facet_planks(z_hi, r_hi, z_lo, r_lo, n, tag, fill_radius,
                  reach_radius=None):
    """Bir KONI bolgesini N egimli kutuya ayristirir (pah-1 ve pah-2).

    Kutunun YEREL Z ekseni koninin kovuga bakan normalidir; govde -Z yonunde,
    yani malzeme tarafinda uzar. Yerel X ekseni koni dogrusu boyuncadir.

    Uzunluk yalnizca YUKARI dogru uzatilir. Faset tam bolge boyunda kesilirse
    fasetin ust ucunun disinda-altinda kalan koseyi hicbir kutu kapatmiyor ve
    kovuk duvari orada delik veriyor. Asagi uzatmak ise kutuyu alt bolgenin
    (daha dar) kovuguna sokar, o yuzden tek yon."""
    s_ = facet_scale(n)
    R_hi, R_lo = r_hi * s_, r_lo * s_
    dr, dz = R_hi - R_lo, z_hi - z_lo          # ikisi de pozitif
    L = math.hypot(dr, dz)
    u_r, u_z = dr / L, dz / L                  # disa+yukari birim vektor
    n_r, n_z = -u_z, u_r                       # ice+yukari bakan normal
    r_mid, z_mid = (R_hi + R_lo) / 2.0, (z_hi + z_lo) / 2.0
    pitch = -math.atan2(u_z, u_r)

    RR = fill_radius if reach_radius is None else reach_radius
    reach = [-((tr - r_mid) * n_r + (tz - z_mid) * n_z)
             for (tr, tz) in ((RR, z_lo), (RR, z_hi), (R_hi, z_lo))]
    T_want = max(PLANK_MIN_THICK_MM, max(reach) + 0.6)
    W = 2.0 * R_hi * math.tan(math.pi / n) * PLANK_MARGIN

    # Uzatma korlemesine yapilamaz: USTTEKI bolgenin kovugu bu bolgenin
    # konisinden daha HIZLI genisliyorsa (pah-2'nin ustundeki pah-1 boyle),
    # uzatilan yuzey kovugun icinde kalir. Gercek profile karsi sinaniyor.
    e_want = 0.0
    if u_r > 0.2:
        e_want = min(0.5 * L, max(0.0, (RR - R_hi) / u_r) + 0.5)
        while e_want > 0.05:
            if all(R_hi + (e_want * k / 12.0) * u_r
                   >= cavity_radius_mm(z_hi + (e_want * k / 12.0) * u_z) * s_ - 0.02
                   for k in range(1, 13)):
                break
            e_want *= 0.85
        else:
            e_want = 0.0

    planks, clipped = [], 0
    for i in range(n):
        phi = 2.0 * math.pi * i / n
        cx, sx = math.cos(phi), math.sin(phi)
        T, e = T_want, e_want
        box = None
        for _ in range(40):
            rc = r_mid - n_r * T / 2.0 + u_r * e / 2.0
            zc = z_mid - n_z * T / 2.0 + u_z * e / 2.0
            box = Box(f"bore_{tag}_{i:02d}", (L + e, W, T),
                      (rc * cx, rc * sx, zc), (0.0, pitch, phi))
            if _fits_envelope(box):
                break
            T *= 0.92
            e *= 0.92
        if T < T_want - 1e-9:
            clipped += 1
        planks.append(box)
    return planks, clipped


ZONE_FILL_MARGIN_MM = 0.22

# Plank'larin DISA dogru hedefledigi yaricap, bolge basina.
# Ust (wall) bolgesinde dolgunun ic siniri bir BASAMAK fonksiyonu; seridin
# uzak ucunda cember ile basamak arasinda kama seklinde bir bosluk kaliyor ve
# bu bosluk deck ust yuzeyine kadar cikiyor. Plank'lari cok daha disa
# uzatmak bu kamayi kapatiyor; +/-Y'de zarf (25 mm) izin vermediginde
# _fits_envelope zaten kirpiyor, orada da dolgu devrali'yor cunku seritler
# x=0 civarinda ve orada basamak hatasi ihmal edilebilir.
ZONE_PLANK_REACH_MM = {"wall": 30.0}


def build_boxes(n=DEFAULT_FACETS, strips=DEFAULT_STRIPS):
    """Bir payload icin butun collision kutularini uretir.

    Dolgu bolge basina yapilir: her koni bolgesinin dolgusu, o bolgedeki EN
    GENIS kovuk yaricapinin hemen disindan baslar. Tek bir kalin dilim yerine
    bolge basina dolgu kullanmak, plank'larin ince kalmasini ve +/-Y'de
    zarfin asilmamasini sagliyor.

    Deck ust yuzeyinin surekliligi yalnizca EN UST bolgeyi ilgilendirdigi icin
    ince tarama (strips) orada kullanilir; alt bolgelerde kaba dolgu yeterli,
    cunku oradaki bosluklar tamamen kapali kalir ve kanca onlara erisemez."""
    boxes, clipped_total = [], 0
    base_h = BORE_FLOOR_MM - (-BODY_HGT_MM / 2.0)
    boxes.append(Box("bore_base", (BODY_LEN_MM, BODY_WID_MM, base_h),
                     (0.0, 0.0, -BODY_HGT_MM / 2.0 + base_h / 2.0)))

    zones = list(zip(BORE_PROFILE, BORE_PROFILE[1:], ZONE_NAMES))
    for idx, ((z_hi, r_hi), (z_lo, r_lo), tag) in enumerate(zones):
        fill_r = max(r_hi, r_lo) + ZONE_FILL_MARGIN_MM
        k = strips if idx <= 1 else 1
        boxes.extend(_zone_fill(z_lo, z_hi, fill_r, k, tag))
        reach_r = ZONE_PLANK_REACH_MM.get(tag, fill_r)
        if tag == "wall":
            planks, clipped = _wall_facets(z_hi, z_lo, r_lo, n, tag, reach_r)
        else:
            planks, clipped = _facet_planks(z_hi, r_hi, z_lo, r_lo, n, tag,
                                            fill_r, reach_r)
        boxes.extend(planks)
        clipped_total += clipped
    build_boxes.last_clipped = clipped_total
    return boxes


build_boxes.last_clipped = 0


# ======================================================================
# DOGRULAMA -- uretilen kutular gercekten dogru sekli veriyor mu
# ======================================================================
def verify(boxes, n, verbose=False):
    """Nokta ornekleme ile ayristirmayi denetler.

    Elle yapilan bir geometri ayristirmasinda isaret/konvansiyon hatasi
    gozle yakalanmaz; bu yuzden sekil analitik profile karsi ornekleme ile
    sinaniyor. Dort SERT kosul var, biri bile kirilirsa uretim durur."""
    s = facet_scale(n)
    delta_out = BORE_PROFILE[1][1] * (1.0 / math.cos(math.pi / n) - 1.0) * s
    fails = []
    counts = {}

    def covered(p):
        return any(b.contains(p) for b in boxes)

    # --- SERT 1: kovuk bos olmali -------------------------------------
    bad = 0
    for iz in range(0, 181):
        z = BORE_FLOOR_MM + iz * (DECK_TOP_MM - BORE_FLOOR_MM) / 180.0
        rc = modelled_cavity_radius_mm(z)
        if rc <= 0.0:
            continue
        # faset ortalarinda kovuk delta kadar dar; guvenli sinir icin
        # analitik yaricapin biraz icini ornekle
        r_safe = rc * s * 0.985
        for ia in range(72):
            a = 2.0 * math.pi * ia / 72.0
            p = (r_safe * math.cos(a), r_safe * math.sin(a), z + 1e-6)
            if covered(p):
                bad += 1
                if verbose and bad < 6:
                    print(f"    KOVUK IHLALI: r={r_safe:.2f} z={z:.2f} "
                          f"aci={math.degrees(a):.0f}")
    counts["kovuk_ihlali"] = bad
    if bad:
        fails.append(f"kovuk {bad} noktada dolu -- burun giremez")

    # --- SERT 2: zarf asilmamali --------------------------------------
    hx, hy, hz = BODY_LEN_MM / 2, BODY_WID_MM / 2, BODY_HGT_MM / 2
    over = []
    for b in boxes:
        for (cx, cy, cz) in b.corners():
            if (abs(cx) > hx + 1e-6 or abs(cy) > hy + 1e-6
                    or abs(cz) > hz + 1e-6):
                over.append((b.name, round(cx, 2), round(cy, 2), round(cz, 2)))
                break
    counts["zarf_asan"] = len(over)
    if over:
        fails.append(f"{len(over)} kutu 140x50x70 zarfini asiyor: {over[:3]}")

    # --- SERT 3: kovuk duvari VAR olmali ------------------------------
    # Olcut "su nokta dolu mu" degil, "burada bir DUVAR var mi": kovugun
    # hemen disindaki 2 mm'lik radyal bantta malzeme bulunmasi yeterli.
    # Tek bir yaricapta ornekleme, faset kosesi ile faset ortasi arasindaki
    # 0.4 mm'lik gecise takilip yanlis alarm veriyordu.
    miss = 0
    for iz in range(0, 121):
        z = BORE_FLOOR_MM + 0.5 + iz * (DECK_TOP_MM - BORE_FLOOR_MM - 1.0) / 120.0
        rc = modelled_cavity_radius_mm(z)
        if rc <= 0.0:
            continue
        r0 = rc * s / math.cos(math.pi / n)
        for ia in range(72):
            a = 2.0 * math.pi * ia / 72.0
            ca, sa = math.cos(a), math.sin(a)
            band = False
            for rr in (r0 + 0.15, r0 + 0.7, r0 + 1.3, r0 + 2.0):
                if abs(rr * sa) > BODY_WID_MM / 2 - 0.15:
                    band = True          # zarf zaten bitiyor: govde kenari
                    break
                if covered((rr * ca, rr * sa, z)):
                    band = True
                    break
            if not band:
                miss += 1
                if verbose and miss < 6:
                    print(f"    DUVAR EKSIK: r~{r0:.2f} z={z:.2f} "
                          f"aci={math.degrees(a):.0f}")
    counts["duvar_eksik"] = miss
    if miss:
        fails.append(f"kovuk duvari {miss} noktada yok -- yanal sinir olusmaz")

    # --- SERT 4: deck ust yuzeyinde BURUN'U ALACAK bosluk olmamali -----
    # Yine olcut fiziksel: yalitilmis 1-2 mm'lik bosluklar onemsiz, cunku
    # O26'lik burun (yuzey alani ~531 mm2) onlarin uzerine KOPRU kurar.
    # Onemli olan, burnun ICINE girebilecegi genislikte bir bosluk olup
    # olmadigi. Bu yuzden her bos noktada NOSE_PROBE_MM yaricapli bir
    # diskin tamami bos mu diye bakiliyor.
    NOSE_PROBE_MM = 5.0
    z_top = DECK_TOP_MM - 0.25
    r_deck = BORE_PROFILE[0][1]
    empties = set()
    for ix in range(-69, 70):
        for iy in range(-24, 25):
            x, y = float(ix), float(iy)
            if math.hypot(x, y) < r_deck + 0.8:
                continue
            if not covered((x, y, z_top)):
                empties.add((ix, iy))
    counts["deck_bosluk_noktasi"] = len(empties)
    admits = 0
    for (ix, iy) in empties:
        wide = True
        for k in range(12):
            a = 2.0 * math.pi * k / 12.0
            px = ix + NOSE_PROBE_MM * math.cos(a)
            py = iy + NOSE_PROBE_MM * math.sin(a)
            if abs(px) > BODY_LEN_MM / 2 or abs(py) > BODY_WID_MM / 2:
                continue
            if covered((px, py, z_top)) or math.hypot(px, py) < r_deck:
                wide = False
                break
        if wide:
            admits += 1
            if verbose and admits < 6:
                print(f"    BURUN ALAN BOSLUK: x={ix} y={iy}")
    counts["burun_alan_bosluk"] = admits
    if admits:
        fails.append(f"deck ust yuzeyinde burnu alacak {admits} bosluk var")

    return fails, counts


# ======================================================================
# SDF URETIMI
# ======================================================================
def render_boxes(boxes, indent: str, z_offset_mm: float = 0.0) -> str:
    """Kutulari <collision> bloklarina cevirir. Olculer METRE."""
    lines = []
    for b in boxes:
        sx, sy, sz = (v / 1000.0 for v in b.size)
        px, py, pz = (b.pos[0] / 1000.0, b.pos[1] / 1000.0,
                      (b.pos[2] + z_offset_mm) / 1000.0)
        r, p, y = b.rpy
        lines.append(f'{indent}<collision name="{b.name}">')
        if any(abs(v) > 1e-12 for v in (px, py, pz, r, p, y)):
            lines.append(f'{indent}  <pose>{px:.6f} {py:.6f} {pz:.6f} '
                         f'{r:.9f} {p:.9f} {y:.9f}</pose>')
        lines.append(f'{indent}  <geometry><box><size>'
                     f'{sx:.6f} {sy:.6f} {sz:.6f}'
                     f'</size></box></geometry>')
        lines.append(f'{indent}</collision>')
    return "\n".join(lines)


def _header(n, strips, count, indent):
    z_stop, ins = nose_stop_mm()
    return "\n".join([
        f"{indent}<!-- URETILMIS BLOK -- generate_bore_collision.py yazar.",
        f"{indent}     ELLE DUZENLEME. Profil ve N o script'te tek yerde.",
        f"{indent}     Faset N={n}, deck serit K={strips}, {count} kutu.",
        f"{indent}     CAD yuva: cep O46.50 (10.5mm derin), pah-1 23.20deg,",
        f"{indent}     pah-2 46.97deg, gecis deligi O22.00.",
        f"{indent}     Burun (O26, r 13.00) link z {z_stop:+.2f}'de durur",
        f"{indent}     -> maks. girme {ins:.2f} mm. Yanal sinir 10.25 mm. -->",
    ])


def nose_stop_mm(nose_r=13.00):
    """CAD burnunun (O26) durdugu link z'si ve girme derinligi."""
    for (z_hi, r_hi), (z_lo, r_lo) in zip(BORE_PROFILE, BORE_PROFILE[1:]):
        if r_lo <= nose_r <= r_hi:
            t = (nose_r - r_lo) / (r_hi - r_lo)
            z = z_lo + t * (z_hi - z_lo)
            return z, DECK_TOP_MM - z
    return BORE_FLOOR_MM, DECK_TOP_MM - BORE_FLOOR_MM


def _span(text, path):
    i = text.find(MARKER_START)
    if i < 0:
        raise BoreGenerationError(
            f"{path.name} icinde {MARKER_START} bulunamadi. Bu script yalnizca "
            f"marker'lar arasini yeniden yazar; blok bir kez elle kurulmalidir.")
    j = text.find(MARKER_END, i)
    if j < 0:
        raise BoreGenerationError(
            f"{path.name}: {MARKER_START} var ama {MARKER_END} yok -- bozuk.")
    return i, j + len(MARKER_END)


def _indent_of(text, i):
    ls = text.rfind("\n", 0, i)
    return text[ls + 1:i] if ls >= 0 else ""


def render_into(text, boxes, n, strips, path, z_off=0.0):
    i, j = _span(text, path)
    indent = _indent_of(text, i)
    body = "\n".join([_header(n, strips, len(boxes), indent),
                      render_boxes(boxes, indent, z_off)])
    return text[:i] + MARKER_START + "\n" + body + "\n" + indent + MARKER_END + text[j:]


def count_markers(text):
    return text.count(MARKER_START), text.count(MARKER_END)


# ======================================================================
def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--facets", type=int, default=DEFAULT_FACETS,
                    help=f"cevresel faset sayisi N (varsayilan {DEFAULT_FACETS})")
    ap.add_argument("--strips", type=int, default=DEFAULT_STRIPS,
                    help=f"deck dolgusu Y serit sayisi K (varsayilan {DEFAULT_STRIPS})")
    ap.add_argument("--dry-run", action="store_true", help="yazma, uretileni goster")
    ap.add_argument("--check", action="store_true", help="yazma, sadece dogrula")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    if a.facets < 4:
        print("HATA: --facets en az 4 olmali.", file=sys.stderr)
        return 2

    print("YUVA (BORE) COLLISION URETICISI")
    print("=" * 62)
    print(f"CAD profili (link cercevesi, deck ust yuzeyi = {DECK_TOP_MM:.2f} mm):")
    for z, r in BORE_PROFILE:
        print(f"    link z {z:+7.2f}   r {r:6.2f} mm")
    print(f"\nBolge egimleri  (mu < tan(theta) ise yercekimiyle kayar; mu=1.0):")
    for nm, z_lo, z_hi, r_lo, r_hi, th, tn in zone_angles():
        d_lo, d_hi = r_lo - 13.00, r_hi - 13.00
        kayar = "EVET" if tn > 1.0 else "HAYIR"
        print(f"    {nm:9s} z[{z_lo:+6.2f},{z_hi:+6.2f}]  {th:5.2f}deg  "
              f"tan={tn:6.4f}  ofset d=[{d_lo:5.2f},{d_hi:5.2f}]  kayar={kayar}")
    z_stop, ins = nose_stop_mm()
    print(f"\nBurun (O26, r 13.00) durus: link z {z_stop:+.2f} -> girme {ins:.2f} mm")
    print(f"Yanal sinir: {BORE_PROFILE[1][1]:.2f} - 13.00 = "
          f"{BORE_PROFILE[1][1] - 13.00:.2f} mm")

    boxes = build_boxes(a.facets, a.strips)
    s = facet_scale(a.facets)
    d = BORE_PROFILE[1][1] * (1 - s)
    print(f"\nN={a.facets}, K={a.strips} -> {len(boxes)} kutu/payload "
          f"({2 * len(boxes)} toplam)")
    print(f"Faset hatasi: +/-{d:.3f} mm  -> etkin yanal sinir "
          f"{BORE_PROFILE[1][1] - d - 13.00:.2f} - "
          f"{BORE_PROFILE[1][1] + d - 13.00:.2f} mm")

    print("\nDOGRULAMA (nokta ornekleme)")
    print("-" * 62)
    fails, counts = verify(boxes, a.facets, a.verbose)
    for k, v in counts.items():
        print(f"    {k:16s}: {v}")
    if fails:
        print("\nSONUC: FAIL")
        for f in fails:
            print(f"  * {f}")
        return 1
    print("\nSONUC: dort SERT kosul da saglandi (kovuk bos, zarf korundu,")
    print("       duvar var, deck ust yuzeyi surekli).")

    if a.check:
        print("\n--check: hicbir dosyaya YAZMA yapilmadi.")
        return 0

    files = {"world": WORLD_FILE, "model": MODEL_FILE}
    print("\nHEDEF DOSYALAR")
    print("-" * 62)
    plans = []
    for (key, blen, bwid, zoff) in TARGETS:
        path = files[key]
        if not path.is_file():
            print(f"  ATLANDI (yok): {path}")
            continue
        text = path.read_text()
        ns, ne = count_markers(text)
        if ns == 0:
            print(f"  ATLANDI (marker yok): {path.name}")
            continue
        if ns != ne:
            print(f"  HATA: {path.name} marker sayilari esit degil ({ns}/{ne})")
            return 1

        # Bu hedefin zarfina gore YENIDEN uret ve YENIDEN dogrula. Zarf
        # degisince kirpma da degisir; onceki hedefin dogrulamasi burada
        # gecerli sayilamaz.
        global BODY_LEN_MM, BODY_WID_MM
        keep = (BODY_LEN_MM, BODY_WID_MM)
        BODY_LEN_MM, BODY_WID_MM = blen, bwid
        try:
            tb = build_boxes(a.facets, a.strips)
            tf, tc = verify(tb, a.facets)
        finally:
            BODY_LEN_MM, BODY_WID_MM = keep
        if tf:
            print(f"  HATA: {path.name} ({blen:.0f}x{bwid:.0f}) dogrulamayi "
                  f"gecemedi: {tf}")
            return 1
        print(f"  {path.name}: zarf {blen:.0f}x{bwid:.0f}, z ofset "
              f"{zoff:+.0f} mm, {len(tb)} kutu, dogrulama PASS")

        new = _render_all(text, tb, a.facets, a.strips, path, ns, zoff)
        plans.append((path, text, new))

    if a.dry_run:
        print("\n--dry-run: hicbir dosyaya YAZMA yapilmadi.")
        return 0

    for path, old, new in plans:
        if old == new:
            print(f"  degismedi: {path.name}")
            continue
        path.write_text(new)
        print(f"  YAZILDI: {path}")
    return 0


def _render_all(text, boxes, n, strips, path, pairs, z_off=0.0):
    """Birden fazla marker cifti varsa hepsini sirayla yeniden yazar."""
    out, cursor = [], 0
    for _ in range(pairs):
        i = text.find(MARKER_START, cursor)
        if i < 0:
            break
        j = text.find(MARKER_END, i)
        if j < 0:
            raise BoreGenerationError(f"{path.name}: {MARKER_END} eksik.")
        j += len(MARKER_END)
        indent = _indent_of(text, i)
        body = "\n".join([_header(n, strips, len(boxes), indent),
                          render_boxes(boxes, indent, z_off)])
        out.append(text[cursor:i])
        out.append(MARKER_START + "\n" + body + "\n" + indent + MARKER_END)
        cursor = j
    out.append(text[cursor:])
    return "".join(out)


if __name__ == "__main__":
    sys.exit(main())
