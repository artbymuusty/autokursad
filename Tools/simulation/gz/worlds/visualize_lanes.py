#!/usr/bin/env python3
"""KURSAD40 v34 -- tek yarisma alani + QGC rotalari gorsellestirici.

NEDEN VAR
---------
`generate_competition_area.py` sekilleri HER SITL acilisinda yeniden
konumlandiriyor, QGC rotalari ise
(`Documents/QGroundControl Daily/Missions/competition_*.plan`)
`generate_competition_plans.py` tarafindan uretilen ayri dosyalar. Ikisinin AYNI dunyada birbiriyle tutarli olup
olmadigini -- sekiller rotanin kamera izine giriyor mu, lead-in/run-out
bacaklari parkur disina mi tasiyor, U donusu gercekten yumusak mi --
sayilara bakarak dogrulamak zor. Bu script ikisini tek bir plana cizip
gozle denetlenebilir hale getirir.

HICBIR SEYE YAZMAZ. Sadece okur ve PNG uretir.

VERI KAYNAKLARI (hicbiri hardcode DEGIL)
-----------------------------------------
  sekiller  : default.sdf, KURSAD_COMPETITION_AREA_START/END arasindaki
              <include> bloklarindan (uri + name + pose)
  spawn     : safe_sitl_launcher.sh icindeki PX4_GZ_MODEL_POSE
  world GPS : default.sdf <spherical_coordinates> (yalnizca --source plans
              modunda, .plan lat/lon'unu yerel X/Y'ye geri cevirmek icin)
  sekil olcusu: models/<ad>/model.sdf collision <box><size>
  kamera FOV: ../models/mono_cam/model.sdf <horizontal_fov>

Sekil olculeri model dosyalarindan OKUNUR, brief'ten degil. Onemli bir
tutarsizlik var: brief "Mavi Altigen (2m kenar)" diyor ama model
(`blue_hexagon/model.sdf`, scale 2x + collision 2 x 1.732) kose-koseye
2 m olan, yani KENARI 1 m olan bir altigen. Bu script modeli cizer.

ROTALAR
-------
Varsayilan (--source design): FAZ 3 tasarim sabitlerinden uretir -- .plan
dosyalari daha yazilmadan once tasarimi onizlemek icin.
--source plans: gercek .plan dosyalarini okuyup lat/lon'u yerel X/Y'ye
geri cevirir -- dosyalar yazildiktan SONRA teyit icin.

BILINEN DURUM -- gorev sonu donusu
-----------------------------------
GECERSIZ KILINDI (2026-08-30, tek-parkur migrasyonu). Bu basligin altinda
onceden su analiz duruyordu: "1WAY'in RTL'i lane uzerinden geri doner;
home spawn'da (25, 0) oldugu icin RTL yolu bandin 52 m'sini 30 m
irtifadan ikinci kez katediyor". O metin artik her yuk tasiyan sayisinda
yanlisti, cunku uc dayanagi da degisti:

  * .plan dosyalarinda RTL YOK. competition_1way/2way yalnizca seq 0'da
    NAV_TAKEOFF (22) ve sonrasinda NAV_WAYPOINT (16) tasiyor -- Gorev 2
    rota sozlesmesi RTL ve LAND'i acikca reddediyor
    (gorev2_orchestrator.py _validate_route_and_start_index). Rota
    bitiminde ne olacagi PX4'un kendi mission-end davranisi ve bu
    sistemin RETURN_TO_CHECKPOINT / LANDING fazlaridir, rotadaki bir
    RTL ogesi degil.
  * Home artik (25, 0) degil, (0, -25): parkurun GUNEYINDE, yani donus
    yolu parkurun icinden degil, guney ucundan disari cikar.
  * Gorev irtifasi 12 m degil 15 m (ALT, asagida).

Bu blok kasitli olarak SILINMEDI, GECERSIZ KILINDI: eski 1WAY
loglarindaki "ayni sekil, ikinci kez, daha kucuk" tespitlerin kaynagi
oydu ve o loglara bakan biri aciklamayi burada arayacaktir.

KULLANIM
--------
    python3 visualize_lanes.py                 # tasarimdan, PNG uret
    python3 visualize_lanes.py --source plans  # yazilmis .plan'lardan
    python3 visualize_lanes.py --show          # ayrica ekranda ac
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Arc, Polygon, Rectangle

# --- yollar -----------------------------------------------------------------
HERE      = os.path.dirname(os.path.abspath(__file__))
REPO      = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
WORLD     = os.path.join(HERE, "default.sdf")
MODELS    = os.path.join(HERE, "models")
CAM_MODEL = os.path.join(HERE, "..", "models", "mono_cam", "model.sdf")
LAUNCHER  = os.path.join(REPO, "safe_sitl_launcher.sh")
MISSIONS  = os.path.expanduser("~/Documents/QGroundControl Daily/Missions")
OUT_PNG   = os.path.join(HERE, "competition_layout_preview.png")

# --- alan geometrisi (generate_competition_area.py ile ayni) ----------------
AREA_WIDTH, AREA_LENGTH, EDGE_MARGIN = 30.0, 100.0, 3.0
AREA_CENTER_X = 0.0

# --- FAZ 3 rota tasarim sabitleri -------------------------------------------
ALT        = 15       # gorev irtifasi (m, relative) = MISSION_ALTITUDE_M
                      # (parameters.py:9). 12 DEGIL: target_validator.py:32
                      # geciti |alt - MISSION_ALTITUDE_M| < 0.5 ile kilitliyor,
                      # yani 12 m'lik bir rotada altitude_ok kalici False olur
                      # ve hicbir hedef dogrulanamaz.
TRACK_HALF = 7.25     # 2way iz yari-araligi -> aralik 14.50 m, merkeze simetrik
LEADIN     = 20.0     # tarama bandi disina lead-in / run-out payi
ARC_R      = TRACK_HALF
ARC_SEGS   = 6        # yarim daireyi 6 segmente bol -> 5 ara waypoint
ARC_OFFSET = 13.0     # yay merkezi Y=100'un bu kadar kuzeyinde.
                      # BAGLAYICI KISIT FREN MESAFESI, geometri DEGIL: PX4'un
                      # computeXYSpeedFromWaypoints<3>'u yalnizca 2 WP ileri bakar
                      # ve son adimda target==next_target oldugu icin "ikinci
                      # WP'de durabilmeliyim" kisiti uygular
                      # (TrajectoryConstraints.hpp:117-125). 3.753 m'lik yay
                      # kirisiyle yay girisindeki hiz 2.04 m/s'ye civileniyor;
                      # 5 m/s'ten oraya inmek 10.97 m suruyor. Yay Y=105'te
                      # bassaydi fren tarama bandinin ~6 m ICINDE (Y=94.03)
                      # baslardi. 13 m ile fren Y=102.03'te basliyor.
                      #
                      # DUZELTME (2026-08-30): bu iki turetilmis Y daha once
                      # 94.06 / 102.06 yaziyordu; bagimsiz yeniden turetmede
                      # 3.3 cm sapiyorlar. Sonucu degistirmiyor (minimum kabul
                      # edilebilir ARC_OFFSET 10.9733 m, yani 13.0'da 2.03 m
                      # pay var) ama bu yorum yuk tasiyor, dogru olmali.
                      #
                      # BAGIMLILIK ZINCIRI -- IRTIFA BUNUN ICINDE DEGIL:
                      # ARC_R (=TRACK_HALF), ARC_SEGS, MPC_ACC_HOR=3,
                      # MPC_JERK_AUTO=4, efektif seyir hizi 5 m/s ve
                      # NAV_ACC_RAD=2. PX4'un yatay fren hesabindaki her
                      # mesafe .xy() ile projelendirilir, dolayisiyla gorev
                      # irtifasini degistirmek bu sayiyi ETKILEMEZ (12 -> 15 m
                      # gecisinde dogrulandi). Iz araligini degistiren biri
                      # ise bunu YENIDEN turetmek zorundadir.

# --- gorsel stil ------------------------------------------------------------
RED, BLUE = "#ff0000", "#008cff"           # model.sdf <diffuse> degerleri
ROUTE_STYLE = {                            # (renk, cizgi stili, etiket)
    "1way": ("#e6ab02", "-",  "1WAY (tek gecis)"),
    "2way": ("#7570b3", "--", "2WAY (cift gecis + U donusu)"),
}


# ============================================================================
# Ayristiricilar
# ============================================================================
def parse_spawn(path: str = LAUNCHER) -> tuple[float, float]:
    """safe_sitl_launcher.sh'ten PX4_GZ_MODEL_POSE="x,y,z,r,p,yw" oku."""
    m = re.search(r'PX4_GZ_MODEL_POSE\s*=\s*"([^"]+)"', open(path).read())
    if not m:
        raise SystemExit(f"PX4_GZ_MODEL_POSE bulunamadi: {path}")
    parts = [float(v) for v in m.group(1).split(",")]
    return parts[0], parts[1]


def parse_world_origin(path: str = WORLD) -> tuple[float, float]:
    """default.sdf <spherical_coordinates> -> world ENU origin (lat, lon)."""
    txt = open(path).read()
    lat = float(re.search(r"<latitude_deg>([^<]+)</latitude_deg>", txt).group(1))
    lon = float(re.search(r"<longitude_deg>([^<]+)</longitude_deg>", txt).group(1))
    return lat, lon


def parse_shapes(path: str = WORLD) -> list[dict]:
    """KURSAD_COMPETITION_AREA_START/END arasindaki <include>'lari oku.

    Yorum metnine degil, marker sinirlarina ve <uri>/<name>/<pose> etiketlerine
    dayanir -- generate_competition_area.py her SITL acilisinda bu blogu
    yeniden yazdigi icin baska hicbir sey sabit degil.

    Sinir cercevesi (competition_boundary) marker'larin DISINDA durur, bu
    yuzden buraya hic girmez; zaten bir hedef degil."""
    txt = open(path).read()
    shapes = []
    blk = re.search(r"KURSAD_COMPETITION_AREA_START(.*?)KURSAD_COMPETITION_AREA_END",
                    txt, re.S)
    if not blk:
        print("  ! UYARI: KURSAD_COMPETITION_AREA blogu default.sdf'te yok")
        return shapes
    for inc in re.finditer(r"<include>(.*?)</include>", blk.group(1), re.S):
        body = inc.group(1)
        uri  = re.search(r"<uri>model://([^<]+)</uri>", body)
        name = re.search(r"<name>([^<]+)</name>", body)
        pose = re.search(r"<pose>([^<]+)</pose>", body)
        if not (uri and pose):
            continue
        p = [float(v) for v in pose.group(1).split()]
        shapes.append({"model": uri.group(1),
                       "name": name.group(1) if name else uri.group(1),
                       "x": p[0], "y": p[1]})
    return shapes


def parse_camera_swath(alt: float = ALT, path: str = CAM_MODEL) -> float:
    """mono_cam <horizontal_fov> -> `alt` irtifasindaki capraz-iz genisligi (m).

    Kamera nadir bakiyor ve goruntunun YATAY ekseni aracin yanal ekseni
    (x500_mono_cam_down/model.sdf: include pose '... 0 1.5707 0'), yani
    kuzeye ucarken yatay FOV dogrudan capraz-iz kapsamasini verir."""
    m = re.search(r"<horizontal_fov>([^<]+)</horizontal_fov>", open(path).read())
    if not m:
        return 0.0
    return 2.0 * alt * math.tan(float(m.group(1)) / 2.0)


def parse_model_size(model: str) -> tuple[float, float]:
    """models/<model>/model.sdf collision <box><size> -> (genislik_x, genislik_y).

    Sekil olcusunu brief'ten tahmin etmek yerine dosyadan okur."""
    p = os.path.join(MODELS, model, "model.sdf")
    if not os.path.exists(p):
        return 1.0, 1.0
    m = re.search(r"<box>\s*<size>([^<]+)</size>", open(p).read())
    if not m:
        return 1.0, 1.0
    s = [float(v) for v in m.group(1).split()]
    return s[0], s[1]


# ============================================================================
# Rota kaynaklari
# ============================================================================
def design_routes() -> dict[str, list[tuple[float, float]]]:
    """FAZ 3 tasarim sabitlerinden 4 rotanin yerel X/Y noktalarini uret.

    RTL bir koordinat tasimadigi icin cizime girmez; rota son waypoint'te
    biter."""
    sx, sy = parse_spawn()
    cx = AREA_CENTER_X
    cy = AREA_LENGTH + ARC_OFFSET
    arc = [(cx + ARC_R * math.cos(math.pi * k / ARC_SEGS),
            cy + ARC_R * math.sin(math.pi * k / ARC_SEGS))
           for k in range(1, ARC_SEGS)]
    return {
        "1way": [
            (sx, sy),
            (cx, -LEADIN),
            (cx, AREA_LENGTH + LEADIN),
        ],
        "2way": [
            (sx, sy),
            (cx + TRACK_HALF, -LEADIN),
            (cx + TRACK_HALF, cy),
            *arc,
            (cx - TRACK_HALF, cy),
            (cx - TRACK_HALF, -LEADIN),
        ],
    }


def plan_routes() -> dict[str, list[tuple[float, float]]]:
    """Yazilmis .plan dosyalarini oku, lat/lon -> yerel X/Y ters cevir."""
    lat0, lon0 = parse_world_origin()
    R = 6378137.0
    coslat = math.cos(math.radians(lat0))
    out = {}
    for key in ROUTE_STYLE:
        p = os.path.join(MISSIONS, f"competition_{key}.plan")
        if not os.path.exists(p):
            print(f"  ! {p} yok -- atlaniyor")
            continue
        pts = []
        for it in json.load(open(p))["mission"]["items"]:
            if it["command"] == 20:              # RTL: koordinat tasimaz
                continue
            lat, lon = it["params"][4], it["params"][5]
            pts.append((math.radians(lon - lon0) * R * coslat,
                        math.radians(lat - lat0) * R))
        out[key] = pts
    return out


# ============================================================================
# Cizim
# ============================================================================
def shape_patch(sh: dict):
    """Sekli GERCEK olcusu ve rengiyle bir matplotlib patch'ine cevir."""
    w, h = parse_model_size(sh["model"])
    x, y = sh["x"], sh["y"]
    col  = RED if sh["model"].startswith("red") else BLUE
    kw   = dict(facecolor=col, edgecolor="black", lw=0.6, alpha=0.95, zorder=5)

    if "hexagon" in sh["model"]:
        # duzgun altigen, koseleri +-X ekseninde: kose-koseye w, duz-duze h
        r = w / 2.0
        pts = [(x + r * math.cos(math.radians(60 * i)),
                y + r * math.sin(math.radians(60 * i))) for i in range(6)]
        return Polygon(pts, closed=True, **kw)

    if "triangle" in sh["model"]:
        # eskenar ucgen; mesh orijini AGIRLIK MERKEZI (model.sdf yorumu),
        # y araligi [-h/3, +2h/3]
        pts = [(x - w / 2, y - h / 3), (x + w / 2, y - h / 3), (x, y + 2 * h / 3)]
        return Polygon(pts, closed=True, **kw)

    return Rectangle((x - w / 2, y - h / 2), w, h, **kw)


def scan_tracks(pts) -> list[float]:
    """Rotanin tarama bandini (Y in [0,100]) dik gecen duz bacaklarinin X'i.

    Lead-in capraz bacaklari ve U-yay kirislerini disarida birakir -- yalnizca
    sekillerin gercekten tarandigi bacaklar sayilir.

    Toleranslar sifir DEGIL: --source plans modunda koordinatlar lat/lon'dan
    geri projelendiriliyor, yani tam 0.0 / 100.0 yerine 99.99999997 gibi
    degerler geliyor. Sifir toleransla bu mod sessizce hicbir tarama bacagi
    bulamaz ve kapsama paneli bos cikar."""
    out = []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if (abs(x2 - x1) < 0.05                       # dik (kuzey-guney) bacak
                and min(y1, y2) <= 0.5                # bandin altindan basliyor
                and max(y1, y2) >= AREA_LENGTH - 0.5):  # ustunde bitiyor
            out.append((x1 + x2) / 2.0)
    return out


def draw_scene(ax, shapes, spawn, routes, *, legend=False, arrows=True,
               swath=0.0, only=None):
    """Parkur siniri + sekiller + spawn + rotalar.

    swath > 0 ise her tarama bacaginin kamera izini seffaf bant olarak cizer.
    only verilirse yalnizca o rota anahtarlarini cizer."""
    cx = AREA_CENTER_X
    x0 = cx - AREA_WIDTH / 2
    ax.add_patch(Rectangle((x0, 0), AREA_WIDTH, AREA_LENGTH,
                           facecolor="#f2f2f2", edgecolor="#404040",
                           lw=1.6, zorder=0))
    # sekillerin durabilecegi ic bolge (EDGE_MARGIN kadar iceride)
    ax.add_patch(Rectangle((x0 + EDGE_MARGIN, EDGE_MARGIN),
                           AREA_WIDTH - 2 * EDGE_MARGIN,
                           AREA_LENGTH - 2 * EDGE_MARGIN,
                           facecolor="none", edgecolor="#a0a0a0",
                           lw=0.8, ls=":", zorder=1))
    ax.axvline(cx, color="#b0b0b0", lw=0.7, ls="-.", zorder=1)

    for sh in shapes:
        ax.add_patch(shape_patch(sh))

    for key, (col, ls, lbl) in ROUTE_STYLE.items():
        pts = routes.get(key)
        if not pts or (only and key not in only):
            continue
        xs, ys = zip(*pts)
        if swath > 0:
            for tx in scan_tracks(pts):
                ax.add_patch(Rectangle((tx - swath / 2, 0), swath, AREA_LENGTH,
                                       facecolor=col, alpha=0.13, lw=0, zorder=2))
                ax.plot([tx - swath / 2] * 2, [0, AREA_LENGTH], color=col,
                        lw=0.7, alpha=0.5, zorder=2)
                ax.plot([tx + swath / 2] * 2, [0, AREA_LENGTH], color=col,
                        lw=0.7, alpha=0.5, zorder=2)
        ax.plot(xs, ys, color=col, ls=ls, lw=1.9, zorder=6, alpha=0.9,
                label=lbl if legend else None)
        ax.plot(xs, ys, "o", color=col, ms=2.6, zorder=7)
        if arrows:
            for i in range(len(pts) - 1):
                mx, my = ((xs[i] + xs[i + 1]) / 2, (ys[i] + ys[i + 1]) / 2)
                dx, dy = xs[i + 1] - xs[i], ys[i + 1] - ys[i]
                n = math.hypot(dx, dy)
                if n < 4.0:                       # kisa yay kirislerine ok koyma
                    continue
                ax.annotate("", xy=(mx + dx / n * 2.2, my + dy / n * 2.2),
                            xytext=(mx, my), zorder=8,
                            arrowprops=dict(arrowstyle="-|>", color=col, lw=1.6))

    ax.plot(*spawn, marker="*", ms=20, color="#00b000", mec="black", mew=0.8,
            zorder=10, label="Drone spawn" if legend else None)


def draw_crosstrack(ax, shapes, routes, swath):
    """Capraz-iz (X ekseni) kapsama seridi.

    Kapsama tamamen bir X-ekseni sorusu -- Y'nin hicbir etkisi yok -- bu yuzden
    100 m'lik bandi cizmek yerine tek boyutlu bir kesit cizeriz: her tarama
    bacaginin kamera seridi bir cubuk, her sekil kendi X'inde bir isaret."""
    rows = [("1way", "1WAY izi"), ("2way", "2WAY izleri")]

    cx = AREA_CENTER_X                              # parkur siniri
    ax.axvspan(cx - AREA_WIDTH / 2, cx + AREA_WIDTH / 2,
               facecolor="#e8e8e8", edgecolor="#404040", lw=1.2, zorder=0)
    ax.axvspan(cx - AREA_WIDTH / 2 + EDGE_MARGIN,
               cx + AREA_WIDTH / 2 - EDGE_MARGIN,
               facecolor="none", edgecolor="#a0a0a0", lw=0.8, ls=":", zorder=1)

    for i, (key, label) in enumerate(rows):
        y = len(rows) - i
        col = ROUTE_STYLE[key][0]
        for tx in scan_tracks(routes.get(key, [])):
            ax.barh(y, swath, left=tx - swath / 2, height=0.52, color=col,
                    alpha=0.30, edgecolor=col, lw=1.1, zorder=3)
            ax.plot([tx], [y], marker="|", ms=13, color=col, mew=2.0, zorder=4)
        ax.text(-25.5, y, label, va="center", ha="left", fontsize=8.5)

    for sh in shapes:                               # sekiller kendi X'inde
        col = RED if sh["model"].startswith("red") else BLUE
        ax.plot([sh["x"]], [0.35], marker="v", ms=9, color=col, mec="black",
                mew=0.6, zorder=6)
        ax.plot([sh["x"], sh["x"]], [0.35, len(rows) + 0.4], color=col, lw=0.8,
                ls="--", alpha=0.45, zorder=2)
    ax.text(-25.5, 0.35, "sekiller (X konumu)", va="center", ha="left", fontsize=8.5)

    ax.set_ylim(-0.3, len(rows) + 0.9)
    ax.set_xlim(-27, 27)
    ax.set_yticks([])
    ax.set_xlabel("X  (metre)   +X = DOGU  -->")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", choices=("design", "plans"), default="design",
                    help="rotalari FAZ 3 tasarimindan mi, yazilmis .plan'lardan mi al")
    ap.add_argument("--out", default=OUT_PNG)
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    shapes = parse_shapes()
    spawn  = parse_spawn()
    routes = design_routes() if args.source == "design" else plan_routes()

    print(f"default.sdf'ten okunan sekiller ({len(shapes)}):")
    for s in shapes:
        w, h = parse_model_size(s["model"])
        print(f"  {s['name']:<16} X={s['x']:8.3f} Y={s['y']:8.3f}"
              f"  ({w:g}x{h:g} m)  merkeze uzaklik dX={s['x']-AREA_CENTER_X:+7.3f}")
    print(f"safe_sitl_launcher.sh'ten spawn: X={spawn[0]} Y={spawn[1]}")
    print(f"rota kaynagi: {args.source}\n")

    swath = parse_camera_swath()
    print(f"mono_cam capraz-iz kapsamasi @ {ALT} m: {swath:.2f} m\n")

    fig = plt.figure(figsize=(16.5, 12.5))
    gs  = fig.add_gridspec(3, 2, width_ratios=[1.05, 1],
                           height_ratios=[1.10, 0.95, 0.62],
                           wspace=0.15, hspace=0.42)
    ax  = fig.add_subplot(gs[:, 0])
    az1 = fig.add_subplot(gs[0, 1])
    az2 = fig.add_subplot(gs[1, 1])
    az3 = fig.add_subplot(gs[2, 1])

    # --- ana genel gorunum ---
    draw_scene(ax, shapes, spawn, routes, legend=True)
    ax.set_title("KURSAD40 v34 -- tek yarisma alani + QGC rotalari\n"
                 f"(irtifa {ALT} m, iz araligi {2*TRACK_HALF:g} m, "
                 f"lead-in/run-out {LEADIN:g} m)", fontsize=12, pad=12)
    ax.set_xlim(-32, 32)
    ax.set_ylim(-34, 124)
    ax.legend(loc="lower right", fontsize=9, framealpha=0.95)

    # --- zoom 1: U donusu ---
    draw_scene(az1, shapes, spawn, routes, arrows=False)
    az1.set_xlim(-14, 14)
    az1.set_ylim(96, 124)
    az1.set_title(f"ZOOM: U-donusu (R={ARC_R:g} m, {ARC_SEGS} segment)\n"
                  f"yay merkezi Y={AREA_LENGTH+ARC_OFFSET:g}, "
                  f"tarama bandi Y<={AREA_LENGTH:g}", fontsize=10)
    az1.axhline(AREA_LENGTH, color="crimson", lw=1.2, ls="--", zorder=9)
    az1.text(-13.4, AREA_LENGTH + 0.4, "tarama bandi ust siniri Y=100",
             color="crimson", fontsize=8, va="bottom")
    # GERCEK yayi (yalnizca ust yarim daire) poligonun altina ciz:
    # 6-segment yaklasiminin sapmasi (sagitta) gozle olculebilsin diye.
    az1.add_patch(Arc((AREA_CENTER_X, AREA_LENGTH + ARC_OFFSET), 2 * ARC_R, 2 * ARC_R,
                      theta1=0, theta2=180, edgecolor="black", lw=1.0, ls=":",
                      zorder=9))
    az1.text(AREA_CENTER_X, AREA_LENGTH + ARC_OFFSET + 0.6,
             f"noktali = gercek yarim daire\nmax sapma "
             f"{ARC_R*(1-math.cos(math.pi/(2*ARC_SEGS))):.2f} m",
             ha="center", va="bottom", fontsize=7.5, color="black")

    # --- zoom 2: spawn / lead-in bolgesi ---
    draw_scene(az2, shapes, spawn, routes, arrows=False)
    az2.set_xlim(-18, 18)
    az2.set_ylim(-30, 14)
    az2.set_title("ZOOM: spawn + lead-in (tum buyuk donusler Y=-20'de,\n"
                  "tarama bandinin disinda)", fontsize=10)
    az2.axhline(0, color="crimson", lw=1.2, ls="--", zorder=9)
    az2.text(-17.4, 0.4, "tarama bandi alt siniri Y=0", color="crimson",
             fontsize=8, va="bottom")

    # --- kapsama: capraz-iz kesiti ---
    draw_crosstrack(az3, shapes, routes, swath)
    az3.set_title(f"CAPRAZ-IZ KAPSAMA KESITI -- kamera izi {swath:.1f} m @ {ALT} m\n"
                  "(cubuk = kameranin gordugu X araligi, dikey cizgi = iz ekseni)",
                  fontsize=10)

    for a in (ax, az1, az2):
        a.set_aspect("equal", adjustable="box")
        a.set_ylabel("Y  (metre)   +Y = KUZEY = drone ileri ekseni  -->")
        a.set_xlabel("X  (metre)   +X = DOGU  -->")
    for a in (ax, az1, az2, az3):
        a.grid(True, ls=":", lw=0.5, color="#c8c8c8", zorder=-1)

    fig.savefig(args.out, dpi=130, bbox_inches="tight", facecolor="white")
    print(f"PNG yazildi: {args.out}")
    if args.show:
        matplotlib.use("MacOSX", force=True)
        plt.show()
    return 0


if __name__ == "__main__":
    sys.exit(main())
