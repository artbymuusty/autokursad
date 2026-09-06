"""
GOREV I / B-S3 -- KANCA OFSETI TUM GORSEL ISTEN SONRA UYGULANIR.

OLCULEN KUSUR: ofset gorsel islerden ONCE uygulaniyordu. Ofsetten sonra
kamera yuvadan 0.175 + 0.085 = 0.260 m ileride kalir; 0.30 m'de bu
    0.260 * 539.9 / 0.28 = 501 px
eder ve yari-kadraj yalnizca 480 px. Hedef KADRAJ DISINA cikiyor, ardindan
gelen her gorsel adim bakabilecegi bir yuk bulamiyordu (olculdu: 0.30 m'de
30 yinelemede 7 tespit).

Bu dosya SIRAYI kilitler. Aritmetik tek basina yetmez -- kod yolunda
ofsetten sonra gizli bir gorsel adim kalmadigini kanitlamak gerekir; bu
testin tek isi odur.
"""
import inspect
import re

import pytest

from core.mission import gorev3_pickup as gp


SRC = inspect.getsource(gp.Gorev3PickupPhase.run)


def _idx(pattern):
    m = re.search(pattern, SRC)
    assert m, f"kalip bulunamadi: {pattern}"
    return m.start()


# Ofsetin uygulandigi an: "after_visual_work" isaretli yayin.
OFFSET = r'"after_visual_work": True'

# Ofsetten SONRA gorunmemesi gereken gorsel adimlar.
GORSEL = {
    "ilk ortalama (1.2 m)":      r"go_to_and_center\(\s*\n?\s*self\._rect_class, altitude_m=HOOK_ALIGN_ALTITUDE_M",
    "ikinci ortalama (yaklasma irtifasi)": r"go_to_and_center\(\s*\n?\s*self\._rect_class, altitude_m=_approach_alt",
    "piksel sapma olcumu":       r"_rect_pixel_offset\(\)",
    "gorsel kanca hizalamasi":   r"aligner\.align\(",
}


@pytest.mark.parametrize("ad,kalip", sorted(GORSEL.items()))
def test_her_gorsel_adim_ofsetten_ONCE_gelir(ad, kalip):
    assert _idx(kalip) < _idx(OFFSET), (
        f"{ad} kanca ofsetinden SONRA calisiyor -- 501 px kusuru geri geldi")


def test_ofset_ANA_YOLDA_HIC_uygulanmiyor():
    """GOREV R (2026-09-06): ADIM 5'in kanca ofseti KALDIRILDI.

    Bu test eskiden "ofset TEK KEZ uygulanir" diyordu ve o zamanki dogruydu.
    GOREV Q kok nedeni buldu: ADIM 4b (VisualHookAligner.align) KANCA
    referansli -- visual_alignment.py:64 hatayi (recv - hook) olarak
    donduruyor ve align() bunu araca uyguluyor. Yani yakinsadigi anda kanca
    ZATEN yuvanin uzerinde; ofseti tekrar uygulamak onu 175 mm oteye
    tasiyordu.
    OLCULDU (5 kosum / 12 deneme): hizalama kancayi 6.5-29.7 mm'ye
    getiriyordu, settle aninda kanca 184.6-235.0 mm otedeydi; sicrama
    10/10 ornekte POZITIF, ortanca +201.9 mm.

    ADIM 5 SILINMEDI: ikinci isi (hizalama irtifasina cikis) GEREKLI --
    align() araci 0.30 m'de birakiyor, adaptif inisin alcalacak yeri olmali.
    Kaldirilan yalnizca YATAY OTELEME."""
    assert SRC.count('"hook_offset_applied"') == 0, \
        "ana yolda kanca ofseti hala uygulaniyor"
    assert '"align_altitude_restored"' in SRC, "ADIM 5'in irtifa isi kaybolmus"
    assert "_hn, _he = n0, e0" in SRC, "yatay konum korunmuyor"


def test_reacquire_dalindaki_ofset_KORUNUYOR():
    """Reacquire dali ADIM 4b'den ONCE calisiyor ve orada referans hala
    KAMERA: go_to_and_center kamerayi hedefe koyuyor, _rect_pixel_offset'in
    want_y'si de kancanin hedefte olmasini bekliyor. O ofset DOGRU."""
    assert SRC.count("_body_to_ned(HOOK_BODY_OFFSET_FORWARD_M, 0.0)") == 1, \
        "reacquire dalindaki mesru ofset de kaldirilmis olabilir"


def test_gorsel_hizalama_YAKLASMA_irtifasinda_kosar():
    """0.90 m'lik telafi irtifasi, ofsetin erken uygulanmasinin
    SEMPTOMUNU bastirmak icindi. Ofset artik sonda oldugu icin gorsel is
    dogrudan yaklasma irtifasinda yapilir."""
    # GOREV S (2026-09-06): irtifa artik SABIT degil, seklin gorus esiginden
    # turetiliyor (_approach_altitude_m). Sabit 0.30, dedektorun 0.50 m'lik
    # esiginin ALTINDAYDI ve ortalama goremedigi bir irtifada yapiliyordu.
    assert "aligner.align(_approach_alt" in SRC, \
        "gorsel hizalama yaklasma irtifasinda kosmuyor"
    assert "_approach_alt = self._approach_altitude_m()" in SRC


def test_501px_aritmetigi_yeni_irtifada_da_gecerli():
    """Kusurun BUYUKLUGU dokumante kalsin: ofset erken uygulansaydi,
    yaklasma irtifasinda hedef hala kadraj disinda olurdu."""
    f_px = 539.9
    kamera_yuva_m = gp.HOOK_BODY_OFFSET_FORWARD_M + 0.085
    derinlik_m = 0.28                      # 0.30 m irtifada yuvaya derinlik
    dusey_px = kamera_yuva_m * f_px / derinlik_m
    assert dusey_px > 480, f"{dusey_px:.0f} px -- aritmetik degismis olmali"


# ---------------------------------------------------------------------
# B maddesi: dis deneme dongusu (maddeler 9-12)
# ---------------------------------------------------------------------
from core.config.parameters import (          # noqa: E402
    GOREV3_PICKUP_ATTEMPT_TIMEOUT_S,
    GOREV3_PICKUP_MAX_ATTEMPTS,
    GOREV3_VERIFY_CLIMB_ALTITUDE_M,
)


def test_deneme_sahipligi_FAZDA_aktuatorde_degil():
    """Ikisi birden 3 olsaydi 9 yakalama penceresi olurdu; spec 3 diyor."""
    from gz_system import gz_payload_actuator as gz
    assert GOREV3_PICKUP_MAX_ATTEMPTS == 3
    assert gz.HOOK_PICKUP_ATTEMPTS == 1, (
        "aktuatorun ic dongusu hala coklu -- toplam deneme sayisi carpilir")


def test_dis_dongu_ust_butceyi_UYGULAR():
    """60 s yalnizca bir sabit degil, gercekten wait_for ile uygulanmali."""
    assert "asyncio.wait_for(_attempt(attempt)" in SRC
    assert "GOREV3_PICKUP_ATTEMPT_TIMEOUT_S)" in SRC
    assert "except asyncio.TimeoutError" in SRC


def test_butce_ic_dagilimi_60_saniyeye_toplanir():
    """S5'in dagilimi: 4 (salim) + 6 (inis) + 30 (yakalama) + 15
    (dogrulama) + 5 (pay). Parcalar kayarsa toplam da kaymali."""
    from gz_system.gz_payload_actuator import HOOK_CONTACT_TIMEOUT_S
    from core.mission.gorev3_pickup import HOOK_PAYOUT_SETTLE_S
    inis, dogrulama, pay = 6.0, 15.0, 5.0
    toplam = HOOK_PAYOUT_SETTLE_S + inis + HOOK_CONTACT_TIMEOUT_S + dogrulama + pay
    assert toplam == pytest.approx(GOREV3_PICKUP_ATTEMPT_TIMEOUT_S), toplam


def test_dogrulama_TEK_irtifada_ve_2_metrede():
    assert GOREV3_VERIFY_CLIMB_ALTITUDE_M == 2.0
    assert "for alt in (GOREV3_VERIFY_CLIMB_ALTITUDE_M,):" in SRC, \
        "dogrulama hala coklu kademeye cikiyor"


def test_2_metrede_yuk_hala_alan_kapisinin_uzerinde():
    """Dogrulama irtifasi, yukun tespit edilebildigi bir yer olmali --
    yoksa 'gorunmuyor' demek 'alindi' anlamina gelmez."""
    from core.config.parameters import HSV_MIN_AREA_RECT_BASE
    f_px = 539.9
    alan_px2 = (0.14 * f_px / 2.0) * (0.05 * f_px / 2.0)
    assert alan_px2 > HSV_MIN_AREA_RECT_BASE, alan_px2


def test_denemeler_tukenince_FATAL_degil_birakilir():
    """Madde 12: uc deneme de tutmazsa faz False doner ama orkestrator
    MISSION_FAILED'a GECMEZ -- finish/start cizgisine doner."""
    import inspect
    from core.mission.gorev3_orchestrator import Gorev3Orchestrator
    osrc = inspect.getsource(Gorev3Orchestrator.run)
    assert "GOREV3_PICKUP_ABANDONED" in osrc
    assert "RETURN_TO_CHECKPOINT" in osrc
    assert "self.finish_phase.run()" in osrc
    pickup_blok = osrc.split("pickup_ok")[1].split("transport")[0]
    assert "MISSION_FAILED" not in pickup_blok, \
        "alma basarisizligi hala MISSION_FAILED'a gidiyor"
    assert "GOREV3_PICKUP_EXHAUSTED" in SRC
