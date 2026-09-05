"""GOREV N -- servo3 zamanlama netligi + servo aci tanimlari.

Bu testler DAVRANIS degil SOZLESME kilitler: gecikmenin gercekten kapilari
ornekleyerek beklendigini ve aci tanimlarinin config'ten geldigini
(hardcode edilmedigini) korurlar.
"""
import inspect

from core.config.parameters import (
    GOREV3_SERVO1_ANGLES_DEG,
    GOREV3_SERVO3_CLOSED_DEG,
    GOREV3_SERVO3_OPEN_DEG,
    GOREV3_SERVO3_POST_LOCK_DELAY_S,
    GOREV3_SERVO3_SWEEP_DEG,
)
import gz_system.gz_payload_actuator as _gz
import real_system.real_payload_actuator as _real

GZ_SRC = inspect.getsource(_gz)
REAL_SRC = inspect.getsource(_real)


# --------------------------------------------------------------------------
# A -- SERVO3 KILIT SONRASI GECIKMESI
# --------------------------------------------------------------------------

def test_kilit_sonrasi_gecikme_tanimli():
    """Operator tarifi: kilitlenme aninda DEGIL, ondan sabit bir sure sonra.
    Onceki davranista gecikme YOKTU (dwell dolar dolmaz /hook/attach)."""
    assert GOREV3_SERVO3_POST_LOCK_DELAY_S > 0.0


def test_gecikme_KOR_BEKLEME_DEGIL_kapilari_ornekliyor():
    """Kritik: gecikme boyunca oturma kapilari ORNEKLENMEYE DEVAM etmeli.

    Sadece uyuyup sonra kavramak, garantiyi guclendirmek yerine ZAYIFLATIRDI:
    kanca kayip gitmisken kavramak, oturma kapisinin var olma sebebi olan
    Case 7 kusurunun ta kendisidir."""
    i = GZ_SRC.index("GOREV3_SERVO3_POST_LOCK_DELAY_S > 0.0")
    blok = GZ_SRC[i:i + 1400]
    assert "self.seating_geometry(color)" in blok, \
        "gecikme penceresinde geometri ORNEKLENMIYOR -- kor bekleme"
    assert "evaluator.update(" in blok, \
        "gecikme penceresinde kapilar DEGERLENDIRILMIYOR"
    assert "continue" in blok, \
        "kapilar bozulunca dwell bastan saymiyor"


def test_gecikme_MAGNET_DWELL_S_e_DOKUNMUYOR():
    """Gorev M/S4 alani korunmali: dwell ayri, bu ayri ve UST bir pencere."""
    from core.mission.hook_seating import MAGNET_DWELL_S
    assert MAGNET_DWELL_S == 0.60, \
        "MAGNET_DWELL_S degistirilmis -- Gorev M/S4 alanina dokunulmus"


def test_rapor_gecikmeyi_ve_iptalleri_yaziyor():
    """Gecikmenin BEDAVA olup olmadigi olculebilmeli."""
    assert '"post_lock_delay_s"' in GZ_SRC
    assert '"post_lock_aborts"' in GZ_SRC


# --------------------------------------------------------------------------
# B -- SERVO ACI TANIMLARI
# --------------------------------------------------------------------------

def test_servo1_uc_konum():
    """Operator: 90 sol -- orta -- 90 sag."""
    assert set(GOREV3_SERVO1_ANGLES_DEG) == {"sol", "orta", "sag"}
    assert GOREV3_SERVO1_ANGLES_DEG["sol"] == -90.0
    assert GOREV3_SERVO1_ANGLES_DEG["orta"] == 0.0
    assert GOREV3_SERVO1_ANGLES_DEG["sag"] == +90.0


def test_servo3_180_derece_soldan_saga():
    """Operator: 180 derece, soldan saga; tam aciklik."""
    assert GOREV3_SERVO3_SWEEP_DEG == 180.0
    assert GOREV3_SERVO3_CLOSED_DEG == 0.0
    assert GOREV3_SERVO3_OPEN_DEG == 180.0
    assert abs(GOREV3_SERVO3_OPEN_DEG - GOREV3_SERVO3_CLOSED_DEG) == GOREV3_SERVO3_SWEEP_DEG


def test_acilar_config_ten_okunuyor_HARDCODE_DEGIL():
    """Gercek donanim yolu acilari config adiyla anmali; ciplak sayi degil."""
    assert "GOREV3_SERVO1_ANGLES_DEG" in REAL_SRC
    assert "GOREV3_SERVO3_CLOSED_DEG" in REAL_SRC
    assert "GOREV3_SERVO3_OPEN_DEG" in REAL_SRC
    assert "GOREV3_SERVO3_SWEEP_DEG" in REAL_SRC


def test_servo2_yonu_belgeli():
    """SERVO2'nin hangi yonu sarkitip hangisinin cektigi yazili olmali --
    ters monte edilmis bir servo, sessizce vinci yukari cekerdi."""
    for src in (REAL_SRC, GZ_SRC):
        assert "SARKIT" in src.upper()
        assert "CEK" in src.upper()
