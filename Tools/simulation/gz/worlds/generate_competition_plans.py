#!/usr/bin/env python3
"""KURSAD40 -- tek parkur icin QGroundControl .plan rotalarini uretir.

NEDEN VAR
---------
Rotalar bugune kadar elle QGC'de cizilip kaydediliyordu. Sonuc: koordinatlar
tasarim sabitlerinden (TRACK_HALF, LEADIN, ARC_R, ARC_SEGS, ARC_OFFSET)
kopuk yasiyordu ve bir sabit degistiginde .plan dosyalari sessizce eskiyordu.
Bu script rotalari O SABITLERDEN uretir, yani tek dogruluk kaynagi kod olur.

Ayrica: Gorev 2 rotayi KENDISI uretmez. gorev2_orchestrator.py
_validate_route_and_start_index() yalnizca aracin uzerinde HAZIR bir rota
arar ve su sozlesmeyi dayatir:

    sadece NAV_WAYPOINT (16); seq 0'da opsiyonel NAV_TAKEOFF (22);
    HICBIR yerde NAV_LAND (21) ve NAV_RETURN_TO_LAUNCH (20).

Bu script o sozlesmeye uyan dosyalar uretir ve yazmadan once kendi
ciktisini ayni kurala karsi dogrular. (Eski lane_*.plan dosyalari RTL ile
bitiyordu ve bu yuzden her biri arm etmeden once MISSION_ROUTE_INVALID
ile reddediliyordu -- 2026-08-30'da dordu de olculdu.)

IRTIFA
------
ALT = MISSION_ALTITUDE_M = 15 m. Bu keyfi degil, ZORUNLU:
target_validator.py:32 `abs(current_altitude_m - target_altitude_m) < 0.5`
ile geciti MISSION_ALTITUDE_M'e (parameters.py:9 = 15.0) kilitliyor. Rota
12 m'de ucarsa |12-15| = 3.0 ve altitude_ok KALICI olarak False kalir;
is_track_ready() hicbir zaman True olmaz, Mission->Offboard devri hic
tetiklenmez, hicbir hedef kaydedilmez. Yani 12 m'lik bir rotayla Gorev 2'nin
basarili olmasi yapisal olarak imkansizdir.

KOORDINAT DONUSUMU
------------------
visualize_lanes.py:plan_routes()'un tam tersi (o ters yonde calisir):

    lat = lat0 + degrees(Y / R)
    lon = lon0 + degrees(X / (R * cos(lat0)))

lat0/lon0 default.sdf'in <spherical_coordinates> blogundan OKUNUR,
burada tekrarlanmaz. cos(lat0) sabittir, waypoint basina yeniden
hesaplanmaz -- mevcut dosyalari birebir yeniden uretmesinin sebebi bu
(olculen kalinti < 4e-10 m).

KULLANIM
--------
    python3 generate_competition_plans.py --dry-run
    python3 generate_competition_plans.py
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
WORLD_FILE = HERE / "default.sdf"
LAUNCHER_FILE = HERE.parent.parent.parent.parent / "safe_sitl_launcher.sh"
MISSIONS_DIR = Path("~/Documents/QGroundControl Daily/Missions").expanduser()

# --- rota tasarim sabitleri (visualize_lanes.py ile AYNI) --------------
ALT = 15               # gorev irtifasi (m, relative) -- MISSION_ALTITUDE_M
AREA_LENGTH_M = 100.0  # parkur Y uzunlugu
AREA_CENTER_X = 0.0
TRACK_HALF = 7.25      # 2way iz yari araligi -> aralik 14.50 m
LEADIN = 20.0          # tarama bandi disina lead-in / run-out payi
ARC_R = TRACK_HALF
ARC_SEGS = 6           # yarim daireyi 6 segmente bol -> 5 ara waypoint
ARC_OFFSET = 13.0      # yay merkezi Y=100'un bu kadar kuzeyinde (FREN
                       # MESAFESI sonucu, geometri degil -- visualize_lanes.py
                       # icindeki tam turetmeye bakin). Irtifadan BAGIMSIZ.
CRUISE_SPEED = 5
HOVER_SPEED = 5

R = 6378137.0
CMD_NAV_WAYPOINT, CMD_NAV_TAKEOFF = 16, 22
FORBIDDEN = {20: "NAV_RETURN_TO_LAUNCH", 21: "NAV_LAND"}


def parse_world_origin(path: Path = WORLD_FILE) -> tuple:
    t = path.read_text()
    lat = float(re.search(r"<latitude_deg>([^<]+)</latitude_deg>", t).group(1))
    lon = float(re.search(r"<longitude_deg>([^<]+)</longitude_deg>", t).group(1))
    return lat, lon


def parse_spawn(path: Path = LAUNCHER_FILE) -> tuple:
    m = re.search(r'PX4_GZ_MODEL_POSE\s*=\s*"([^"]+)"', path.read_text())
    if not m:
        raise SystemExit(f"PX4_GZ_MODEL_POSE bulunamadi: {path}")
    p = [float(v) for v in m.group(1).split(",")]
    return p[0], p[1]


def design_routes(spawn: tuple) -> dict:
    """Tasarim sabitlerinden iki rotanin yerel X/Y noktalarini uret."""
    sx, sy = spawn
    cx = AREA_CENTER_X
    cy = AREA_LENGTH_M + ARC_OFFSET
    arc = [(cx + ARC_R * math.cos(math.pi * k / ARC_SEGS),
            cy + ARC_R * math.sin(math.pi * k / ARC_SEGS))
           for k in range(1, ARC_SEGS)]
    return {
        # seq 0 TAKEOFF spawn/home uzerinde; gerisi NAV_WAYPOINT.
        "competition_1way": [
            (CMD_NAV_TAKEOFF, sx, sy),
            (CMD_NAV_WAYPOINT, cx, -LEADIN),
            (CMD_NAV_WAYPOINT, cx, AREA_LENGTH_M + LEADIN),
        ],
        "competition_2way": [
            (CMD_NAV_TAKEOFF, sx, sy),
            (CMD_NAV_WAYPOINT, cx + TRACK_HALF, -LEADIN),
            (CMD_NAV_WAYPOINT, cx + TRACK_HALF, cy),
            *[(CMD_NAV_WAYPOINT, x, y) for x, y in arc],
            (CMD_NAV_WAYPOINT, cx - TRACK_HALF, cy),
            (CMD_NAV_WAYPOINT, cx - TRACK_HALF, -LEADIN),
        ],
    }


def build_plan(points: list, lat0: float, lon0: float, home_xy: tuple) -> dict:
    coslat = math.cos(math.radians(lat0))

    def to_ll(x, y):
        return lat0 + math.degrees(y / R), lon0 + math.degrees(x / (R * coslat))

    hlat, hlon = to_ll(*home_xy)
    items = []
    for i, (cmd, x, y) in enumerate(points):
        lat, lon = to_ll(x, y)
        items.append({
            "AMSLAltAboveTerrain": None,
            "Altitude": ALT,
            "AltitudeMode": 1,          # relative to home
            "autoContinue": True,
            "command": cmd,
            "doJumpId": i + 1,          # 1'den baslar, bosluksuz (QGC sarti)
            "frame": 3,                 # MAV_FRAME_GLOBAL_RELATIVE_ALT
            "params": [0, 0, 0, None, lat, lon, ALT],
            "type": "SimpleItem",
        })
    return {
        "fileType": "Plan",
        "geoFence": {"circles": [], "polygons": [], "version": 2},
        "groundStation": "QGroundControl",
        "mission": {
            "cruiseSpeed": CRUISE_SPEED,
            "firmwareType": 12,         # PX4
            "globalPlanAltitudeMode": 1,
            "hoverSpeed": HOVER_SPEED,
            "items": items,
            "plannedHomePosition": [hlat, hlon, 491],
            "vehicleType": 2,           # multirotor
            "version": 2,
        },
        "rallyPoints": {"points": [], "version": 2},
        "version": 1,
    }


def validate(plan: dict, name: str) -> list:
    """gorev2_orchestrator._validate_route_and_start_index() sozlesmesi."""
    items = plan["mission"]["items"]
    errs = []
    if len(items) < 2:
        errs.append(f"{name}: {len(items)} item, en az 2 gerekli")
    for i, it in enumerate(items):
        c = it["command"]
        if c in FORBIDDEN:
            errs.append(f"{name}: seq={i} {FORBIDDEN[c]} -- rotada yasak")
        elif c == CMD_NAV_TAKEOFF and i != 0:
            errs.append(f"{name}: seq={i} NAV_TAKEOFF, yalnizca seq 0'da olabilir")
        elif c not in (CMD_NAV_WAYPOINT, CMD_NAV_TAKEOFF):
            errs.append(f"{name}: seq={i} cmd={c} desteklenmiyor")
        if it["Altitude"] != ALT or it["params"][6] != ALT:
            errs.append(f"{name}: seq={i} irtifa {it['Altitude']}/{it['params'][6]} != {ALT}")
    if [it["doJumpId"] for it in items] != list(range(1, len(items) + 1)):
        errs.append(f"{name}: doJumpId 1'den baslayan ardisik dizi degil")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="yazmaz, raporlar")
    ap.add_argument("--out-dir", type=Path, default=MISSIONS_DIR)
    args = ap.parse_args()

    lat0, lon0 = parse_world_origin()
    spawn = parse_spawn()
    print(f"world origin : {lat0!r}, {lon0!r}   (default.sdf)")
    print(f"spawn/home   : X={spawn[0]:g}  Y={spawn[1]:g}   (safe_sitl_launcher.sh)")
    print(f"irtifa       : {ALT} m (MISSION_ALTITUDE_M)\n")

    fail = 0
    for name, pts in design_routes(spawn).items():
        plan = build_plan(pts, lat0, lon0, spawn)
        errs = validate(plan, name)
        length = sum(math.hypot(pts[i + 1][1] - pts[i][1], pts[i + 1][2] - pts[i][2])
                     for i in range(len(pts) - 1))
        print(f"=== {name}.plan  ({len(pts)} item, {length:.1f} m, "
              f"{CRUISE_SPEED} m/s'te {length / CRUISE_SPEED:.0f} s) ===")
        print(f"{'seq':>3} {'cmd':>4} {'X(E)':>9} {'Y(N)':>9}   lat / lon")
        for i, ((cmd, x, y), it) in enumerate(zip(pts, plan["mission"]["items"])):
            print(f"{i:>3} {cmd:>4} {x:9.3f} {y:9.3f}   "
                  f"{it['params'][4]:.15f}  {it['params'][5]:.15f}")
        if errs:
            print("  SOZLESME IHLALI:"); [print("   !", e) for e in errs]; fail = 1
        else:
            print("  sozlesme OK (yalnizca NAV_WAYPOINT + seq0 NAV_TAKEOFF, RTL/LAND yok)")

        if not args.dry_run and not errs:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            out = args.out_dir / f"{name}.plan"
            out.write_text(json.dumps(plan, indent=4) + "\n")
            print(f"  yazildi: {out}")
        print()

    if fail:
        print("Sozlesme ihlali var -- yazma yapilmadi.", file=sys.stderr)
        return 1
    if args.dry_run:
        print("--dry-run: hicbir dosya yazilmadi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
