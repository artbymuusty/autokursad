#!/usr/bin/env python3
"""Hover gurultu olcumu -- Climb-then-Cruise esiklerinin kalibrasyonu icin.

NE ICIN: real_system.yaml'daki vz_settle_m_s ve attitude_rate_limit_deg_s
dogrudan SENSOR GURULTU TABANINA oturuyor. Simulasyonda dogrulanmis dar bir
esik gercek ucusta state'in HIC gecmemesine yol acar: CLIMB guard'i
|vz| < vz_settle isterse ve gercek barometre/EKF gurultusu o esigin
uzerindeyse guard hicbir zaman atesleyemez, bacak vertical_timeout_s'te
duser. Bu arac o tabani OLCER.
Protokol: docs/climb-then-cruise-hw-checklist.md, 1. bolum.

GUVENLIK SOZLESMESI -- bu araç UCURMAZ:

  * OFFBOARD'A GIRMEZ. start_offboard() cagrilmaz.
  * HICBIR SETPOINT GONDERMEZ. set_velocity_body / goto_position_ned
    cagrilmaz. Arac nereye gidecegine bu arac karar vermez.
  * VARSAYILAN OLARAK ARM ETMEZ. Gercek donanimda araci havaya RC pilot
    cikarir; bu arac yalnizca telemetriyi okur.
  * --takeoff YALNIZCA SITL kuru kosumu icindir ve acikca istenmelidir.
    O modda bile kullanilan sey PX4'un KENDI AUTO.TAKEOFF'udur (MAVLink
    komutu), Offboard degil -- akan bir setpoint yoktur.

Ornek:

    # Gercek donanim (pasif): pilot araci hover'a alir, sonra
    PYTHONPATH=$PWD python tools/measure_motion_noise.py \
        --config real_system/config/real_system.yaml

    # SITL kuru kosumu (kendisi kalkar ve iner)
    PYTHONPATH=$PWD python tools/measure_motion_noise.py \
        --config gz_system/config/gz_system.yaml --takeoff 10

    # Kaydedilmis bir olcumu yeniden hesapla (ucus gerekmez)
    PYTHONPATH=$PWD python tools/measure_motion_noise.py \
        --analyze logs/motion_noise_20260902_170000.jsonl
"""
import argparse
import asyncio
import json
import logging
import math
import os
import sys
import time
from datetime import datetime

# Guard ile AYNI sarma semantigi. Kalibrasyonun anlamli olmasi icin olculen
# rate, guard'in gordugu rate ile BIREBIR ayni sekilde hesaplanmali; ayri bir
# kopya yazmak ikisinin zamanla ayrismasina davetiye olurdu.
from core.navigation.motion_fsm import _angle_delta_deg
from core.config.parameters import TELEMETRY_STREAM_RATE_HZ
from core.interfaces.i_flight_backend import TelemetryStale

logger = logging.getLogger("measure_motion_noise")

DEFAULT_DURATION_S = 60.0
#: Guard'in kendi dongusuyle ayni hizda ornekle: farkli bir hizda olculen
#: sayisal turev farkli bir gurultu genligi verir (Nyquist), yani baska bir
#: hizin p95'i guard icin gecerli olmaz.
DEFAULT_SAMPLE_HZ = TELEMETRY_STREAM_RATE_HZ
#: Onerilen esik = olculen p95 * bu carpan (checklist 1. bolum).
RECOMMENDATION_MARGIN = 3.0


def percentile(values, pct: float):
    """Dogrusal interpolasyonlu yuzdelik (numpy'nin varsayilan 'linear'
    yontemiyle ayni). Bagimlilik eklememek icin elle yazildi; dogrulugu
    tests/test_measure_motion_noise.py'de bilinen degerlere karsi test
    ediliyor."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[int(rank)])
    fraction = rank - low
    return float(ordered[low] + (ordered[high] - ordered[low]) * fraction)


def attitude_rates(samples):
    """Ardisik orneklerden roll/pitch turevi (deg/s).

    dt her cift icin GERCEK zaman farkindan alinir, nominal ornekleme
    periyodundan degil: bir link tikanmasi 0.1 s yerine 0.4 s'lik bir
    aralik biraktiginda sabit dt kullanmak sahte bir 4x rate uretirdi.
    Bosluk iceren ciftler (telemetri bayat) atlanir."""
    rates = []
    previous = None
    for sample in samples:
        if sample.get("stale") or sample.get("roll_deg") is None:
            previous = None          # bosluk: zinciri kir, ustunden turev alma
            continue
        if previous is not None:
            dt = sample["t"] - previous["t"]
            if dt > 0:
                roll = abs(_angle_delta_deg(sample["roll_deg"], previous["roll_deg"])) / dt
                pitch = abs(_angle_delta_deg(sample["pitch_deg"], previous["pitch_deg"])) / dt
                rates.append({"t": sample["t"], "roll_rate": roll, "pitch_rate": pitch,
                              "max_rate": max(roll, pitch), "dt": dt})
        previous = sample
    return rates


def summarise(samples):
    """Ham orneklerden kalibrasyon ozeti. Ucus gerektirmez -- --analyze bunu
    kaydedilmis bir dosya uzerinde yeniden calistirir, yani p95 hesabi
    olcumden BAGIMSIZ olarak dogrulanabilir."""
    vz = [abs(s["vz"]) for s in samples if not s.get("stale") and s.get("vz") is not None]
    rates = attitude_rates(samples)
    rate_values = [r["max_rate"] for r in rates]

    def stats(values):
        if not values:
            return None
        return {"n": len(values),
                "p50": round(percentile(values, 50), 4),
                "p95": round(percentile(values, 95), 4),
                "p99": round(percentile(values, 99), 4),
                "max": round(max(values), 4),
                "mean": round(sum(values) / len(values), 4)}

    vz_stats, rate_stats = stats(vz), stats(rate_values)
    summary = {
        "kind": "SUMMARY",
        "sample_count": len(samples),
        "stale_count": sum(1 for s in samples if s.get("stale")),
        "duration_s": round(samples[-1]["t"] - samples[0]["t"], 2) if len(samples) > 1 else 0.0,
        "vz_abs_m_s": vz_stats,
        "attitude_rate_deg_s": rate_stats,
        "recommendation_margin": RECOMMENDATION_MARGIN,
        "recommended": {
            "vz_settle_m_s": round(vz_stats["p95"] * RECOMMENDATION_MARGIN, 3) if vz_stats else None,
            "attitude_rate_limit_deg_s": round(rate_stats["p95"] * RECOMMENDATION_MARGIN, 2)
            if rate_stats else None,
        },
    }
    return summary


def print_summary(summary, source: str):
    vz, rate = summary["vz_abs_m_s"], summary["attitude_rate_deg_s"]
    print("")
    print("=" * 68)
    print(f" HOVER GURULTU OLCUMU -- {source}")
    print("=" * 68)
    print(f" ornek: {summary['sample_count']}  bayat: {summary['stale_count']}  "
          f"sure: {summary['duration_s']} s")
    print("")
    if vz:
        print(f" |vz| (m/s)          p50={vz['p50']:<8} p95={vz['p95']:<8} "
              f"p99={vz['p99']:<8} max={vz['max']}")
    else:
        print(" |vz|                 ORNEK YOK")
    if rate:
        print(f" attitude rate (d/s) p50={rate['p50']:<8} p95={rate['p95']:<8} "
              f"p99={rate['p99']:<8} max={rate['max']}")
    else:
        print(" attitude rate        ORNEK YOK")
    print("")
    print(f" ONERILEN ESIKLER (p95 x {RECOMMENDATION_MARGIN:.0f}):")
    print(f"   vz_settle_m_s:             {summary['recommended']['vz_settle_m_s']}")
    print(f"   attitude_rate_limit_deg_s: {summary['recommended']['attitude_rate_limit_deg_s']}")
    print("")
    print(" Bu degerler real_system.yaml'a ELLE, olcum tarihi ve bu log")
    print(" dosyasinin adi yorum olarak yazilmalidir (checklist 1. bolum).")
    print("=" * 68)


async def _sample_loop(flight, duration_s: float, sample_hz: float):
    period = 1.0 / sample_hz
    samples = []
    started = time.monotonic()
    next_tick = started
    print(f"[OLCUM] {duration_s:.0f} s boyunca {sample_hz:.0f} Hz ornekleniyor...")

    while time.monotonic() - started < duration_s:
        now = time.monotonic()
        record = {"t": round(now - started, 4)}
        try:
            _n, _e, vel_down = await flight.get_velocity_ned()
            _lat, _lon, alt = await flight.get_global_position()
            record.update(vz=round(vel_down, 5), alt_m=round(alt, 3))
        except TelemetryStale as e:
            record.update(stale=True, reason=str(e))
        attitude = await flight.get_attitude_euler()
        if attitude is None:
            record["stale"] = True
            record.setdefault("reason", "attitude unavailable")
        else:
            record.update(roll_deg=round(attitude[0], 5),
                          pitch_deg=round(attitude[1], 5),
                          yaw_deg=round(attitude[2], 5))
        samples.append(record)

        elapsed = time.monotonic() - started
        if len(samples) % int(sample_hz * 10) == 0:
            print(f"  {elapsed:5.1f}s  {len(samples)} ornek")
        next_tick += period
        await asyncio.sleep(max(0.0, next_tick - time.monotonic()))
    return samples


async def _run(args) -> int:
    import yaml
    from gz_system.gz_flight_backend import GzFlightBackend
    from real_system.real_flight_backend import RealFlightBackend

    connection, backend_cls = args.connection, GzFlightBackend
    if args.config:
        with open(args.config, "r") as handle:
            config = yaml.safe_load(handle)
        connection = connection or config["flight_backend"]["connection_string"]
        if "real_system" in os.path.basename(os.path.dirname(os.path.dirname(args.config))) \
                or "real" in os.path.basename(args.config):
            backend_cls = RealFlightBackend
    if not connection:
        print("HATA: --connection ya da --config verilmeli.", file=sys.stderr)
        return 2

    print(f"[OLCUM] backend={backend_cls.__name__} connection={connection}")
    flight = backend_cls(connection)
    await asyncio.wait_for(flight.connect(), timeout=args.connect_timeout_s)

    took_off = False
    try:
        if args.takeoff:
            # GUVENLIK: bu dal yalnizca acikca istenirse calisir ve PX4'un
            # KENDI AUTO.TAKEOFF'unu kullanir -- Offboard degil, akan
            # setpoint yok. SITL kuru kosumu icindir.
            print(f"[OLCUM] --takeoff {args.takeoff} m (PX4 AUTO.TAKEOFF, Offboard DEGIL)")
            await flight.arm()
            await flight.takeoff(args.takeoff)
            took_off = True
            for _ in range(int(args.connect_timeout_s * 2)):
                try:
                    _lat, _lon, alt = await flight.get_global_position()
                    if alt >= args.takeoff - 1.0:
                        break
                except TelemetryStale:
                    pass
                await asyncio.sleep(0.5)
            print(f"[OLCUM] Kalkis tamam, {args.settle_s} s oturma bekleniyor...")
            await asyncio.sleep(args.settle_s)
        else:
            print("[OLCUM] PASIF MOD -- arm edilmeyecek, setpoint gonderilmeyecek.")
            print("[OLCUM] Arac ZATEN hover'da olmali. Degilse olcum gecersizdir.")

        samples = await _sample_loop(flight, args.duration_s, args.sample_hz)
    finally:
        if took_off:
            print("[OLCUM] Inis (yalnizca --takeoff ile kalkildigi icin)...")
            try:
                await flight.land()
            except Exception as exc:  # noqa: BLE001 -- teardown olcumu maskelemesin
                print(f"[OLCUM] UYARI: inis komutu basarisiz: {exc}", file=sys.stderr)

    if not samples:
        print("HATA: hic ornek toplanamadi.", file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"motion_noise_{stamp}.jsonl")

    summary = summarise(samples)
    summary.update(source=path, connection=connection, backend=backend_cls.__name__,
                   sample_hz=args.sample_hz, recorded_at=datetime.now().isoformat(timespec="seconds"),
                   takeoff_used=bool(args.takeoff))
    with open(path, "w") as handle:
        handle.write(json.dumps({"kind": "META", "recorded_at": summary["recorded_at"],
                                 "connection": connection, "backend": backend_cls.__name__,
                                 "sample_hz": args.sample_hz, "duration_s": args.duration_s,
                                 "takeoff_used": bool(args.takeoff)}) + "\n")
        for record in samples:
            handle.write(json.dumps({"kind": "SAMPLE", **record}) + "\n")
        handle.write(json.dumps(summary) + "\n")

    print_summary(summary, path)
    return 0


def _analyze(path: str) -> int:
    samples = []
    with open(path, "r") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("kind") == "SAMPLE":
                samples.append(record)
    if not samples:
        print(f"HATA: {path} icinde SAMPLE kaydi yok.", file=sys.stderr)
        return 1
    print_summary(summarise(samples), path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="gz_system.yaml ya da real_system.yaml")
    parser.add_argument("--connection", help="MAVSDK baglanti dizesi (config'i ezer)")
    parser.add_argument("--duration-s", type=float, default=DEFAULT_DURATION_S, dest="duration_s")
    parser.add_argument("--sample-hz", type=float, default=DEFAULT_SAMPLE_HZ, dest="sample_hz")
    parser.add_argument("--out-dir", default="logs", dest="out_dir")
    parser.add_argument("--connect-timeout-s", type=float, default=60.0, dest="connect_timeout_s")
    parser.add_argument("--settle-s", type=float, default=5.0, dest="settle_s",
                        help="--takeoff sonrasi olcume baslamadan once beklenecek sure")
    parser.add_argument("--takeoff", type=float, metavar="ALT_M",
                        help="YALNIZCA SITL kuru kosumu: PX4 AUTO.TAKEOFF ile kalk "
                             "(Offboard DEGIL). Gercek donanimda KULLANMA.")
    parser.add_argument("--analyze", metavar="JSONL",
                        help="Kaydedilmis bir olcumu yeniden hesapla (ucus gerekmez)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    if args.analyze:
        return _analyze(args.analyze)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
