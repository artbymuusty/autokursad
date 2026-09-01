#!/usr/bin/env python3
"""Bir QGC .plan'dan GOREV-UYUMLU bir varyant uretir: <ad>_gorev.plan

NEDEN
-----
Hazirlanan lane_*.plan rotalari QGC'de tek basina ucurulmak icin dogru: son
item NAV_RETURN_TO_LAUNCH, yani rota bitince arac kendi basina eve doner.
Ama Gorev 2 bu rotayi KABUL ETMEZ. gorev2_orchestrator.py
_validate_route_and_start_index() sozlesmesi:

    sadece NAV_WAYPOINT (16); seq 0'da opsiyonel NAV_TAKEOFF (22);
    HICBIR yerde NAV_LAND (21) ve NAV_RETURN_TO_LAUNCH (20).

Gerekcesi de rotanin kendisinde: PX4 rotayi bir inise kadar ucurursa, arama
fazi Offboard payload asamasi icin hala havada olmasi gerekirken arac inmis
olur. Bu yuzden rota arm etmeden ONCE reddedilir -- ucus ortasinda degil.

Donus/inis bu sistemin KENDI isi: MISSION_TIMEOUT ya da arama bitisi ->
RETURN_TO_CHECKPOINT -> LANDING (core/mission/phase.py). Rotadaki RTL o
mantigi devralip bozar.

BU SCRIPT ORIJINALE DOKUNMAZ. Yeni bir dosya yazar; QGC'de tek basina
ucurmak icin orijinal .plan oldugu gibi kalir.

Yapilan tek degisiklik: RTL ve LAND item'larinin silinmesi ve kalanlarin
doJumpId'lerinin yeniden numaralandirilmasi. Waypoint koordinatlari, irtifa,
hiz, home pozisyonu, geofence ve rally noktalari AYNEN korunur.
"""
import json
import sys
from pathlib import Path

CMD_NAV_WAYPOINT = 16
CMD_NAV_RETURN_TO_LAUNCH = 20
CMD_NAV_LAND = 21
CMD_NAV_TAKEOFF = 22
DROP = {CMD_NAV_RETURN_TO_LAUNCH, CMD_NAV_LAND}
NAMES = {16: "NAV_WAYPOINT", 20: "NAV_RETURN_TO_LAUNCH", 21: "NAV_LAND", 22: "NAV_TAKEOFF"}


def main() -> int:
    if len(sys.argv) < 2:
        print("kullanim: make_gorev_plan.py <plan.plan> [cikti.plan]")
        return 1
    src = Path(sys.argv[1]).expanduser().resolve()
    if not src.is_file():
        print(f"HATA: yok: {src}")
        return 1
    dst = Path(sys.argv[2]).expanduser().resolve() if len(sys.argv) > 2 \
        else src.with_name(src.stem + "_gorev.plan")

    doc = json.loads(src.read_text())
    items = doc.get("mission", {}).get("items", [])

    kept, dropped = [], []
    for it in items:
        (dropped if it.get("command") in DROP else kept).append(it)

    # doJumpId QGC icinde 1'den baslayan ardisik olmali; item silince bosluk
    # kalirsa QGC dosyayi tekrar actiginda sikayet eder.
    for i, it in enumerate(kept, start=1):
        it["doJumpId"] = i

    # Sozlesmeyi cikti uzerinde tekrar dogrula -- silmek yetmez, kalanin
    # gecerli oldugunu da kanitlamak gerek.
    problems = []
    if len(kept) < 2:
        problems.append(f"kalan item sayisi {len(kept)} < 2")
    for i, it in enumerate(kept):
        c = it.get("command")
        n = NAMES.get(c, f"cmd_{c}")
        if c == CMD_NAV_TAKEOFF and i != 0:
            problems.append(f"seq={i} NAV_TAKEOFF ama seq 0 degil")
        elif c not in (CMD_NAV_WAYPOINT, CMD_NAV_TAKEOFF):
            problems.append(f"seq={i} {n} -- desteklenmiyor")

    doc["mission"]["items"] = kept
    print(f"[GOREV-PLAN] kaynak : {src.name}  ({len(items)} item)")
    for it in dropped:
        print(f"[GOREV-PLAN] silindi: {NAMES.get(it.get('command'), it.get('command'))}")
    print(f"[GOREV-PLAN] kalan  : {len(kept)} item "
          f"({', '.join(NAMES.get(i.get('command'), str(i.get('command'))) for i in kept)})")

    if problems:
        print("[GOREV-PLAN] HATA: cikti Gorev 2 sozlesmesine uymuyor:")
        for p in problems:
            print(f"[GOREV-PLAN]   - {p}")
        return 1

    dst.write_text(json.dumps(doc, indent=4) + "\n")
    print(f"[GOREV-PLAN] yazildi: {dst}")
    print("[GOREV-PLAN] orijinal dosyaya DOKUNULMADI")
    return 0


if __name__ == "__main__":
    sys.exit(main())
