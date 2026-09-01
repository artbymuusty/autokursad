#!/usr/bin/env python3
"""FAZ 4 / ADIM 6 -- sinir cercevesi HSV tespitini bozuyor mu?

Log taramak yerine DOGRUDAN test: araci gorev irtifasina cikar, orada
Gazebo'nun GERCEK render ettigi kameradan kare topla ve o karelerin
uzerinde projenin GERCEK detektorunu (HSVContourDetector, main_gz.py'de
kurulan tek detektor) calistir.

Cerceve kadraja girdigi halde hicbir kare/ucgen/altigen tespiti
uretmiyorsa iddia kanitlanmis olur. Yalnizca "yanlis pozitif yok" demek
yetmez: cerceve GORUNUYOR mu, o da olculur (notr gri piksel orani), yoksa
"kadrajda olmayan bir seyi tespit etmedik" gibi bos bir sonuc cikar.

Exit: 0 = cerceve kadrajda VE ondan kaynakli tespit yok, 1 = aksi.
"""
import asyncio
import json
import math
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from mavsdk import System

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "v34_flight_stack"))
from core.detection.hsv_contour_detector import HSVContourDetector      # noqa: E402
from gz_system.gz_camera_source import GzCameraSource                    # noqa: E402
from gz_system.gz_env import apply_gz_env                                # noqa: E402

CONNECTION = "udp://:14540"
TARGET_ALT_M = 15.0
CLIMB_TIMEOUT_S = float(os.environ.get("FP_CLIMB_TIMEOUT_S", 300.0))
HOVER_SAMPLE_S = 25.0
GZ_TOPIC = "/world/default/model/x500_mono_cam_down_0/link/camera_link/sensor/camera/image"
ZMQ_ADDR = "tcp://127.0.0.1:5555"       # kanonik adres: camera_service_manager
                                        # tek bir servis ornegi tutar (PID dosyasi),
                                        # ikinci bir adres istemek onu asiyordu.


def log(m): print(f"[FP-TEST] {m}", flush=True)


def neutral_fraction(bgr):
    """Notr (S dusuk) ve parlak piksellerin orani -- cerceve kadrajda mi."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    s, v = hsv[:, :, 1], hsv[:, :, 2]
    return float(np.mean((s < 30) & (v > 140)))


async def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("boundary_fp.json")
    apply_gz_env()

    drone = System()
    await drone.connect(system_address=CONNECTION)
    async def _c():
        async for st in drone.core.connection_state():
            if st.is_connected: return
    await asyncio.wait_for(_c(), timeout=60)
    async def _h():
        async for h in drone.telemetry.health():
            if h.is_armable: return
    await asyncio.wait_for(_h(), timeout=60)
    log("arac hazir")

    camera = GzCameraSource(GZ_TOPIC, ZMQ_ADDR)
    await camera.start()
    log("kamera kaynagi acildi")

    await drone.action.set_takeoff_altitude(TARGET_ALT_M)
    await drone.action.arm()
    await drone.action.takeoff()
    log(f"kalkis (hedef {TARGET_ALT_M} m, tirmanis penceresi {CLIMB_TIMEOUT_S:.0f}s)")

    t0 = time.monotonic()
    alt = 0.0
    async for p in drone.telemetry.position():
        alt = p.relative_altitude_m
        if alt >= TARGET_ALT_M - 2.5 or time.monotonic() - t0 > CLIMB_TIMEOUT_S:
            break
        if int(time.monotonic() - t0) % 20 == 0:
            log(f"  tirmanis t+{time.monotonic()-t0:5.0f}s alt={alt:5.2f} m")
        await asyncio.sleep(0.5)
    log(f"orneklemeye baslaniyor, alt={alt:.2f} m")

    det = HSVContourDetector()
    frames = 0
    hits = {}
    neutral = []
    saved = None
    t1 = time.monotonic()
    while time.monotonic() - t1 < HOVER_SAMPLE_S:
        try:
            frame = await camera.get_frame()
        except Exception:
            await asyncio.sleep(0.2); continue
        if frame is None:
            await asyncio.sleep(0.2); continue
        frames += 1
        neutral.append(neutral_fraction(frame))
        if saved is None:
            saved = frame.copy()
        for d in det.detect(frame):
            hits[d.shape_type] = hits.get(d.shape_type, 0) + 1
        await asyncio.sleep(0.2)

    async for p in drone.telemetry.position():
        alt = p.relative_altitude_m
        break

    nf = (sum(neutral) / len(neutral)) if neutral else 0.0
    log("")
    log(f"irtifa            : {alt:.2f} m")
    log(f"islenen kare      : {frames}")
    log(f"notr-parlak piksel: %{nf*100:.2f}  (cerceve kadrajda mi)")
    log(f"tespitler         : {hits if hits else '(hicbiri)'}")

    frame_ok = frames >= 20
    visible = nf > 0.0005          # cerceve en az bir miktar kadrajda
    no_fp = not hits
    ok = frame_ok and no_fp
    log("")
    log(f"  {'PASS' if frame_ok else 'FAIL'}  yeterli kare toplandi (>=20): {frames}")
    log(f"  {'PASS' if visible else 'NOT '}  cerceve kadrajda gorunuyor: %{nf*100:.3f}")
    log(f"  {'PASS' if no_fp else 'FAIL'}  cerceveden yanlis pozitif YOK: {hits or 'yok'}")
    log(f"SONUC: {'PASS' if ok else 'FAIL'}")

    if saved is not None:
        cv2.imwrite(str(out.with_suffix(".png")), saved)
    out.write_text(json.dumps({"altitude_m": alt, "frames": frames,
                               "neutral_bright_fraction": nf, "detections": hits,
                               "pass": ok}, indent=1))
    log(f"artefakt: {out} ve {out.with_suffix('.png')}")

    try:
        await drone.action.land()
        for _ in range(90):
            async for a in drone.telemetry.armed():
                armed = a; break
            if not armed: break
            await asyncio.sleep(1.0)
    except Exception:
        pass
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
