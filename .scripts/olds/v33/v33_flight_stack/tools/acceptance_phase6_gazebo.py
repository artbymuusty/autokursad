#!/usr/bin/env python3
"""PHASE 6 acceptance: payload UAV'ı GERÇEKTEN takip ediyor mu (SITL).

Kriter: "Capture -> Validate -> Create Joint -> Joint State -> Payload
physically follows UAV", ve takip BAĞIMSIZ bir Gazebo poz ölçümüyle
doğrulanır -- payload pose'u elle UAV'a KOPYALANMAZ.

Bu script:
  * Yakalamayı PayloadManager.catch_box_down() ÜZERİNDEN yapar (üretim
    API'si; kalibrasyon scriptlerinin aksine bypass YOK -- burada
    doğrulanan şey tam olarak üretim yolunun kendisidir).
  * Yakalamadan sonra aracı ~0.5 m tırmandırır ve payload'ın pozunu
    GzPoseMonitor'den (Gazebo'nun kendi dynamic_pose yayını) okur.
    Takip iddiası bu bağımsız okumadan doğrulanır.
  * NEGATİF KONTROL çalıştırır: yakalama YOKKEN aynı tırmanışta payload
    yerinde kalmalı. Bu olmadan "takip etti" iddiası her koşulda geçen
    boş bir cümle olurdu.
  * SARKMA GÖZLEMİ: farklı dikey açıklıklarda yakalayıp tırmanır ve
    payload'ın kancadan (araç tabanından) ne kadar sarktığını raporlar.
    Bu bir GÖZLEMDİR, teşhis değil -- FLEX-20'nin ileride gözden
    geçirilmesine veri olsun diye.

FLEX-20'ye veya herhangi bir config'e HİÇBİR ŞEY YAZMAZ.
"""
import argparse
import asyncio
import csv
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config.parameters import (  # noqa: E402
    GOREV3_DESCENT_ALTITUDE_M, OFFBOARD_SETPOINT_INTERVAL_S,
)
from gz_system.gz_flight_backend import GzFlightBackend  # noqa: E402
from gz_system.gz_hook_client import GzHookClient  # noqa: E402
from gz_system.gz_payload_actuator import (  # noqa: E402
    GOREV3_PICKUP_TARGET_COLOR, PAYLOAD_DETACH_TOPIC, PAYLOAD_MODEL,
    VEHICLE_MODEL_NAME,
)
from gz_system.gz_pose_monitor import GzPoseMonitor  # noqa: E402
from payload import PayloadManager, PayloadState  # noqa: E402
from payload import payload_config  # noqa: E402
from payload.backends.gazebo_payload_backend import GazeboPayloadBackend  # noqa: E402

logger = logging.getLogger("phase6")

CLIMB_M = 0.5
SETTLE_S = 5.0
CLIMB_SETTLE_S = 6.0
FOLLOW_TOLERANCE_M = 0.10   # takip kabul payi (hover salinimi + poz gecikmesi)
STATIONARY_TOLERANCE_M = 0.05

# Sarkma gozlemi icin taranacak dikey acikliklar -- Adim D'nin taradigi
# noktalar. Bunlar KALIBRASYON DEGERI DEGIL, gozlem noktalaridir.
SAG_CLEARANCES_M = [0.15, 0.30, 0.50, 0.80]


async def _stock_release(color):
    proc = await asyncio.create_subprocess_exec(
        "gz", "topic", "-t", PAYLOAD_DETACH_TOPIC % color, "-m", "gz.msgs.Empty",
        "-p", "", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await proc.wait()


class Phase6Acceptance:
    def __init__(self, flight, pose_monitor, client, manager_factory, payload_model):
        self.flight = flight
        self.pose_monitor = pose_monitor
        self.client = client
        # HER acceptance kosulu KENDI PayloadManager'ini alir.
        #
        # NEDEN: PayloadState failure state'leri TERMINALdir ve retry/reset
        # akisi bu pakette KASITLI olarak yoktur (payload_state.py
        # TODO(PHASE-13)). Ilk kosul DEPLOY_TIMEOUT'a dustugunde ayni
        # manager'la ikinci bir catch_box_down() cagirmak
        # IllegalPayloadTransitionError firlatir -- 2026-08-23 kosusunda
        # bunu canli gorduk. Bu bir hata DEGIL, tasarimin calismasidir:
        # state machine sessizce yeniden denemeyi REDDETTI. Dogru cozum
        # guard'i gevsetmek degil, her bagimsiz denemeye temiz bir state
        # machine vermektir.
        self._manager_factory = manager_factory
        self.manager = manager_factory()
        self.payload_model = payload_model
        self._target = None
        self._streamer = None
        self.results = {}
        self.sag_rows = []

    # -- ucus yardimcilari ------------------------------------------------

    async def _stream(self):
        while True:
            if self._target is not None:
                try:
                    await self.flight.goto_position_ned(*self._target, 0.0)
                except Exception as e:  # noqa: BLE001
                    logger.warning("setpoint akitilamadi: %s", e)
            await asyncio.sleep(OFFBOARD_SETPOINT_INTERVAL_S)

    async def start_streaming(self):
        n, e, d = await self.flight.get_position_ned()
        self._target = (n, e, d)
        self._streamer = asyncio.create_task(self._stream())

    async def stop_streaming(self):
        if self._streamer:
            self._streamer.cancel()
            try:
                await self._streamer
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._streamer = None

    async def hover_at_altitude(self, altitude_m):
        """Aracı payload'ın üstünde, verilen MUTLAK irtifaya götürür.

        Acceptance bunu kullanır çünkü üretim akışı da böyle uçar:
        gorev3_pickup.py aracı GOREV3_DESCENT_ALTITUDE_M (0.30 m) irtifasına
        indirir -- "açıklık 0.30" komutu DEĞİL. İkisi aynı şey değildir:
        0.30 m irtifada dikey açıklık 0.30 - (payload_z + yarı-yükseklik)
        = 0.25 m'dir ve FLEX-20 eşiğinin ALTINDA kalır. İlk acceptance
        koşusunda (2026-08-23) açıklık 0.30 komutlandı, bu da aracı 0.35 m'ye
        çıkardı ve hover aşımıyla ölçülen açıklık 0.325 m olup kapı
        kapandı -- ölçüm doğruydu, komut yanlıştı."""
        payload = self.pose_monitor.get(self.payload_model)
        if payload is None:
            return False
        self._target = (payload[1], payload[0], -altitude_m)
        await asyncio.sleep(SETTLE_S)
        return True

    async def hover_at_clearance(self, clearance_m):
        """Aracı, payload üstüne `clearance_m` dikey açıklık kalacak şekilde
        götürür. FRAME: Gazebo ENU -> PX4 NED (north=gz_y, east=gz_x)."""
        payload = self.pose_monitor.get(self.payload_model)
        if payload is None:
            return False
        from gz_system.gz_hook_client import PAYLOAD_HALF_HEIGHT_M
        target_z = payload[2] + PAYLOAD_HALF_HEIGHT_M + clearance_m
        self._target = (payload[1], payload[0], -target_z)
        await asyncio.sleep(SETTLE_S)
        return True

    async def climb(self, delta_m):
        n, e, d = self._target
        self._target = (n, e, d - delta_m)
        await asyncio.sleep(CLIMB_SETTLE_S)

    async def reset_hook(self):
        """Mekanizmayı attach'siz duruma getirir.

        BELGELENMİŞ PLUGIN SINIRI (Phase 5, gazebo_payload_backend.py
        has_released() docstring'i): hiçbir şey takılı DEĞİLKEN gelen detach
        isteği HİÇ yayın üretmez (HookAttachSystem.cc:96-99 -- "Detach
        requested but nothing is attached; ignoring"). Bu yüzden koşulsuz
        `wait_for_hook_state(False)` beklemek, zaten temiz olan durumda
        zaman aşımına düşer. İlk acceptance koşusunda (2026-08-23) sarkma
        gözlemi tam bu yüzden hiç satır üretmeden durdu -- kendi
        belgelediğim davranışı hesaba katmamıştım.

        Zaten takılı DEĞİLSE beklemeden döner; yalnızca gerçek bir
        geçişi bekler."""
        if self.client.hook_state() is not True:
            return True
        await self.client.publish_detach()
        try:
            await asyncio.wait_for(self.client.wait_for_hook_state(False), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error("detach dogrulanamadi -- sonraki attach SESSIZCE yok sayilirdi "
                         "(HookAttachSystem.cc:135-139)")
            return False
        await asyncio.sleep(3.0)
        return True

    # -- testler ----------------------------------------------------------

    async def negative_control(self):
        """Yakalama YOKKEN tırmanış: payload yerinde kalmalı."""
        logger.info("=== NEGATIF KONTROL: yakalama yok, arac tirmaniyor ===")
        await self.hover_at_altitude(GOREV3_DESCENT_ALTITUDE_M)
        before = self.pose_monitor.get(self.payload_model)
        await self.climb(CLIMB_M)
        after = self.pose_monitor.get(self.payload_model)
        moved = abs(after[2] - before[2]) if before and after else None
        ok = moved is not None and moved <= STATIONARY_TOLERANCE_M
        self.results["negative_control"] = {
            "payload_z_before": before[2] if before else None,
            "payload_z_after": after[2] if after else None,
            "payload_moved_m": moved, "passed": ok,
        }
        logger.info("NEGATIF KONTROL: payload %.4f m oynadi -> %s",
                    moved if moved is not None else -1, "GECTI" if ok else "KALDI")
        return ok

    async def acceptance(self, label, hover):
        """catch_box_down() -> tirman -> payload takip etti mi.

        İKİ KOŞULDA çalıştırılır (2026-08-23 ölçümü sonrası):
          * "production_altitude": araç GOREV3_DESCENT_ALTITUDE_M'e iner.
            Ölçüldü ki PX4 bu alçaklıkta komutun ~0.03-0.06 m üstünde tutuyor
            ve ulaşılan açıklık 0.307-0.325 m oluyor -- FLEX-20'nin 0.30
            eşiğinin hemen ÜSTÜNDE. Yani kapı üretim profilinde açılmıyor.
          * "inside_envelope": araç kapının GERÇEKTEN açıldığı bir açıklığa
            iner. Phase 6'nın asıl sorusu ("joint oluşuyor ve payload UAV'ı
            takip ediyor mu") ancak kapı açıkken cevaplanabilir; bu koşul
            onu ölçer. FLEX-20 DEĞİŞTİRİLMEZ -- sadece daha alçak uçulur.
        """
        logger.info("=== ACCEPTANCE [%s]: catch_box_down() + %.2f m tirmanis ===",
                    label, CLIMB_M)
        self.manager = self._manager_factory()   # temiz state machine
        await hover()

        clearance = self.client.read_vehicle_payload_clearance()
        result = await self.manager.catch_box_down()
        logger.info("catch_box_down -> success=%s state=%s reason=%s (aciklik=%.3f m)",
                    result.success, self.manager.get_state().value,
                    result.error_reason, clearance if clearance else -1)

        payload_before = self.pose_monitor.get(self.payload_model)
        vehicle_before = self.pose_monitor.get(VEHICLE_MODEL_NAME)
        await self.climb(CLIMB_M)
        payload_after = self.pose_monitor.get(self.payload_model)
        vehicle_after = self.pose_monitor.get(VEHICLE_MODEL_NAME)

        vehicle_delta = (vehicle_after[2] - vehicle_before[2]
                         if vehicle_before and vehicle_after else None)
        payload_delta = (payload_after[2] - payload_before[2]
                         if payload_before and payload_after else None)
        follow_error = (abs(payload_delta - vehicle_delta)
                        if None not in (payload_delta, vehicle_delta) else None)
        ok = (result.success and follow_error is not None
              and follow_error <= FOLLOW_TOLERANCE_M
              and payload_delta > STATIONARY_TOLERANCE_M)

        self.results[f"acceptance[{label}]"] = {
            "catch_box_down_success": result.success,
            "state_after_capture": self.manager.get_state().value,
            "clearance_at_capture_m": clearance,
            "vehicle_climb_m": vehicle_delta, "payload_climb_m": payload_delta,
            "follow_error_m": follow_error, "passed": ok,
        }
        logger.info("ACCEPTANCE [%s]: arac %.3f m, payload %.3f m tirmandi "
                    "(takip hatasi %.4f m) -> %s", label,
                    vehicle_delta or -1, payload_delta or -1, follow_error or -1,
                    "GECTI" if ok else "KALDI")
        return ok

    async def sag_observation(self):
        """GÖZLEM (teşhis değil): farklı açıklıklarda yakalayıp tırmanınca
        payload araç tabanından ne kadar sarkıyor."""
        logger.info("=== SARKMA GOZLEMI ===")
        for clearance in SAG_CLEARANCES_M:
            if not await self.reset_hook():
                break
            await self.hover_at_clearance(clearance)
            measured = self.client.read_vehicle_payload_clearance()
            published = await self.client.publish_attach()
            state = None
            if published:
                try:
                    await asyncio.wait_for(self.client.wait_for_hook_state(True),
                                           timeout=10.0)
                    state = True
                except asyncio.TimeoutError:
                    state = self.client.hook_state()
            await self.climb(CLIMB_M)
            payload = self.pose_monitor.get(self.payload_model)
            vehicle = self.pose_monitor.get(VEHICLE_MODEL_NAME)
            sag = (vehicle[2] - payload[2]) if payload and vehicle else None
            self.sag_rows.append({
                "target_clearance_m": clearance,
                "measured_clearance_m": measured,
                "attach_published": published, "hook_state": state,
                "sag_below_vehicle_m": sag,
                "payload_z": payload[2] if payload else None,
                "vehicle_z": vehicle[2] if vehicle else None,
            })
            logger.info("aciklik %.2f (olculen %.3f): sarkma %.3f m, state=%s",
                        clearance, measured if measured else -1,
                        sag if sag else -1, state)

    def write_csv(self, path):
        if not self.sag_rows:
            return
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(self.sag_rows[0]))
            w.writeheader()
            w.writerows(self.sag_rows)
        logger.info("Sarkma gozlemi yazildi: %s", path)


async def main_async(args):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    payload_model = PAYLOAD_MODEL % GOREV3_PICKUP_TARGET_COLOR
    logger.info("FLEX-20 = %s m (dikey aciklik esigi)",
                payload_config.FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M)

    pose_monitor = GzPoseMonitor(args.world)
    await pose_monitor.start()
    client = await GzHookClient.create(
        payload_model_name=payload_model, vehicle_model_name=VEHICLE_MODEL_NAME,
        world_name=args.world, pose_monitor=pose_monitor)
    if not client.is_state_stream_ready():
        logger.error("/hook/state hazir degil -- plugin yuklu mu? Cikiliyor.")
        await client.stop(); await pose_monitor.stop()
        return 2

    backend = GazeboPayloadBackend(client, payload_model_name=payload_model,
                                   vehicle_model_name=VEHICLE_MODEL_NAME)
    # Backend/client PAYLASILIR (tek gz baglantisi), manager her kosulda
    # yeniden kurulur -- bkz. Phase6Acceptance.__init__ notu.
    flight = GzFlightBackend(args.connection)
    run = Phase6Acceptance(flight, pose_monitor, client,
                           lambda: PayloadManager(backend), payload_model)

    try:
        await flight.connect()
        await _stock_release(GOREV3_PICKUP_TARGET_COLOR)
        await asyncio.sleep(3.0)
        await flight.arm()
        await flight.takeoff(2.0)
        await asyncio.sleep(8.0)
        await flight.start_offboard()
        await run.start_streaming()

        await run.negative_control()
        await run.reset_hook()
        await run.acceptance(
            "production_altitude",
            lambda: run.hover_at_altitude(GOREV3_DESCENT_ALTITUDE_M))
        await run.reset_hook()
        await run.acceptance(
            "inside_envelope", lambda: run.hover_at_clearance(0.15))
        await run.sag_observation()
    finally:
        await run.stop_streaming()
        try:
            await flight.stop_offboard(); await flight.land(); await asyncio.sleep(8.0)
        except Exception as e:  # noqa: BLE001
            logger.warning("Inis hatasi (yoksayiliyor): %s", e)
        await client.stop(); await pose_monitor.stop()

    print("\n===== PHASE 6 ACCEPTANCE SONUCU =====")
    for name, data in run.results.items():
        print(f"\n[{name}] passed={data.get('passed')}")
        for k, v in data.items():
            if k != "passed":
                print(f"    {k}: {v}")
    print("\n===== SARKMA GOZLEMI (TESHIS DEGIL) =====")
    for row in run.sag_rows:
        print("    " + "  ".join(f"{k}={v}" for k, v in row.items()))
    run.write_csv(args.out)
    return 0 if all(d.get("passed") for d in run.results.values()) else 1


def main():
    p = argparse.ArgumentParser(description="Phase 6 acceptance (SITL).")
    p.add_argument("--connection", default="udp://:14540")
    p.add_argument("--world", default="default")
    p.add_argument("--out", default=None)
    a = p.parse_args()
    if a.out is None:
        a.out = os.path.join("logs", f"phase6_sag_{int(time.time())}.csv")
    return asyncio.run(main_async(a))


if __name__ == "__main__":
    sys.exit(main())
