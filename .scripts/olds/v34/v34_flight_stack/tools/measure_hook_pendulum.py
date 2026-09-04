#!/usr/bin/env python3
"""GOREV J: kanca sarkac periyodu ve genligini CANLI olcer (salt-okunur).

NEDEN VAR: MAGNET_DWELL_S (hook_seating.py) olculen sarkac periyodundan
TURETILIYOR -- secilmiyor. Kanca 25 cm'den 31 cm'e uzatildiginda o olcum
gecersiz kalir, cunku periyot ip boyuna baglidir. Bu arac, 0.831 s'lik eski
degeri ureten olcumun ayni turden bir tekrarini yapar: kancanin ARACA GORE
yanal sapmasini yuksek hizla kaydeder, sifir gecislerinden periyodu ve
tepe genligini cikarir.

observe_payload_pose.py ile ayni gz-transport akisini dinler; hicbir seye
yazmaz, gorev runtime'ina baglanmaz.

    python3 tools/measure_hook_pendulum.py --out /tmp/hook_swing.csv --seconds 40
"""
import argparse
import math
import os
import subprocess
import sys
import time

HOOK = "hook_body_link"
BASE = "base_link"


def analiz(ornekler):
    """(t, lateral_m) listesinden periyot ve genlik cikarir.

    Yontem: ortalamayi cikar (salinim merkezi arac altinda degil,
    surukleme yuzunden kayabilir), yukari yonlu sifir gecislerini bul,
    ardisik gecisler arasindaki sureleri periyot say. Medyan raporlanir --
    tek bir bozuk gecis sonucu kaydirmasin.
    """
    if len(ornekler) < 20:
        return None
    t = [o[0] for o in ornekler]
    y = [o[1] for o in ornekler]
    ort = sum(y) / len(y)
    y = [v - ort for v in y]

    gecisler = []
    for i in range(1, len(y)):
        if y[i - 1] <= 0.0 < y[i]:
            # dogrusal ara deger: sifiri tam nerede kesti
            pay = -y[i - 1] / (y[i] - y[i - 1])
            gecisler.append(t[i - 1] + pay * (t[i] - t[i - 1]))
    periyotlar = [b - a for a, b in zip(gecisler, gecisler[1:])]
    periyotlar = [p for p in periyotlar if 0.15 < p < 5.0]
    if not periyotlar:
        return None
    periyotlar.sort()
    n = len(periyotlar)
    medyan = periyotlar[n // 2] if n % 2 else 0.5 * (periyotlar[n // 2 - 1] + periyotlar[n // 2])
    genlik = max(abs(v) for v in y)
    p95 = periyotlar[min(n - 1, int(0.95 * n))]
    return {
        "periyot_medyan_s": medyan,
        "periyot_min_s": periyotlar[0],
        "periyot_max_s": periyotlar[-1],
        "periyot_p95_s": p95,
        "periyot_sayisi": n,
        "genlik_tepe_m": genlik,
        "ornek": len(ornekler),
        "sure_s": t[-1] - t[0],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--world", default=os.environ.get("PX4_GZ_WORLD", "default"))
    args = ap.parse_args()

    topic = f"/world/{args.world}/dynamic_pose/info"
    proc = subprocess.Popen(["gz", "topic", "-e", "-t", topic],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, bufsize=1)
    out = open(args.out, "w", buffering=1)
    out.write("wall_ts,name,x,y,z\n")
    print(f"[SARKAC] {topic} -> {args.out} ({args.seconds:.0f} s)", flush=True)

    name = None
    section = None
    pos, ori = {}, {}
    hook_ornek = []          # (t, yanal sapma)
    son_base = None
    t0 = time.time()
    try:
        for raw in proc.stdout:
            if time.time() - t0 > args.seconds:
                break
            line = raw.strip()
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip().strip('"')
                pos, ori, section = {}, {}, None
            elif line.startswith("position"):
                section = "pos"
            elif line.startswith("orientation"):
                section = "ori"
            elif line == "}":
                section = None
            elif section and ":" in line:
                key, _, value = line.partition(":")
                try:
                    val = float(value)
                except ValueError:
                    continue
                (pos if section == "pos" else ori)[key.strip()] = val
                if section == "ori" and key.strip() == "w" and name and len(pos) == 3:
                    simdi = time.time()
                    if name.endswith(BASE):
                        son_base = (pos["x"], pos["y"])
                    if name.endswith(HOOK):
                        out.write(f"{simdi:.6f},{name},"
                                  f"{pos['x']:.5f},{pos['y']:.5f},{pos['z']:.5f}\n")
                        # dynamic_pose link pozlari MODEL cercevesinde gelir;
                        # base gorulduyse yine de fark alinir (iki durumda da
                        # dogru: model cercevesinde base ~0'dadir).
                        bx, by = son_base if son_base else (0.0, 0.0)
                        hook_ornek.append((simdi, math.hypot(pos["x"] - bx,
                                                             pos["y"] - by)))
                    name = None
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        out.close()

    print(f"[SARKAC] {len(hook_ornek)} kanca ornegi.", flush=True)
    sonuc = analiz(hook_ornek)
    if not sonuc:
        print("[SARKAC] YETERSIZ VERI -- periyot cikarilamadi.", flush=True)
        return 1
    for k, v in sonuc.items():
        print(f"[SARKAC] {k:20s} = {v:.4f}" if isinstance(v, float) else
              f"[SARKAC] {k:20s} = {v}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
