"""GOREV P -- servo3 zamanlamasi + "dogrulanamayan durumda ALINMADI" ilkesi."""
import inspect
import re

from core.config.parameters import GOREV3_SERVO3_POST_LOCK_DELAY_S
import core.mission.gorev3_pickup as _g3
import gz_system.gz_payload_actuator as _gz
import real_system.real_payload_actuator as _real

G3 = inspect.getsource(_g3)
#: Yorumlar ayiklanmis hali. Eski kusuru BELGELEYEN yorum, kusurun
#  KENDISIYLE karistirilmamali -- ilk yazimda tam bunu yaptim ve test
#  kendi acikladigi metni yakaladi.
G3_KOD = "\n".join(l for l in G3.splitlines()
                   if not l.lstrip().startswith("#"))
GZ = inspect.getsource(_gz)
REAL = inspect.getsource(_real)


# --------------------------------------------------------------------------
# A -- SERVO3 ZAMANLAMASI HER DENEMEDE
# --------------------------------------------------------------------------

def test_gecikme_HER_denemede_kosuyor_kosula_bagli_degil():
    """Gecikme _await_seating'in icinde ve tek kosulu sabitin pozitif
    olmasi; deneme numarasina, ilk-deneme-mi'ye ya da baska bir duruma
    BAGLI DEGIL. _await_seating her alma denemesinde cagriliyor."""
    i = GZ.index("GOREV3_SERVO3_POST_LOCK_DELAY_S > 0.0")
    kosul = GZ[GZ.rindex("if ", 0, i):i + 40]
    assert "attempt" not in kosul and "first" not in kosul, \
        f"gecikme deneme durumuna bagli: {kosul!r}"
    # _await_seating, alma dongusunun HER turunda cagriliyor
    assert GZ.count("await self._await_seating(") == 1
    i2 = GZ.index("await self._await_seating(")
    assert "for attempt in range" in GZ[:i2], "dongu disinda cagriliyor"


def test_gecikme_ve_kilit_sonrasi_sonumleme_CAKISMIYOR():
    """Ikisi AYRI ve SIRALI: POST_LOCK_DELAY, MAGNET_LOCKED'dan ONCE
    (kapilar hala orneklenerek); HOOK_SETTLE_S ise SERVO3'ten SONRA ve
    artik butce DISINDA (_verify_lift'in basinda)."""
    i_delay = GZ.index("GOREV3_SERVO3_POST_LOCK_DELAY_S > 0.0")
    i_lock = GZ.index("MAGNET_LOCKED")
    i_servo = GZ.index("SERVO3 KAVRAMA")
    assert i_delay < i_lock < i_servo, "sira bozuk"
    # HOOK_SETTLE_S artik aktuatorde KOSULLU, gorevde butce disinda
    assert "if settle_after_lock:" in GZ
    assert "settle_after_lock=False" in G3
    i_verify = G3.index("async def _verify_lift")
    assert "asyncio.sleep(_SETTLE_S)" in G3[i_verify:i_verify + 1200]


def test_gecikme_kor_bekleme_degil():
    i = GZ.index("GOREV3_SERVO3_POST_LOCK_DELAY_S > 0.0")
    blok = GZ[i:i + 1400]
    assert "self.seating_geometry(color)" in blok
    assert "evaluator.update(" in blok
    assert "continue" in blok


# --------------------------------------------------------------------------
# B -- DOGRULANAMAYAN DURUMDA "ALINMADI"
# --------------------------------------------------------------------------

def test_grip_engaged_ve_pickup_verified_AYRI_bayraklar():
    assert "grip_engaged = True" in G3
    assert "pickup_verified = bool(attached and lift_ok)" in G3


def test_olculemeyen_kaldirma_BASARISIZ_sayilir():
    """DUZELTILEN KUSUR: onceki kod
        if lifted_m is not None and lifted_m < PICKUP_LIFT_CONFIRM_M: return False
        return True
    diyordu -- lifted_m OLCULEMEDIGINDE kontrol atlanip True donuyordu,
    yani 'olcemedim, o halde almisimdir'. Kanit YOKLUGU artik
    basarisizliktir."""
    assert "lift_ok = (lifted_m is not None" in G3
    assert "if lifted_m is not None and lifted_m < PICKUP_LIFT_CONFIRM_M:" not in G3_KOD, \
        "iyimser varsayim geri gelmis (YORUMDA degil, KODDA)"


def test_servo3_olayi_TEK_BASINA_basarili_saymiyor():
    """grip_engaged True olsa bile pickup_verified False ise faz basarisiz
    donmeli."""
    i = G3.index("if not pickup_verified:")
    blok = G3[i:i + 900]
    assert "return False" in blok
    assert "grip_engaged=True olsa bile" in blok


def test_gercek_donanim_bosluguna_TODO_var():
    """Servo3'un fiziksel kavrama geri bildirimi YOK; bu ACIK boslugu
    gercek donanim yolunda belgele."""
    assert "GEREK" in REAL.upper() or "GERÇEK" in REAL
    assert "GERİ BİLDİRİMİ YOKTUR" in REAL
    assert "pickup_verified" in REAL
    assert "ALINMADI" in REAL


def test_sabit_tanimli_ve_pozitif():
    assert GOREV3_SERVO3_POST_LOCK_DELAY_S > 0.0
