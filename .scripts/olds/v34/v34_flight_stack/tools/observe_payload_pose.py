#!/usr/bin/env python3
"""E2 teshis araci: yuk pozunu CANLI ve YUKSEK HIZLA kaydet (salt-okunur).

NEDEN VAR: PAYLOAD_FINAL_POSE, birakmadan 2 s sonra GzPoseMonitor
onbellegini TEK BIR KEZ okuyor ve `age_s`'i hic kontrol etmiyor. Boylece
"yuk nereye dustu" sorusuna verilen cevabin
  (a) taze mi bayat mi,
  (b) yuk birakma sonrasi gercekten hareket ediyor mu
oldugu kayitlardan ANLASILAMIYOR. Bu arac ayni gz-transport akisini
bagimsiz olarak dinleyip her ornegi duvar saatiyle damgalar, boylece iki
soru da olculerek cevaplanir.

Gorev calisirken paralel calistirilir; hicbir seye yazmaz, hicbir seyi
tetiklemez, mission runtime'ina baglanmaz. Coktugunde gorev etkilenmez.

    python3 tools/observe_payload_pose.py --out /tmp/pose_trace.csv
"""
import argparse
import os
import subprocess
import sys
import time

WATCH = ("payload_red", "payload_blue", "x500_mono_cam_down_0")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--world", default=os.environ.get("PX4_GZ_WORLD", "default"))
    args = ap.parse_args()

    topic = f"/world/{args.world}/dynamic_pose/info"
    proc = subprocess.Popen(["gz", "topic", "-e", "-t", topic],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, bufsize=1)
    out = open(args.out, "w", buffering=1)
    out.write("wall_ts,name,x,y,z,qx,qy,qz,qw\n")
    print(f"[OBSERVE] {topic} -> {args.out}", flush=True)

    # GzPoseMonitor._read_loop ile AYNI ayristirma: Pose icinde tam iki blok
    # (position, orientation) var, quaternion'un w'si girisin bittigi isaret.
    name = None
    section = None
    pos, ori = {}, {}
    count = 0
    try:
        for raw in proc.stdout:
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
                    if name in WATCH:
                        # E4 FAZ 1.5: yonelim de kaydediliyor -- komut BODY
                        # cercevesinde uretiliyor; aracin GERCEK yaw'i olmadan
                        # "komut dogru yone mi bakiyor" sorusu kontrolcunun
                        # kendi yaw inancina bagimli kalirdi.
                        out.write(f"{time.time():.6f},{name},"
                                  f"{pos['x']:.4f},{pos['y']:.4f},{pos['z']:.4f},"
                                  f"{ori.get('x',0.0):.6f},{ori.get('y',0.0):.6f},"
                                  f"{ori.get('z',0.0):.6f},{ori['w']:.6f}\n")
                        count += 1
                    name = None
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        out.close()
        print(f"[OBSERVE] {count} ornek yazildi.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
