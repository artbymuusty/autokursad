"""GOREV K -- adaptif alcalma (madde 6) ve zemin guvenlik siniri (madde 7).

Bu testler `_adaptive_descend()`'i DOGRUDAN cagirir: tam bir gorev kosumu
kurmadan, durma kosullarinin her birini ayri ayri sinar.

Neden bu davranislar korunmali: sabit bir iniş irtifasinin isabet etmesi
gereken pencere yalnizca 70 mm genisliginde, PX4'un irtifa hatasi ise
90-290 mm (docs/gorevK-adaptif-alcalma-faz1.md). Yani asagidaki her kural
olculmus bir arizanin karsiligidir, stil tercihi degil.
"""
import math

import pytest

from core.mission.gorev3_pickup import (
    Gorev3PickupPhase,
    ADAPTIVE_DESCENT_GAIN,
    ADAPTIVE_DESCENT_MAX_STEP_M,
    ADAPTIVE_DESCENT_MIN_STEP_M,
    ADAPTIVE_DESCENT_NOSE_FLOOR_M,
    HOOK_VISUAL_ALIGN_ALTITUDE_M,
)
from core.mission.hook_seating import (
    MAGNET_ATTRACT_RANGE_M,
    MAGNET_CAPTURE_RADIUS_M,
    MAGNET_MAX_GAP_M,
    SeatingGeometry,
)
from core.mission.gorev3_pickup import ADAPTIVE_DESCENT_MAGNET_GAP_M


class _Flight:
    """Komut edilen irtifalari kaydeder; baska hicbir sey yapmaz."""
    def __init__(self):
        self.commands = []

    async def goto_position_ned_and_hold(self, n, e, d, yaw, dur):
        self.commands.append({"n": n, "e": e, "alt": -d, "yaw": yaw, "dur": dur})


class _Actuator:
    """Geometriyi ve burun z'sini SENARYODAN uretir.

    `descend(step_m)` cagrisi, aracin inisini burun z'sine ve eksenel
    bosluga birebir yansitir -- gercek kinematik bagintinin ta kendisi:
        nose_z = A + 0.04235 - P     (P inis boyunca sabit)
    yani irtifa dusunce burun da ayni kadar duser.
    """
    def __init__(self, gap_m, nose_z, lateral_m=0.008, tilt_rad=0.0,
                 rel_speed=0.0, geometry_none=False):
        self.gap_m = gap_m
        self.nose_z = nose_z
        self.lateral_m = lateral_m
        self.tilt_rad = tilt_rad
        self.rel_speed = rel_speed
        self.geometry_none = geometry_none
        self.reads = 0

    def descend(self, step_m):
        self.gap_m -= step_m
        self.nose_z -= step_m

    def seating_geometry(self, color):
        self.reads += 1
        if self.geometry_none:
            return None
        return SeatingGeometry(lateral_m=self.lateral_m,
                               insertion_m=-self.gap_m,
                               tilt_rad=self.tilt_rad,
                               rel_speed_mps=self.rel_speed,
                               pose_age_s=0.0)

    def get_hook_world_pose(self):
        if self.geometry_none:
            return None
        return ((0.0, 0.0, self.nose_z + 0.06465), (0.0, 0.0, 0.0, 1.0), 0.0)


def _inisler(flight, start_alt):
    """Yalnizca GERCEKTEN alcaltan komutlar (miknatis bandi tutusu ayni
    irtifayi komut eder, o bir inis adimi degildir)."""
    out, prev = [], start_alt
    for c in flight.commands:
        if c["alt"] < prev - 1e-9:
            out.append(prev - c["alt"])
        prev = c["alt"]
    return out


def _phase(flight, actuator):
    p = Gorev3PickupPhase.__new__(Gorev3PickupPhase)
    p.flight = flight
    p.actuator = actuator
    p.publisher = None
    p._color = "red"
    return p


async def _run(phase, flight, actuator, start_alt=HOOK_VISUAL_ALIGN_ALTITUDE_M):
    """Ucus komutlarini aktuatorun durumuna geri besleyerek kos."""
    real_goto = flight.goto_position_ned_and_hold
    last = {"alt": start_alt}

    async def goto(n, e, d, yaw, dur):
        await real_goto(n, e, d, yaw, dur)
        actuator.descend(last["alt"] - (-d))
        last["alt"] = -d

    flight.goto_position_ned_and_hold = goto
    alt, _reason = await phase._adaptive_descend(1.0, 2.0, 90.0, start_alt)
    return alt


async def _run_ham(phase, flight, actuator, start_alt=HOOK_VISUAL_ALIGN_ALTITUDE_M):
    """_run ile ayni, ama (irtifa, sebep) ciftini dondurur."""
    real_goto = flight.goto_position_ned_and_hold
    last = {"alt": start_alt}

    async def goto(n, e, d, yaw, dur):
        await real_goto(n, e, d, yaw, dur)
        actuator.descend(last["alt"] - (-d))
        last["alt"] = -d

    flight.goto_position_ned_and_hold = goto
    return await phase._adaptive_descend(1.0, 2.0, 90.0, start_alt)


# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kapi_zaten_gecilmisse_hic_alcalmaz():
    """Eksenel kapi baslangicta saglaniyorsa TEK BIR ADIM bile komut edilmez.

    Fazladan inis = ipte gevseklik = zincirin bukulmesi = tilt kapisi olur
    (P3'un ariza modu). 'Zaten yeterli' durumunda hareket etmemek, bu
    mekanizmanin en onemli davranisi."""
    flight, act = _Flight(), _Actuator(gap_m=0.002, nose_z=0.072)
    alt = await _run(_phase(flight, act), flight, act)
    assert flight.commands == []
    assert alt == pytest.approx(HOOK_VISUAL_ALIGN_ALTITUDE_M)


@pytest.mark.asyncio
async def test_oransal_adim_kapiya_yakinsar():
    """420 mm'lik bosluk kazanc 0.7 ile birkac adimda 5 mm kapisina girer."""
    flight, act = _Flight(), _Actuator(gap_m=0.420, nose_z=0.490)
    alt = await _run(_phase(flight, act), flight, act)
    assert flight.commands, "hic adim komut edilmedi"
    # Ilk adim tam olarak oransal olmali (tavan, zemin ve bant bu senaryoda
    # baglayici degil: 0.420*0.7 = 0.294 < 0.30 tavan ve < 0.420-0.04 bant).
    ilk = flight.commands[0]
    beklenen = (
        HOOK_VISUAL_ALIGN_ALTITUDE_M - min(0.420 * ADAPTIVE_DESCENT_GAIN,
                                           ADAPTIVE_DESCENT_MAX_STEP_M))
    assert ilk["alt"] == pytest.approx(beklenen, abs=1e-9)
    # Sonunda eksenel kapi gecilmis olmali.
    assert act.gap_m <= MAGNET_MAX_GAP_M + 1e-9
    assert alt < HOOK_VISUAL_ALIGN_ALTITUDE_M


@pytest.mark.asyncio
async def test_adimlar_kuculerek_gider_asim_yok():
    """Her adim bir oncekinden kucuk olmali; kazanc<1'in tum amaci bu."""
    flight, act = _Flight(), _Actuator(gap_m=0.420, nose_z=0.490)
    await _run(_phase(flight, act), flight, act)
    adimlar = _inisler(flight, HOOK_VISUAL_ALIGN_ALTITUDE_M)
    assert adimlar, "hic inis adimi yok"
    assert adimlar == sorted(adimlar, reverse=True), f"adimlar kuculmuyor: {adimlar}"
    # Burun HICBIR ZAMAN zeminin altina inmemeli.
    assert act.nose_z >= ADAPTIVE_DESCENT_NOSE_FLOOR_M - 1e-9


@pytest.mark.asyncio
async def test_zemin_siniri_yanal_hata_buyukken_durdurur():
    """Yanal hata burnu guverteden YANA dusurmusse eksenel bosluk hic
    kapanmaz; tek koruma zemindir ve burun onun ALTINA inmemelidir.

    Bu tam olarak P3'un olculen arizasi: nose_z = -0.0987 m."""
    # Burun guverteden yana: bosluk 200 mm ama burun zemine yalnizca 30 mm.
    flight, act = _Flight(), _Actuator(gap_m=0.200, nose_z=0.030,
                                       lateral_m=0.064)
    await _run(_phase(flight, act), flight, act)
    assert act.nose_z >= ADAPTIVE_DESCENT_NOSE_FLOOR_M - 1e-9, \
        f"burun zeminin altina indi: {act.nose_z}"
    # Toplam inis, mevcut boslugun degil, ZEMIN PAYININ kadari olmali.
    toplam = HOOK_VISUAL_ALIGN_ALTITUDE_M - flight.commands[-1]["alt"]
    assert toplam <= 0.030 + 1e-9


@pytest.mark.asyncio
async def test_poz_okunamazsa_kor_alcalma_yok():
    """Geometri/poz yoksa hicbir sey komut edilmez. Yokluk 'guvenli' demek
    degildir -- oturma kapisinin kendi kurali da budur."""
    flight, act = _Flight(), _Actuator(gap_m=0.420, nose_z=0.490,
                                       geometry_none=True)
    alt = await _run(_phase(flight, act), flight, act)
    assert flight.commands == []
    assert alt == pytest.approx(HOOK_VISUAL_ALIGN_ALTITUDE_M)


@pytest.mark.asyncio
async def test_kapiya_YETEN_kucuk_adim_atilir():
    """Oransal adim 5 mm esiginin altinda olsa bile, o adim boslugu kapinin
    ICINE sokuyorsa ATILIR.

    Bu, r2/A kosumunda OLCULEN bir kusurun testi: bosluk 6.8 mm iken oransal
    adim 4.76 mm cikmis, kosulsuz min-adim kurali inisi kesmis ve kapi
    ins = -6.8 mm ile 1.8 mm FARKLA kacirilmisti. 6.8 - 4.76 = 2.0 mm, yani
    o adim kapiyi (5.0 mm) TAM DA aciyordu."""
    flight, act = _Flight(), _Actuator(gap_m=0.0068, nose_z=0.0768)
    assert 0.0068 * ADAPTIVE_DESCENT_GAIN < ADAPTIVE_DESCENT_MIN_STEP_M
    await _run(_phase(flight, act), flight, act)
    assert _inisler(flight, HOOK_VISUAL_ALIGN_ALTITUDE_M), "kapiya yeten adim atilmadi"
    assert act.gap_m <= MAGNET_MAX_GAP_M + 1e-9, \
        f"inis bitti ama kapi hala acik: {act.gap_m * 1000:.1f} mm"


@pytest.mark.asyncio
async def test_kapiya_YETMEYEN_kucuk_adim_atilmaz():
    """Zemin payi adimi kapiya yetmeyecek kadar kirpiyorsa durulur --
    yoksa burun bosuna zemine surulur."""
    # Bosluk 100 mm ama zemin payi yalnizca 2 mm: 2 mm'lik adim sonrasi
    # 98 mm bosluk kalir, kapi acilmaz.
    flight, act = _Flight(), _Actuator(gap_m=0.100, nose_z=0.002,
                                       lateral_m=0.064)
    await _run(_phase(flight, act), flight, act)
    assert act.nose_z >= ADAPTIVE_DESCENT_NOSE_FLOOR_M - 1e-9


@pytest.mark.asyncio
async def test_adim_tavani_bozuk_okumayi_sinirlar():
    """Sacma buyuklukte bir bosluk okunursa adim tavani devreye girer."""
    flight, act = _Flight(), _Actuator(gap_m=5.0, nose_z=6.0)
    await _run(_phase(flight, act), flight, act)
    ilk_adim = HOOK_VISUAL_ALIGN_ALTITUDE_M - flight.commands[0]["alt"]
    assert ilk_adim == pytest.approx(ADAPTIVE_DESCENT_MAX_STEP_M)


def test_kazanc_birin_altinda():
    """Kazanc 1'e cikarsa olcum gurultusu dogrudan asima donusur ve asim
    P3'un ariza moduna (gevseklik -> bukulme -> tilt kapisi) yol acar."""
    assert 0.0 < ADAPTIVE_DESCENT_GAIN < 1.0


def test_zemin_siniri_secilmis_bir_sayi_degil():
    """Alt sinir zeminin kendisi; bir 'ayar degeri' haline getirilmemeli."""
    assert ADAPTIVE_DESCENT_NOSE_FLOOR_M == 0.0


def test_min_adim_kapinin_kendi_toleransi():
    assert ADAPTIVE_DESCENT_MIN_STEP_M == MAGNET_MAX_GAP_M


# --------------------------------------------------------------------------
# BAGLANTI TESTLERI -- adaptif inisin ULASTIGI irtifanin fiilen kullanildigini
# ve SALIM REFERANSININ degismedigini kaynak duzeyinde kilitler.
# --------------------------------------------------------------------------
import inspect
import core.mission.gorev3_pickup as _g3

SRC = inspect.getsource(_g3)


def test_tutma_ulasilan_irtifayi_kullaniyor():
    """_start_hold sabit -GOREV3_DESCENT_ALTITUDE_M'i degil, adaptif inisin
    ulastigi irtifayi tutmali. Aksi halde arac inisin hemen ardindan geri
    0.30 m'ye ucar ve tum kademeli is bosa gider."""
    assert "n_, e_, -pickup_alt, aligned_yaw, PICKUP_HOLD_S" in SRC, \
        "_start_hold hala sabit irtifayi tutuyor"


def test_denemeler_arasi_hizalama_ulasilan_irtifada():
    """_on_retry'nin yeniden hizalamasi da ulasilan irtifada kosmali."""
    assert "self._settle_hook_onto(recv_ned, aligned_yaw,\n" \
           "                                                         pickup_alt)" in SRC


def test_salim_referansi_DEGISMEDI():
    """extend_winch_for ve activate_pickup_mechanism hala nominal
    GOREV3_DESCENT_ALTITUDE_M ile cagrilmali.

    NEDEN: adaptif inisin turetmesi 'salim inis boyunca SABIT' on kabulune
    dayaniyor (nose_z = A + 0.04235 - P). Salim ulasilan irtifadan yeniden
    hesaplanirsa fazladan salim komut edilir, O1 kurali geregi buyur, ve
    fazladan salim tam olarak kapiyi bozan gevsekligi uretir."""
    assert "await _extend(GOREV3_DESCENT_ALTITUDE_M)" in SRC
    assert "altitude_m=GOREV3_DESCENT_ALTITUDE_M, on_retry=_on_retry" in SRC


def test_tek_atis_inis_KALDIRILDI():
    """Eski sabit hedefli inis geri gelmemeli."""
    assert "-GOREV3_DESCENT_ALTITUDE_M, aligned_yaw, 6.0" not in SRC
    assert "await self._adaptive_descend(" in SRC


# --------------------------------------------------------------------------
# 3-5 cm MIKNATIS BANDI (operator karari 2026-09-05)
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_miknatis_bandinda_DURULUYOR_ve_alcalmiyor():
    """Bosluk cekim menziline (5 cm) girdiginde inis DURUR ve arac ayni
    irtifayi tutar: kanca orada SERBEST ASILI ve miknatis yanal hatayi
    ancak o rejimde kapatabiliyor. Bant sirasinda ALCALMA KOMUTU OLMAMALI."""
    # Yanal buyuk baslasin ki bant beklemesi erken cikmasin.
    flight, act = _Flight(), _Actuator(gap_m=0.045, nose_z=0.115,
                                       lateral_m=0.040)
    await _run(_phase(flight, act), flight, act)
    # Bant tutusu ayni irtifayi komut eder -> gercek bir inis adimi yok
    # (bandan sonra kapiyi kapatmak icin inilebilir, ama ilk komut TUTUS).
    assert flight.commands, "bant tutusu hic komut etmedi"
    assert flight.commands[0]["alt"] == pytest.approx(HOOK_VISUAL_ALIGN_ALTITUDE_M), \
        "bant tutusu ayni irtifada olmali"


@pytest.mark.asyncio
async def test_bandin_ALTINA_dusulmuyor():
    """Bant henuz kullanilmamisken adim, boslugu bandin altina indirecek
    kadar buyuk olamaz -- yoksa miknatisin serbest-asili rejimde calisma
    firsati atlanir ve kanca dogrudan guverteye dayanir (surtunme rejimi,
    olculdu: 7 adimda 33.8 -> 33.4 mm)."""
    flight, act = _Flight(), _Actuator(gap_m=0.300, nose_z=0.370,
                                       lateral_m=0.040)
    await _run(_phase(flight, act), flight, act)
    ilk = HOOK_VISUAL_ALIGN_ALTITUDE_M - flight.commands[0]["alt"]
    # 0.300*0.7 = 0.210 ama bant kirpmasi 0.300-0.040 = 0.260; kucuk olan 0.210.
    assert ilk == pytest.approx(min(0.300 * ADAPTIVE_DESCENT_GAIN,
                                    0.300 - ADAPTIVE_DESCENT_MAGNET_GAP_M), abs=1e-9)


def test_bant_hedefi_operatorun_3_5_cm_bandinda():
    assert 0.03 <= ADAPTIVE_DESCENT_MAGNET_GAP_M <= 0.05
    assert ADAPTIVE_DESCENT_MAGNET_GAP_M < MAGNET_ATTRACT_RANGE_M


# --------------------------------------------------------------------------
# DEVRILME KORUMASI ve SON BOSLUK HEDEFI (2026-09-05 kosumunda olculdu)
# --------------------------------------------------------------------------
from core.mission.gorev3_pickup import ADAPTIVE_DESCENT_TARGET_GAP_M
from core.mission.hook_seating import MAGNET_MAX_TILT_RAD


@pytest.mark.asyncio
async def test_devrilmis_kanca_inis_kararina_temel_olamaz():
    """Devrilmis kancanin burnu, govdesi yattigi icin guverte duzlemine yakin
    okunabilir ve eksenel kapi YANLISLIKLA 'gecildi' der.

    Olculdu (2026-09-05, deneme 2 ve 3): 0.90 m irtifada, tek adimda,
    'KAPI GECILDI ... tilt=64.4 deg'. 0.90 m'de burnun guvertede olmasi
    fiziksel olarak imkansiz."""
    flight, act = _Flight(), _Actuator(gap_m=-0.0043, nose_z=0.070,
                                       lateral_m=0.017,
                                       tilt_rad=math.radians(64.4))
    phase = _phase(flight, act)
    alt, reason = await phase._adaptive_descend(1.0, 2.0, 90.0,
                                                HOOK_VISUAL_ALIGN_ALTITUDE_M)
    assert reason == "devrilmis_kanca", f"devrilme yakalanmadi: {reason}"
    # GOREV M: artik once torkla dogrultma deneniyor -- o AYNI irtifada bir
    # TUTUS komut eder. Yasak olan sey ALCALMAK.
    assert _inisler(flight, HOOK_VISUAL_ALIGN_ALTITUDE_M) == [], \
        "devrilmis kancayla ALCALMA komut edildi"


@pytest.mark.asyncio
async def test_tork_dogrultursa_inis_DEVAM_EDER():
    """GOREV M: devrilme gorulunce deneme hemen atilmiyor -- tork kancayi
    kapinin icine sokarsa inis kaldigi yerden surer."""
    flight, act = _Flight(), _Actuator(gap_m=0.200, nose_z=0.270,
                                       lateral_m=0.008,
                                       tilt_rad=math.radians(40.0))

    # Tork acilinca kanca dogruluyor: aktuator torku dinlesin.
    async def set_magnet_torque(enabled):
        if enabled:
            act.tilt_rad = math.radians(3.0)
        return True
    act.set_magnet_torque = set_magnet_torque

    phase = _phase(flight, act)
    alt, reason = await _run_ham(phase, flight, act)
    assert reason != "devrilmis_kanca", f"tork dogrulttu ama inis durdu: {reason}"
    assert _inisler(flight, HOOK_VISUAL_ALIGN_ALTITUDE_M), "inis devam etmedi"


@pytest.mark.asyncio
async def test_burun_guverteye_DAYANDIRILMIYOR():
    """Inis, boslugu 0'a kadar kapatmamali: burun guvertede SIKISIK iken
    miknatisin yanal kuvveti kancayi kaydirmiyor, temas noktasi etrafinda
    DEVIRIYOR (2026-09-05: egim 0.9 -> 34.7 -> 42.0 derece)."""
    flight, act = _Flight(), _Actuator(gap_m=0.200, nose_z=0.270,
                                       lateral_m=0.008)
    await _run(_phase(flight, act), flight, act)
    assert act.gap_m >= ADAPTIVE_DESCENT_TARGET_GAP_M - 1e-9, \
        f"burun hedef boslugun altina indi: {act.gap_m * 1000:.2f} mm"


def test_son_bosluk_hedefi_kapinin_ICINDE_ve_temasin_USTUNDE():
    assert 0.0 < ADAPTIVE_DESCENT_TARGET_GAP_M < MAGNET_MAX_GAP_M
    assert ADAPTIVE_DESCENT_TARGET_GAP_M == MAGNET_MAX_GAP_M / 2.0


# --------------------------------------------------------------------------
# PENCERE VINCI TEKRAR SALMAZ (operator karari 2026-09-05)
# --------------------------------------------------------------------------

def test_yakalama_penceresi_vinci_TEKRAR_SALMIYOR():
    """Adaptif inis burnu guvertenin 4.5 mm USTUNDE, dort kapinin da
    gecilebildigi bir durumda birakiyor:
        lat=16.0mm (<=17.5)  ins=-4.5mm (>=-5.0)  tilt=2.7deg (<=8)
    Pencerede vincin tekrar salinmasi burnu guverteye indiriyor
    (ins +1.1 -> +2.5 mm) ve miknatis onu temas noktasi etrafinda deviriyor:
    olculdu 9.4 -> 15.4 -> 18.8 -> 21.4 -> 21.7 derece; bes ornegin BESI de
    yalnizca egim kapisindan dondu (yanal ve eksenel 0 red).
    Temas hic olusmazsa kaldirac da olusmaz."""
    assert "extend_winch=False)" in SRC, \
        "pencere hala vinci tekrar saliyor"


def test_aktuator_salimi_atlayabiliyor():
    """extend_winch parametresi gercekten var ve varsayilani ESKI davranis."""
    import inspect as _i
    from gz_system.gz_payload_actuator import GzPayloadActuator
    sig = _i.signature(GzPayloadActuator.activate_pickup_mechanism)
    assert "extend_winch" in sig.parameters
    assert sig.parameters["extend_winch"].default is True, \
        "varsayilan eski davranis olmali -- baska cagiranlar bozulmasin"


# --------------------------------------------------------------------------
# KILIT SONRASI DOGRULAMA, DENEME BUTCESININ DISINDA (2026-09-05)
# --------------------------------------------------------------------------

def test_dogrulama_deneme_butcesinin_DISINDA():
    """Butcenin amaci BASARISIZ bir denemeyi kesmektir, basarilmis birini
    atmak degil.

    OLCULDU (demo_20260905_172017, deneme 1): kanca gercekten kilitlendi --
        MAGNET_LOCKED lat=15.9mm ins=+0.2mm tilt=4.7deg dwell 0.61 s
        SERVO3 KAVRAMA ... [HOOK] LOCKED (payload_blue) -- yuk ipte
    -- ve dogrulama tirmanisi baslarken 60 s doldu; faz BASARILMIS almayi
    'basarisiz' sayip bastan denedi."""
    # _attempt kilit onaylaninca donmeli (dogrulama govdesini TASIMAMALI).
    assert "_verify_lift" in SRC, "dogrulama ayri bir fonksiyona alinmamis"
    # dogrulama KENDI zaman asimiyla, wait_for icinde kosmali
    assert "_verify_lift(attempt), GOREV3_PICKUP_VERIFY_TIMEOUT_S" in SRC
    # ve deneme butcesi hala yakalamayi sinirlamali (3 x 60 s spec'i)
    assert "_attempt(attempt),\n                                            GOREV3_PICKUP_ATTEMPT_TIMEOUT_S" in SRC


def test_dogrulama_zaman_asimi_tanimli_ve_makul():
    from core.config.parameters import (GOREV3_PICKUP_VERIFY_TIMEOUT_S,
                                        GOREV3_PICKUP_ATTEMPT_TIMEOUT_S)
    assert 0 < GOREV3_PICKUP_VERIFY_TIMEOUT_S < GOREV3_PICKUP_ATTEMPT_TIMEOUT_S
