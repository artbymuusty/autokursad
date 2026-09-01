"""PHASE 4 unit testleri: RealPayloadBackend.

Üç şeyi kanıtlar:
  1. Her action metodu DOĞRU servo index'ine (FLEX-14/15) DOĞRU değeri
     (FLEX-16/17/18/19) tek bir set_actuator() çağrısıyla gönderir; tam
     V33 dizisi doğru SIRAYLA çalışır.
  2. Her CALIBRATION GUARD, kendi iki FLEX parametresinin HER BİRİ için
     AYRI AYRI tetiklenir -- ve tetiklendiğinde donanıma HİÇBİR komut
     gitmez (set_actuator çağrılmaz).
  3. await_capture() ve tüm query primitifleri KASITLI olarak
     NotImplementedError'dır (sahte implementasyon yok) -- sessizce True
     dönen bir stub üst katmanı yanıltacağı için.

Gerçek MAVSDK bağlantısı yok: `_MockAction` set_actuator çağrılarını
sırasıyla kaydeder, istenirse ActionError fırlatır.
"""
import pytest

from payload import payload_config
from payload.backends.payload_backend import PayloadBackend
from payload.backends.real_payload_backend import RealPayloadBackend
from payload.errors import PayloadCalibrationError

# Testlerde kullanilan kalibrasyon degerleri -- GERCEK degerler DEGIL,
# sadece "bu FLEX okundu mu, dogru yere mi gitti" sorusunu ayirt edilebilir
# kilan benzersiz isaretciler. Gercek degerler bench testinden gelecek
# (bkz. payload_config.py, FLEX-14..19 hepsi None/TBD).
_SERVO2_INDEX = 5
_SERVO3_INDEX = 6
_DOWN_VALUE = 0.11
_GRAPPLE_VALUE = 0.22
_REVERSE_VALUE = -0.33
_RELEASE_VALUE = -0.44

# method_name -> (index FLEX adi, deger FLEX adi) -- real_payload_backend.py
# docstring'indeki CALIBRATION GUARD haritasinin test tarafindaki kopyasi.
_GUARD_MAP = {
    "deploy": ("FLEX_14_SERVO2_ACTUATOR_INDEX", "FLEX_16_SERVO2_DOWN_VALUE"),
    "grapple": ("FLEX_15_SERVO3_ACTUATOR_INDEX", "FLEX_17_SERVO3_GRAPPLE_VALUE"),
    "retract": ("FLEX_14_SERVO2_ACTUATOR_INDEX", "FLEX_18_SERVO2_REVERSE_VALUE"),
    "release": ("FLEX_15_SERVO3_ACTUATOR_INDEX", "FLEX_19_SERVO3_RELEASE_VALUE"),
    "stow": ("FLEX_14_SERVO2_ACTUATOR_INDEX", "FLEX_18_SERVO2_REVERSE_VALUE"),
}

_ALL_FLEX = {
    "FLEX_14_SERVO2_ACTUATOR_INDEX": _SERVO2_INDEX,
    "FLEX_15_SERVO3_ACTUATOR_INDEX": _SERVO3_INDEX,
    "FLEX_16_SERVO2_DOWN_VALUE": _DOWN_VALUE,
    "FLEX_17_SERVO3_GRAPPLE_VALUE": _GRAPPLE_VALUE,
    "FLEX_18_SERVO2_REVERSE_VALUE": _REVERSE_VALUE,
    "FLEX_19_SERVO3_RELEASE_VALUE": _RELEASE_VALUE,
}


class _MockAction:
    """MAVSDK Action yerine gecen sahte: set_actuator cagrilarini SIRAYLA
    kaydeder. raise_error verilirse cagri ActionError ile reddedilir."""

    def __init__(self, raise_error=None):
        self.calls = []
        self._raise_error = raise_error

    async def set_actuator(self, index, value):
        self.calls.append((index, value))
        if self._raise_error is not None:
            raise self._raise_error


def _action_error():
    """Gercek mavsdk.action.ActionError uretir -- generic Exception DEGIL,
    boylece backend'in SADECE ActionError yakaladigi gercekten sinanir."""
    from mavsdk.action import ActionError, ActionResult
    result = ActionResult(ActionResult.Result.COMMAND_DENIED, "COMMAND_DENIED")
    return ActionError(result, "set_actuator()", 1, 0.0)


@pytest.fixture
def calibrated(monkeypatch):
    """FLEX-14..19'un HEPSINI test degerlerine sabitler. payload_config
    modul attribute'lari calisma aninda okundugu icin bu monkeypatch
    backend'e aninda yansir."""
    for name, value in _ALL_FLEX.items():
        monkeypatch.setattr(payload_config, name, value)


# ---------------------------------------------------------------------------
# 1. Sozlesme / yapi
# ---------------------------------------------------------------------------

def test_real_backend_is_a_payload_backend():
    """ABC sozlesmesi karsilaniyor -- soyut metod kalmadigi icin
    ornekleneBILIYOR (PHASE 0'daki dependency injection zinciri saglam)."""
    backend = RealPayloadBackend(_MockAction())
    assert isinstance(backend, PayloadBackend)


def test_calibration_error_is_the_shared_type_from_payload_errors():
    """PHASE 5 ADIM 0: PayloadCalibrationError payload/errors.py'ye tasindi.
    real_payload_backend uzerinden erisilen sinif AYNI nesne olmali --
    yoksa Gazebo backend'i baska bir tip firlatir ve ust katmanin tek
    `except PayloadCalibrationError` bloguyla ikisini birden yakalamasi
    sessizce kirilirdi."""
    from payload.backends import real_payload_backend as real_module

    assert real_module.PayloadCalibrationError is PayloadCalibrationError


def test_constructor_injects_action_and_opens_no_connection():
    """Constructor MAVSDK baglantisi KURMAZ, sadece verilen action'i tutar
    -- ve hicbir RPC cagirmaz."""
    action = _MockAction()
    backend = RealPayloadBackend(action)
    assert backend._action is action
    assert action.calls == []


def test_all_new_flex_constants_are_still_tbd():
    """FLEX-14..19 repoda TBD (None) kalmali -- bench test yapilmadan bir
    deger girildiyse bu test kirilir ve kalibrasyonun belgelenmesini
    zorlar."""
    for name in _ALL_FLEX:
        assert getattr(payload_config, name) is None, (
            f"{name} artik None degil -- bench kalibrasyonu yapildiysa bu testi ve "
            f"payload_config.py'deki CURRENT DEFAULT notunu guncelleyin.")


# ---------------------------------------------------------------------------
# 2. Dogru servo, dogru deger, tek cagri
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("method_name,expected", [
    ("deploy", (_SERVO2_INDEX, _DOWN_VALUE)),
    ("grapple", (_SERVO3_INDEX, _GRAPPLE_VALUE)),
    ("retract", (_SERVO2_INDEX, _REVERSE_VALUE)),
    ("release", (_SERVO3_INDEX, _RELEASE_VALUE)),
    ("stow", (_SERVO2_INDEX, _REVERSE_VALUE)),
])
async def test_action_sends_expected_actuator_command(calibrated, method_name, expected):
    """Her action primitifi kendi FLEX index/deger ciftini TEK bir
    set_actuator() cagrisina cevirir ve True (=RPC kabul edildi) doner."""
    action = _MockAction()
    backend = RealPayloadBackend(action)

    assert await getattr(backend, method_name)() is True
    assert action.calls == [expected]


@pytest.mark.asyncio
async def test_retract_and_stow_share_flex_18(calibrated):
    """retract() ve stow() ayni fiziksel SERVO2_REVERSE komutudur --
    ikisi de FLEX-18'i kullanir, kasitli paylasim (bkz. payload_config.py
    FLEX-18 PAYLASIM NOTU). Ayrilirlarsa bu test kirilir."""
    action = _MockAction()
    backend = RealPayloadBackend(action)

    await backend.retract()
    await backend.stow()

    assert action.calls[0] == action.calls[1] == (_SERVO2_INDEX, _REVERSE_VALUE)


@pytest.mark.asyncio
async def test_full_v33_sequence_is_sent_in_order(calibrated):
    """Tam V33 dizisi: SERVO2_DOWN -> SERVO3_GRAPPLE -> SERVO2_REVERSE ->
    SERVO3_RELEASE -> SERVO2_REVERSE. Sira ve servo/deger eslesmesi birlikte
    dogrulanir.

    NOT: await_capture() bu dizide KASITLI OLARAK yok -- bir komut degil
    gozlemdir ve sensor yolu olmadigi icin NotImplementedError'dir
    (bkz. test_await_capture_is_not_implemented)."""
    action = _MockAction()
    backend = RealPayloadBackend(action)

    await backend.deploy()
    await backend.grapple()
    await backend.retract()
    await backend.release()
    await backend.stow()

    assert action.calls == [
        (_SERVO2_INDEX, _DOWN_VALUE),       # V33: SERVO2_DOWN
        (_SERVO3_INDEX, _GRAPPLE_VALUE),    # V33: SERVO3_GRAPPLE
        (_SERVO2_INDEX, _REVERSE_VALUE),    # V33: SERVO2_REVERSE (1. kullanim)
        (_SERVO3_INDEX, _RELEASE_VALUE),    # V33: SERVO3_RELEASE
        (_SERVO2_INDEX, _REVERSE_VALUE),    # V33: SERVO2_REVERSE (2./son kullanim)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", sorted(_GUARD_MAP))
async def test_action_returns_false_when_rpc_rejected(calibrated, method_name):
    """set_actuator() ActionError firlatirsa metod False doner (exception
    disari sizmaz) -- 'komut REDDEDILDI' sinyali."""
    action = _MockAction(raise_error=_action_error())
    backend = RealPayloadBackend(action)

    assert await getattr(backend, method_name)() is False
    assert len(action.calls) == 1  # cagri denendi, sonra reddedildi


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", sorted(_GUARD_MAP))
async def test_non_action_error_is_not_swallowed(calibrated, method_name):
    """SADECE ActionError yakalanir. Baska bir exception (or. baglanti
    kopmasi) False'a cevrilip 'mission basarisiz' gibi gizlenmez --
    payload_manager.py'nin 'backend hatasi != mission hatasi' kuraliyla
    tutarli."""
    action = _MockAction(raise_error=RuntimeError("gRPC channel kapandi"))
    backend = RealPayloadBackend(action)

    with pytest.raises(RuntimeError, match="gRPC channel kapandi"):
        await getattr(backend, method_name)()


# ---------------------------------------------------------------------------
# 3. CALIBRATION GUARD -- her metod, her TBD parametre icin AYRI AYRI
# ---------------------------------------------------------------------------

def _guard_cases():
    """Her (metod, o metodun kullandigi FLEX) cifti icin bir vaka uretir:
    5 metod x 2 FLEX = 10 ayri guard testi."""
    for method_name, flex_names in sorted(_GUARD_MAP.items()):
        for flex_name in flex_names:
            yield pytest.param(method_name, flex_name, id=f"{method_name}-{flex_name}")


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name,missing_flex", list(_guard_cases()))
async def test_calibration_guard_trips_for_each_tbd_parameter(
        monkeypatch, calibrated, method_name, missing_flex):
    """CALIBRATION GUARD haritasinin tam kanit testi.

    Diger TUM FLEX'ler kalibre edilmisken SADECE bir tanesi None'a
    cekilir; ilgili metod PayloadCalibrationError ile durmali ve --
    kritik olan -- donanima HICBIR komut GITMEMELI (set_actuator
    cagrilmamis olmali).

    Bu, her metodun gercekten KENDI iki FLEX'ini guard ettigini kanitlar:
    bir metod yanlis FLEX'i guard etseydi, dogru FLEX None iken sessizce
    None ile RPC gonderirdi."""
    monkeypatch.setattr(payload_config, missing_flex, None)
    action = _MockAction()
    backend = RealPayloadBackend(action)

    with pytest.raises(PayloadCalibrationError, match=missing_flex):
        await getattr(backend, method_name)()

    assert action.calls == [], (
        f"{method_name}(): {missing_flex} TBD iken donanima komut gonderildi -- "
        f"CALIBRATION GUARD set_actuator'dan ONCE calismali.")


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name,unrelated_flex", [
    ("deploy", "FLEX_15_SERVO3_ACTUATOR_INDEX"),
    ("deploy", "FLEX_17_SERVO3_GRAPPLE_VALUE"),
    ("grapple", "FLEX_14_SERVO2_ACTUATOR_INDEX"),
    ("grapple", "FLEX_16_SERVO2_DOWN_VALUE"),
    ("retract", "FLEX_19_SERVO3_RELEASE_VALUE"),
    ("release", "FLEX_16_SERVO2_DOWN_VALUE"),
    ("stow", "FLEX_17_SERVO3_GRAPPLE_VALUE"),
])
async def test_guard_ignores_flex_the_method_does_not_use(
        monkeypatch, calibrated, method_name, unrelated_flex):
    """Guard KAPSAMI testi: bir metod, kullanmadigi bir FLEX None diye
    durMAMALI. (Aksi halde 'her sey kalibre olmadan hicbir sey calismaz'
    olurdu; harita metod bazinda dar tutulmustur.)"""
    monkeypatch.setattr(payload_config, unrelated_flex, None)
    action = _MockAction()
    backend = RealPayloadBackend(action)

    assert await getattr(backend, method_name)() is True
    assert len(action.calls) == 1


@pytest.mark.asyncio
async def test_calibration_error_message_points_to_config(monkeypatch, calibrated):
    """Hata mesaji, ne yapilmasi gerektigini ve komutun GONDERILMEDIGINI
    soylemeli -- sahada log okuyan kisi icin."""
    monkeypatch.setattr(payload_config, "FLEX_16_SERVO2_DOWN_VALUE", None)
    backend = RealPayloadBackend(_MockAction())

    with pytest.raises(PayloadCalibrationError) as excinfo:
        await backend.deploy()

    message = str(excinfo.value)
    assert "payload_config.py" in message
    assert "HOW TO CALIBRATE" in message
    assert "GONDERILMEDI" in message


# ---------------------------------------------------------------------------
# 4. Kasitli olarak implement EDILMEYENLER
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_await_capture_is_not_implemented(calibrated):
    """await_capture() bir komut degil GOZLEMdir; sensor yolu olmadigi icin
    KASITLI olarak NotImplementedError. Sahte 'hep True' donen bir stub, ust
    katmanin hic payload yakalamadan CAPTURED'a gecmesine yol acardi."""
    action = _MockAction()
    backend = RealPayloadBackend(action)

    with pytest.raises(NotImplementedError, match="await_capture"):
        await backend.await_capture()
    assert action.calls == []


@pytest.mark.parametrize("query_name", [
    "is_deployed", "is_in_capture_zone", "has_captured",
    "is_grappled", "is_secured", "has_released",
])
def test_query_primitives_are_not_implemented(calibrated, query_name):
    """Query primitifleri KASITLI olarak NotImplementedError -- kalibrasyon
    yapilmis olsa BILE (calibrated fixture aktif), cunku eksik olan sey bir
    sayi degil, sensor yolunun kendisi."""
    backend = RealPayloadBackend(_MockAction())

    with pytest.raises(NotImplementedError, match=query_name):
        getattr(backend, query_name)()
