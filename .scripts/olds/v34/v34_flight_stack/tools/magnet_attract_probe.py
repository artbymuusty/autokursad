#!/usr/bin/env python3
"""GOREV K / D: manyetik cekim OLCUMU -- kontrollu A/B, gorevden bagimsiz.

NEDEN VAR: operator "cekim, J demosundaki 41-72 mm'lik yanal hatayi
GERCEKTEN cozuyor mu, varsaymayin olcun" dedi. Tam gorev kosumu bu olcumu
vermiyor: dort kosum ust uste alma penceresine girmeden once yuku goruntude
bulamadi (tespit oynakligi), yani cekim kodu bir kez bile calismadi.

Bu arac pencereyi DOGRUDAN kuruyor: bir yuku yere birakir, aracin kancasini
istenen yanal hatayla (varsayilan 41 mm -- olculen ariza bandinin alt ucu)
yukun uzerine getirir, vinci salar ve oturma dongusunu KOSAR. Ayni sey iki
kez yapilir:
    KONTROL : on_attract=None  -> cekim yok (bugunku davranis)
    CEKIM   : on_attract=cb    -> cekim acik
Ikisinin seat_trace'i (yanal hata zaman serisi) yan yana raporlanir.

SITL'in ZATEN CALISIYOR olmasi gerekir (safe_sitl_launcher.sh).

    python3 tools/magnet_attract_probe.py --lateral-mm 41
"""
import argparse
import asyncio
import math
import statistics
import sys
import time

from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw

from gz_system.gz_pose_monitor import GzPoseMonitor
from gz_system.gz_payload_actuator import (
    GzPayloadActuator, PAYLOAD_MODEL, VEHICLE_MODEL_NAME, HOOK_WINCH_RETRACT_M,
)
from core.mission.gorev3_pickup import (
    HOOK_ALIGN_MAX_CORRECTIONS, HOOK_SETTLE_GAIN, HOOK_SETTLE_WAIT_S,
    HOOK_PAYOUT_SETTLE_S,
)
from core.config.parameters import (
    GOREV3_MAGNET_ATTRACT_GAIN, GOREV3_MAGNET_ATTRACT_MAX_STEP_M,
    GOREV3_DESCENT_ALTITUDE_M,
)

RENK = "blue"          # KIRMIZI_UCGEN'e birakilan yuk -- gorevdeki alma hedefi
YAW = 0.0


def log(msg):
    print(f"[PROBE {time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ==========================================================================
# K1 -- YUKU DETERMINISTIK VE DIK YERLESTIR (dusurme YOK)
# ==========================================================================
# v1 yuku 0.55 m'den birakiyordu ve durusu dogrulamiyordu. Olculdu
# (docs/gorevK-D-probe-sonuc.md): payload_blue YAN YATTI -- yerel +Z ekseni
# dunyada (+0.995, +0.103, 0.000), yani dikeyden 90.0 derece. Yuva agzi
# yatay olunca oturma geometrisi tilt 179.6 deg okudu (kapi 8 deg) ve
# olcum daha baslamadan gecersizlesti.
#
# NOT: bu bir GOREV kusuru DEGIL. 202 gercek birakmanin egimi tarandi:
# ortanca 0.2 deg, max 6.7 deg, 15 derecenin ustunde 0/202. Gorevdeki
# birakma koreografisi (RELEASE_HOLD + aim-offset) yuku duz birakiyor;
# dusuren ve dogrulamayan sey probe'du.
#
# Cozum: dusurmek yerine Gazebo'ya DOGRUDAN poz yaziyoruz
# (/world/<w>/set_pose, gz.msgs.Pose). Boylece K3 de kendiliginden
# kapaniyor -- taklit edilecek bir birakma koreografisi kalmiyor.
async def yuku_yerlestir(dunya, model, x, y, z=0.026):
    """Yuku verilen noktaya DIK olarak koy. Kuaterniyon birim = duz."""
    istek = (f'name: "{model}" '
             f'position {{ x: {x} y: {y} z: {z} }} '
             f'orientation {{ x: 0 y: 0 z: 0 w: 1 }}')
    pr = await asyncio.create_subprocess_exec(
        "gz", "service", "-s", f"/world/{dunya}/set_pose",
        "--reqtype", "gz.msgs.Pose", "--reptype", "gz.msgs.Boolean",
        "--timeout", "3000", "--req", istek,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await pr.communicate()
    return b"true" in (out or b"").lower()


async def durusu_dogrula(monitor, model, tol_deg=5.0):
    """Yerlestirmeden sonra GERCEKTEN dik mi -- varsayma, olc."""
    q = monitor._quats.get(model)
    if q is None:
        return None
    x, y, z, w = q
    zz = 1 - 2 * (x * x + y * y)
    egim = math.degrees(math.acos(max(-1.0, min(1.0, zz))))
    return egim if egim <= tol_deg else egim


class Tutucu:
    """Arka planda ayni setpoint'i tekrarlayan basit tutma dongusu.

    PX4 ~500 ms setpoint'siz kalinca Offboard'dan duser; gorev katmani da
    ayni nedenle goto_position_ned_and_hold kullaniyor.
    """

    def __init__(self, drone):
        self.drone = drone
        self.n = self.e = 0.0
        self.d = -GOREV3_DESCENT_ALTITUDE_M
        self._task = None

    async def _loop(self):
        while True:
            await self.drone.offboard.set_position_ned(
                PositionNedYaw(self.n, self.e, self.d, YAW))
            await asyncio.sleep(0.1)

    def hedef(self, n, e, d=None):
        self.n, self.e = n, e
        if d is not None:
            self.d = d

    async def basla(self, n, e, d):
        self.hedef(n, e, d)
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def dur(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None



async def _tilt_tanisi(actuator, monitor, etiket):
    """P2: oturma kapisinin gordugu her bileseni AYNI ANDA yaz."""
    def _dikeyden(q):
        if q is None:
            return None
        x, y, z, w = q
        return math.degrees(math.acos(max(-1.0, min(1.0, 1 - 2 * (x * x + y * y)))))

    hp = actuator.get_hook_world_pose()
    hook_pos, hook_q = (hp[0], hp[1]) if hp else (None, None)
    pay_q = monitor._quats.get(PAYLOAD_MODEL % RENK)
    pay_pos = monitor.get(PAYLOAD_MODEL % RENK)
    ws = actuator.winch_state() or {}
    geom = actuator.seating_geometry(RENK)

    log(f"[TILT-TANI] {etiket}")
    log(f"   kanca  poz={None if hook_pos is None else tuple(round(v,4) for v in hook_pos)}"
        f"  quat={None if hook_q is None else tuple(round(v,4) for v in hook_q)}"
        f"  dikeyden={None if _dikeyden(hook_q) is None else round(_dikeyden(hook_q),1)} deg")
    log(f"   yuva   poz={None if pay_pos is None else tuple(round(v,4) for v in pay_pos)}"
        f"  quat={None if pay_q is None else tuple(round(v,4) for v in pay_q)}"
        f"  dikeyden={None if _dikeyden(pay_q) is None else round(_dikeyden(pay_q),1)} deg")
    log(f"   vinc   achieved={ws.get('achieved_m')}  span={ws.get('span_m')}"
        f"  fold={ws.get('fold_deg')}  nose_z={ws.get('nose_z_m')}")
    if geom is not None:
        log(f"   GEOMETRI lateral={geom.lateral_m*1000:.1f} mm  "
            f"insertion={geom.insertion_m*1000:+.1f} mm  "
            f"tilt={math.degrees(geom.tilt_rad):.1f} deg")
    else:
        log("   GEOMETRI: None")


async def pencere(actuator, drone, tutucu, monitor, lateral_m, cekim: bool,
                  timeout_s: float):
    """Tek bir oturma penceresi kos ve seat_trace dondur."""
    # Hedef: kanca, yuvanin ekseninden `lateral_m` KUZEYDE dursun.
    yuk = monitor.get(PAYLOAD_MODEL % RENK)
    arac = monitor.get(VEHICLE_MODEL_NAME)
    if yuk is None or arac is None:
        log("HATA: yuk/arac pozu okunamadi")
        return None
    # ======================================================================
    # K2 -- KONUMLANDIRMA KAPALI CEVRIM
    # ======================================================================
    # v1 tek atislik bir NED hedefi hesapliyordu:
    #     hedef = EKF_NED + (Gazebo dunya deltasi) - kanca_ofseti + lateral
    # Iki hatasi vardi:
    #  1) EKF NED'i ile Gazebo dunya deltasini karistiriyordu. O5'te
    #     olculdu: EKF <-> gercek farki 0.09-0.29 m ve SABIT DEGIL. Acik
    #     cevrim bu hatayi oldugu gibi devraliyor.
    #  2) Kanca ofsetini TEK ORNEKTEN okuyordu; kanca sarkarken o deger
    #     salinim iceriyor (v1'de iki kol (-0.089,-0.014) ve
    #     (-0.064,-0.029) okudu, yani 25 mm fark).
    # Olculen sonuc: istenen 41 mm yerine 192-229 / 96-109 mm.
    #
    # Simdi: EKF hic kullanilmiyor. Her adimda kancanin yuvaya gore GERCEK
    # yanal hatasi Gazebo'dan okunuyor (oturma kapisinin baktigi ayni
    # kaynak) ve setpoint o hatayi kapatacak sekilde duzeltiliyor. Kapali
    # cevrim, EKF sapmasini ve sarkac salinimini birlikte yutar.
    pv = await drone.telemetry.position_velocity_ned().__aiter__().__anext__()
    hedef_n, hedef_e = pv.position.north_m, pv.position.east_m
    # P2 (2026-09-05): 0.30 m'ye ERKEN INIS KALDIRILDI.
    # v4'te sira soyleydi: 0.30 m'ye in -> vinci sal -> hizala. Bu, 0.30 m
    # irtifada 0.31 m salim demek: kanca 0.25 m uzunlugunda, yani burun
    # ZEMININ ALTINA suruluyor. Olculdu (p41h): pencereye gelindiginde yuk
    # 90 dereceye DEVRILMIS ve 0.3 m kaymis, kanca zinciri patlamis
    # (poz km olceginde, fold 134 deg, span 0.127 yerine 0.235).
    # 165-169 derecelik "tilt anomalisi" bunun sonucuydu -- probe ile gorev
    # arasinda bir MODEL farki degil, probe'un kancayi yere surmesi.
    #
    # GOREVIN GERCEK SIRASI (gorev3_pickup.py:1071-1107): vinc 0.90 m'de
    # salinir ("ARAC HALA 0.90 m'de, kanca serbest asili kalacak"),
    # hizalama orada yapilir, SONRA "SAF DIKEY" inilir. Probe artik ayni
    # sirayi izliyor. 0.90 m'de burun 0.90 - 0.25 - 0.31 = 0.34 m'de,
    # yani serbest asili.
    await tutucu.basla(hedef_n, hedef_e, -0.9)
    await asyncio.sleep(5.0)

    # ======================================================================
    # VINCI ONCE SAL, SONRA HIZALA -- gorevin OLCTUGU sira.
    # ======================================================================
    # v2/v3'te hizalama dongusu vinc CEKILIYKEN kosuyordu, yani kanca
    # serbest sarkiyordu. Olculdu (bu kosum): hizalama sirasinda tilt 78.9
    # dereceye ciktu ve arac 0.760 m/s ile hareket halindeydi; 200 mm'lik
    # bir duzeltme sarkaci uyandiriyor, sonraki okuma salinimi olcuyor ve
    # dongu kendi uyandirdigi salinimi kovaliyordu.
    #
    # gorev3_pickup.py bu tuzagi zaten kaydetmis: "Ilk surumde sira tersti:
    # once hizala, sonra alma mekanizmasini cagir -- ve alma mekanizmasi
    # ilk isi olarak vinci saliyordu. Yani hizalama kanca HAVADAYKEN
    # olculuyor, sonra kanca asagi iniyor, o inis sirasinda salliniyor ve
    # yukun YANINA konuyordu." Cozum orada da ayni: once sal, kanca
    # guverteye otursun, SONRA hizala -- surtunme sarkaci sonumler.
    await actuator.extend_winch_for(GOREV3_DESCENT_ALTITUDE_M)
    await asyncio.sleep(HOOK_PAYOUT_SETTLE_S)

    log(f"{'CEKIM' if cekim else 'KONTROL'}: kapali cevrim hizalama basliyor "
        f"(vinc SALINMIS, istenen yanal {lateral_m*1000:.0f} mm)")
    son_hata = None
    for it in range(1, HOOK_ALIGN_MAX_CORRECTIONS + 1):
        # (d_east, d_north): kanca burnundan yuva eksenine dunya vektoru.
        # Arac NED'i Gazebo dunyasiyla eksen-hizali (aktuator docstring'i,
        # ucusta dogrulanmis), yani north += d_north ; east += d_east.
        off = actuator.hook_to_receiver_offset_world(RENK)
        if off is None:
            await asyncio.sleep(0.5)
            continue
        hata_n, hata_e = off[1], off[0]
        # Istenen: kanca yuvanin `lateral_m` KUZEYINDE dursun, yani
        # kancadan yuvaya vektor (dogu=0, kuzey=-lateral_m) olmali.
        duz_n = hata_n + lateral_m
        duz_e = hata_e
        son_hata = math.hypot(duz_n, duz_e)

        # AKIL SAGLIGI KAPISI: 1 m'den buyuk bir "duzeltme" okuma hatasidir.
        # v2'de bu yoktu ve tek bir kotu okuma araci 400 km oteye ucurdu
        # (setpoint +71393, -423256; artik 178 844 893 mm).
        # P1: esik 1.0 -> 2.0 m. Kapinin isi 178 milyon mm'lik cop okumayi
        # (v2'de araci 400 km ucuran sey) yakalamak; mesru bir baslangic
        # hatasini degil. 2 m hala cop okumadan mertebelerce kucuk.
        if son_hata > 2.0:
            log(f"  it={it}: artik {son_hata*1000:.0f} mm -- OKUMA GECERSIZ, "
                f"duzeltme UYGULANMIYOR")
            await asyncio.sleep(HOOK_SETTLE_WAIT_S)
            continue
        if son_hata <= 0.004:
            log(f"  hizalama yakinsadi: it={it} artik={son_hata*1000:.1f} mm")
            break

        # KAZANC ve BEKLEME GOREVIN OLCTUGU DEGERLER.
        # v2 kazanc 0.6 + 0.5 s bekleme kullaniyordu: duzeltme uygulanip
        # aracin VARMASI BEKLENMEDEN yenisi ekleniyordu, yani setpoint
        # birikiyordu (integrator windup) ve dongu iraksadi.
        # gorev3_pickup.py bu tuzagi zaten olcmus: "dead-beat tek adimda
        # asiyor -- 93 -> 131 -> 68 -> 68 -> 48 -> 78 mm, yakinsamiyor",
        # ve cozumu kazanc 0.5 + her adimdan sonra sarkacin durmasini
        # beklemek (olculen periyot 1.078 s, HOOK_SETTLE_WAIT_S ~3 periyot).
        adim_n = duz_n * HOOK_SETTLE_GAIN
        adim_e = duz_e * HOOK_SETTLE_GAIN
        hedef_n += adim_n
        hedef_e += adim_e
        tutucu.hedef(hedef_n, hedef_e)
        log(f"  it={it:2d} artik={son_hata*1000:6.1f} mm  adim=({adim_n*1000:+6.1f},"
            f"{adim_e*1000:+6.1f}) mm")
        await asyncio.sleep(HOOK_SETTLE_WAIT_S)
    else:
        log(f"  UYARI: hizalama yakinsamadi, artik="
            f"{son_hata*1000 if son_hata is not None else float('nan'):.1f} mm")
    await asyncio.sleep(2.0)                       # sarkac sonumlensin


    async def _on_attract(dn, de, dist_m):
        step_n = dn * GOREV3_MAGNET_ATTRACT_GAIN
        step_e = de * GOREV3_MAGNET_ATTRACT_GAIN
        mag = math.hypot(step_n, step_e)
        if mag > GOREV3_MAGNET_ATTRACT_MAX_STEP_M and mag > 0:
            k = GOREV3_MAGNET_ATTRACT_MAX_STEP_M / mag
            step_n *= k
            step_e *= k
        tutucu.hedef(tutucu.n + step_n, tutucu.e + step_e)
        log(f"  cekim adimi: d={dist_m*1000:5.1f} mm  adim=({step_n*1000:+5.1f}, "
            f"{step_e*1000:+5.1f}) mm")

    # ======================================================================
    # P2 -- TILT ANOMALISI TANISI (2026-09-05)
    # ======================================================================
    # v4'te oturma kapisi kanca HAREKETSIZKEN tilt 165-169 deg okudu; ayni
    # kapi gercek gorevde 0.1-0.5 deg okuyor. Fark kapanmadan A/B anlamsiz.
    # Burada, kapinin baktigi ANIN ham bilesenleri yan yana yaziliyor:
    # kanca kuaterniyonu, yuva kuaterniyonu, vinc achieved_m, burun dunya
    # z'si ve geometrinin kendi tilt'i. Boylece "kanca gercekten mi
    # devrilmis" ile "geometri baska bir referansla mi hesapliyor"
    # ayrilabilir -- tahminle degil sayiyla.
    # Hizalama bitti -> SAF DIKEY in (yanal surukleme yok).
    log(f"hizalandi, {GOREV3_DESCENT_ALTITUDE_M:.2f} m alma irtifasina saf dikey iniliyor")
    tutucu.hedef(tutucu.n, tutucu.e, -GOREV3_DESCENT_ALTITUDE_M)
    await asyncio.sleep(6.0)

    await _tilt_tanisi(actuator, monitor, "pencere oncesi")

    seated = await actuator._await_seating(RENK, timeout_s,
                                           on_attract=_on_attract if cekim else None)
    rapor = actuator.last_seating_report or {}
    await actuator.set_winch(HOOK_WINCH_RETRACT_M)
    tutucu.hedef(tutucu.n, tutucu.e, -1.5)
    await asyncio.sleep(5.0)
    return {"seated": seated, "rapor": rapor}


def ozet(ad, sonuc):
    if not sonuc:
        return f"{ad}: OLCULEMEDI"
    r = sonuc["rapor"]
    tr = r.get("seat_trace") or []
    lats = [s[2] for s in tr if len(s) > 2 and s[2] is not None]
    ma = r.get("magnet_attract") or {}
    if not lats:
        return f"{ad}: seated={sonuc['seated']} -- seat_trace bos"
    return (f"{ad}: seated={sonuc['seated']}  ornek={len(lats)}  "
            f"yanal ilk={lats[0]:.1f} son={lats[-1]:.1f} min={min(lats):.1f} "
            f"medyan={statistics.median(lats):.1f} mm  "
            f"17.5mm_alti={sum(1 for v in lats if v <= 17.5)}/{len(lats)}  "
            f"cekim={ma.get('engaged')} adim={ma.get('steps')}")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="udp://:14540")
    ap.add_argument("--lateral-mm", type=float, default=41.0)
    ap.add_argument("--timeout", type=float, default=25.0)
    ap.add_argument("--world", default="default")
    args = ap.parse_args()

    monitor = GzPoseMonitor()
    await monitor.start()
    actuator = GzPayloadActuator("/v34/set_payload_state", pose_monitor=monitor)

    drone = System()
    await drone.connect(system_address=args.url)
    async for st in drone.core.connection_state():
        if st.is_connected:
            break
    async for h in drone.telemetry.health():
        if h.is_global_position_ok and h.is_home_position_ok:
            break
    log("baglandi")

    await drone.action.set_takeoff_altitude(2.0)
    await drone.action.arm()
    await drone.action.takeoff()
    async for p in drone.telemetry.position():
        if p.relative_altitude_m >= 1.8:
            break
    await asyncio.sleep(3.0)
    log("2 m'de")

    tutucu = Tutucu(drone)
    pv = await drone.telemetry.position_velocity_ned().__aiter__().__anext__()
    await drone.offboard.set_position_ned(
        PositionNedYaw(pv.position.north_m, pv.position.east_m, -2.0, YAW))
    try:
        await drone.offboard.start()
    except OffboardError as e:
        log(f"offboard baslatilamadi: {e}")
        return 1
    await tutucu.basla(pv.position.north_m, pv.position.east_m, -0.55)
    await asyncio.sleep(8.0)
    # Birakma HALA GEREKLI: yuk dunyaya DetachableJoint ile bagli ve
    # ayrilmadan set_pose ile tasinamaz. Ama NEREYE dustugu artik
    # ONEMSIZ -- asagidaki K1 yerlestirmesi konumu da durusu da eziyor.
    log("0.55 m'de -- yuk AYIRILIYOR (dustugu yer onemsiz, yerlestirilecek)")
    await actuator.release_payload_at_kirmizi_ucgen()
    await asyncio.sleep(4.0)
    tutucu.hedef(tutucu.n, tutucu.e, -1.5)
    await asyncio.sleep(4.0)

    # ------------------------------------------------------------------
    # K1: yuku DUSURMEDEN, dogrudan ve DIK yerlestir; sonra durusu OLC.
    # ------------------------------------------------------------------
    arac0 = monitor.get(VEHICLE_MODEL_NAME)
    if arac0 is None:
        log("HATA: arac pozu okunamadi -- yerlestirme yapilamiyor")
        return 1
    # P1 (2026-09-05): 1.0 m -> 0.15 m.
    # v4'te yuk aracin 1.0 m kuzeyine konuyordu, yani kapali cevrim daha
    # ilk iterasyonda ~1.18 m'lik bir "hata" goruyordu ve asagidaki akil
    # sagligi kapisi (o zaman 1.0 m) bunu COP OKUMA sanip her duzeltmeyi
    # blokluyordu. Kapi yanlis calismiyordu; kurulum kapinin altina
    # sigmiyordu. 0.40 m: kapinin (2.0 m) rahat altinda ama kanca
    # hizalama sirasinda yuke carpacak kadar yakin degil.
    hedef_x, hedef_y = arac0[0], arac0[1] + 0.40
    ok = await yuku_yerlestir(args.world, PAYLOAD_MODEL % RENK, hedef_x, hedef_y)
    log(f"yuk yerlestirildi ({hedef_x:+.3f}, {hedef_y:+.3f}) -> servis={ok}")
    await asyncio.sleep(2.0)
    egim = await durusu_dogrula(monitor, PAYLOAD_MODEL % RENK)
    yuk = monitor.get(PAYLOAD_MODEL % RENK)
    log(f"yuk yerde: {yuk}  DURUS egimi={egim if egim is None else round(egim,1)} deg")
    if egim is None or egim > 5.0:
        log("HATA: yuk DIK degil -- olcum gecersiz olurdu, durduruluyor")
        return 1

    # Araci yukun yanina getir (kaba), kapali cevrim gerisini halleder.
    pv0 = await drone.telemetry.position_velocity_ned().__aiter__().__anext__()
    tutucu.hedef(pv0.position.north_m + (hedef_y - arac0[1]),
                 pv0.position.east_m + (hedef_x - arac0[0]), -1.5)
    await asyncio.sleep(6.0)

    lateral = args.lateral_mm / 1000.0
    kontrol = cekimli = None
    try:
        kontrol = await pencere(actuator, drone, tutucu, monitor, lateral, False, args.timeout)
        log(ozet("KONTROL", kontrol))
        cekimli = await pencere(actuator, drone, tutucu, monitor, lateral, True, args.timeout)
        log(ozet("CEKIM  ", cekimli))
    finally:
        # VINC HER HALUKARDA TOPLANIR. Bu satirin yoklugu 2026-09-05'te
        # Gazebo'yu cokerttti: probe ucus ortasinda oldurulunce arac
        # offboard'da setpoint'siz kalip failsafe ile indi, VINC ACIKTI ve
        # kanca inis takimindan once yere degip prizmatik eklemi ezdi ->
        # kisitlama infilaki -> "ODE INTERNAL ERROR 1: assertion aabbBound
        # ... failed in collide()". Ayni sebep gercek gorevde de gecerli:
        # inisden once vinc toplanmali.
        try:
            await actuator.set_winch(HOOK_WINCH_RETRACT_M)
            log("vinc toplandi (finally)")
        except Exception:  # noqa: BLE001
            pass

    print("\n================ SONUC ================", flush=True)
    print(ozet("KONTROL (cekim yok)", kontrol), flush=True)
    print(ozet("CEKIM   (5 cm menzil)", cekimli), flush=True)

    await tutucu.dur()
    try:
        await drone.offboard.stop()
    except OffboardError:
        pass
    await drone.action.land()
    await monitor.stop()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
