"""PHASE 5 unit testleri: GazeboPayloadBackend.

test_real_payload_backend.py'nin yapısını yansıtır. Kanıtladıkları:
  1. Sadece iki metod (deploy/release) simülasyona mesaj yayınlar ve doğru
     topic'e doğru içerikle yayınlar; karşılığı olmayan metodlar HİÇ mesaj
     yayınlamaz.
  2. CALIBRATION GUARD (FLEX-20) hem is_in_capture_zone()'da hem deploy()'da
     tetiklenir ve tetiklendiğinde simülasyona HİÇBİR mesaj gitmez.
  3. deploy()'un iki kapısı (yakınlık + /hook/state hazırlığı) gerçekten
     yayını ENGELLER -- HookAttachSystem mesafe kontrolü yapmadığı ve
     /hook/state latch'siz/tek-seferlik olduğu için ikisi de zorunlu.
  4. Dört query aynı tek biti okur (belgelenmiş sadakat kaybı) ve None
     ("hiç geçiş görülmedi") asla yakalandı/bırakıldı olarak okunmaz.

Gerçek gz-transport yok: `_MockGzClient` yayınları sırasıyla kaydeder ve
/hook/state ile poz okumalarını senaryolaştırır.
"""
import asyncio

import pytest

from payload import payload_config
from payload.backends.gazebo_payload_backend import GazeboPayloadBackend
from payload.backends.payload_backend import PayloadBackend
from payload.errors import PayloadCalibrationError

_PAYLOAD_MODEL = "payload_red"
_VEHICLE_MODEL = "x500_mono_cam_down_0"

# Test envelope'u -- GERCEK bir deger DEGIL, sadece "FLEX-20 okundu mu,
# karsilastirmaya girdi mi" sorusunu ayirt edilebilir kilan bir isaretci.
# Gercek deger SITL karakterizasyonundan gelecek (payload_config.py FLEX-20
# hala None/TBD).
_ENVELOPE = 0.5


class _MockGzClient:
    """gz-transport client yerine gecen sahte. Yayinlari SIRAYLA (topic,
    payload) ciftleri olarak kaydeder."""

    def __init__(self, *, hook_state=None, stream_ready=True,
                 clearance=None, publish_ok=True, raise_on_publish=None,
                 wait_result=True):
        self.published = []
        self._hook_state = hook_state
        self._stream_ready = stream_ready
        self._clearance = clearance
        self._publish_ok = publish_ok
        self._raise_on_publish = raise_on_publish
        self._wait_result = wait_result
        self.wait_calls = []

    async def publish_attach(self, model_name):
        self.published.append(("/hook/attach", model_name))
        if self._raise_on_publish is not None:
            raise self._raise_on_publish
        return self._publish_ok

    async def publish_detach(self):
        self.published.append(("/hook/detach", True))
        if self._raise_on_publish is not None:
            raise self._raise_on_publish
        return self._publish_ok

    async def wait_for_hook_state(self, expected):
        self.wait_calls.append(expected)
        return self._wait_result

    def hook_state(self):
        return self._hook_state

    def is_state_stream_ready(self):
        return self._stream_ready

    def read_vehicle_payload_clearance(self):
        """FORMUL burada da YOK: backend tek formule (client'taki
        _vertical_clearance) delege ettigi icin test sadece sonucu
        senaryolastirir."""
        return self._clearance


def _backend(client):
    return GazeboPayloadBackend(client, payload_model_name=_PAYLOAD_MODEL,
                                vehicle_model_name=_VEHICLE_MODEL)


@pytest.fixture
def calibrated(monkeypatch):
    """FLEX-20'yi test degerine sabitler. payload_config modul attribute'u
    calisma aninda okundugu icin monkeypatch backend'e aninda yansir."""
    monkeypatch.setattr(payload_config, "FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M", _ENVELOPE)


# ---------------------------------------------------------------------------
# 1. Sozlesme / yapi
# ---------------------------------------------------------------------------

def test_gazebo_backend_is_a_payload_backend():
    """ABC sozlesmesi karsilaniyor -- soyut metod kalmadigi icin
    ornekleneBILIYOR."""
    assert isinstance(_backend(_MockGzClient()), PayloadBackend)


def test_calibration_error_is_the_shared_type_from_payload_errors():
    """Iki backend AYNI hata tipini paylasmali: ust katman hangi backend'in
    bagli oldugunu bilmeden tek `except PayloadCalibrationError` ile
    kalibrasyon eksigini yakalayabilmeli. Ayri tipler bunu sessizce
    kirardi."""
    from payload.backends import gazebo_payload_backend as gz_module
    from payload.backends import real_payload_backend as real_module

    assert gz_module.PayloadCalibrationError is PayloadCalibrationError
    assert real_module.PayloadCalibrationError is PayloadCalibrationError


def test_constructor_injects_client_and_opens_no_connection():
    """Constructor gz-transport baglantisi KURMAZ ve hicbir sey yayinlamaz."""
    client = _MockGzClient()
    backend = _backend(client)
    assert backend._client is client
    assert client.published == []


@pytest.mark.parametrize("payload_name,vehicle_name", [
    ("", _VEHICLE_MODEL),
    (None, _VEHICLE_MODEL),
    (_PAYLOAD_MODEL, ""),
    (_PAYLOAD_MODEL, None),
])
def test_constructor_requires_explicit_model_names(payload_name, vehicle_name):
    """Model adlarinin sessiz varsayilani OLMAMALI: gizli bir "payload_red"
    varsayimi, yanlis payload'a kaynaklanan bir gorevi fark edilmez
    kilardi."""
    with pytest.raises(ValueError):
        GazeboPayloadBackend(_MockGzClient(), payload_model_name=payload_name,
                             vehicle_model_name=vehicle_name)


def test_gazebo_envelope_flex_is_the_agreed_policy_value():
    """FLEX-20, 2026-08-24'te operator karariyla 0.45 m'ye yukseltildi
    (POLITIKA esigi; PROVENANCE payload_config.py'de). Ilk deger 0.30'du;
    Phase 6 acceptance'inda uretim irtifasinda ulasilan acikligin
    0.303-0.311 m oldugu olculunce (PX4 yer-etkisi hover hatasi) marj
    birakildi. Deger sessizce degisirse bu test kirilir ve PROVENANCE'in
    da guncellenmesini zorlar -- Phase 16'da FLEX-01 bench'i sonrasi
    yeniden gozden gecirilecek."""
    assert payload_config.FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M == 0.45


# ---------------------------------------------------------------------------
# 2. Dogru topic, dogru mesaj, tek yayin
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deploy_publishes_model_name_to_hook_attach(calibrated):
    """KARAR 1: tetikleme deploy()'da. /hook/attach'e child MODEL adi
    yayinlanir (link adi degil -- plugin modeli adiyla arar)."""
    client = _MockGzClient(clearance=0.1)
    assert await _backend(client).deploy() is True
    assert client.published == [("/hook/attach", _PAYLOAD_MODEL)]


@pytest.mark.asyncio
async def test_release_publishes_true_on_hook_detach(calibrated):
    """/hook/detach'e Boolean(true). false KASITLI olarak hic kullanilmaz --
    plugin onu sessizce yok sayar."""
    client = _MockGzClient()
    assert await _backend(client).release() is True
    assert client.published == [("/hook/detach", True)]


@pytest.mark.asyncio
async def test_await_capture_observes_and_publishes_nothing(calibrated):
    """SAF GOZLEM: await_capture() hicbir mesaj yayinlamaz, sadece
    /hook/state=true'yu bekler."""
    client = _MockGzClient(wait_result=True)
    assert await _backend(client).await_capture() is True
    assert client.published == []
    assert client.wait_calls == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", ["grapple", "retract", "stow",
                                        "lower_for_release"])
async def test_no_counterpart_methods_are_silent_noops(calibrated, method_name):
    """KARAR 3: Gazebo karsiligi olmayan metodlar True doner ama
    simulasyona HICBIR mesaj gondermez."""
    client = _MockGzClient()
    assert await getattr(_backend(client), method_name)() is True
    assert client.published == []


@pytest.mark.asyncio
async def test_full_v33_sequence_publishes_exactly_two_messages_in_order(calibrated):
    """Tam dizi yalnizca iki mesaj uretir: attach, sonra detach.
    Karsiligi olmayan uc metodun sessizligini de birlikte kanitlar."""
    client = _MockGzClient(clearance=0.1)
    backend = _backend(client)

    await backend.deploy()
    await backend.await_capture()
    await backend.grapple()
    await backend.retract()
    await backend.lower_for_release()
    await backend.release()
    await backend.stow()

    assert client.published == [
        ("/hook/attach", _PAYLOAD_MODEL),
        ("/hook/detach", True),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name,needs_distance", [
    ("deploy", True),
    ("release", False),
])
async def test_action_returns_false_when_publish_fails(calibrated, method_name, needs_distance):
    """Client yayini basaramazsa metod False doner, exception sizmaz."""
    client = _MockGzClient(publish_ok=False,
                           clearance=0.1 if needs_distance else None)
    assert await getattr(_backend(client), method_name)() is False


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name,needs_distance", [
    ("deploy", True),
    ("release", False),
])
async def test_client_exception_is_not_swallowed(calibrated, method_name, needs_distance):
    """Beklenmedik bir client hatasi False'a cevrilip 'gorev basarisiz' gibi
    GIZLENMEZ -- payload_manager.py'nin 'backend hatasi != mission hatasi'
    kuraliyla tutarli."""
    client = _MockGzClient(raise_on_publish=RuntimeError("gz transport coktu"),
                           clearance=0.1 if needs_distance else None)
    with pytest.raises(RuntimeError, match="gz transport coktu"):
        await getattr(_backend(client), method_name)()


@pytest.mark.asyncio
async def test_backend_never_sleeps(calibrated, monkeypatch):
    """Zaman yonetimi PayloadManager'in isi: backend hicbir yerde
    asyncio.sleep cagirmaz (bekleme client'in abonelik olayina devredilmis)."""
    called = []
    real_sleep = asyncio.sleep

    async def _tracking_sleep(delay, *a, **kw):
        called.append(delay)
        return await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _tracking_sleep)
    client = _MockGzClient(clearance=0.1)
    backend = _backend(client)

    await backend.deploy()
    await backend.await_capture()
    await backend.grapple()
    await backend.retract()
    await backend.release()
    await backend.stow()

    assert called == []


# ---------------------------------------------------------------------------
# 3. CALIBRATION GUARD ve deploy()'un iki kapisi
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", ["deploy", "is_in_capture_zone"])
async def test_calibration_guard_trips_for_tbd_envelope(monkeypatch, method_name):
    """FLEX-20 TBD iken hem deploy() hem is_in_capture_zone()
    PayloadCalibrationError ile durur ve simulasyona HICBIR mesaj gitmez."""
    monkeypatch.setattr(payload_config, "FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M", None)
    client = _MockGzClient(clearance=0.1)
    backend = _backend(client)

    with pytest.raises(PayloadCalibrationError, match="FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M"):
        result = getattr(backend, method_name)()
        if asyncio.iscoroutine(result):
            await result

    assert client.published == [], (
        "FLEX-20 TBD iken simulasyona komut gonderildi -- CALIBRATION GUARD "
        "yayindan ONCE calismali.")


def test_calibration_error_message_points_to_config(monkeypatch):
    """Hata mesaji ne yapilmasi gerektigini ve komutun GONDERILMEDIGINI
    soylemeli."""
    monkeypatch.setattr(payload_config, "FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M", None)
    with pytest.raises(PayloadCalibrationError) as excinfo:
        _backend(_MockGzClient()).is_in_capture_zone()

    message = str(excinfo.value)
    assert "payload_config.py" in message
    assert "HOW TO CALIBRATE" in message
    assert "GONDERILMEDI" in message


@pytest.mark.parametrize("flex_name", [
    "FLEX_14_SERVO2_ACTUATOR_INDEX",
    "FLEX_16_SERVO2_DOWN_VALUE",
    "FLEX_19_SERVO3_RELEASE_VALUE",
])
def test_guard_ignores_servo_flex_constants(calibrated, monkeypatch, flex_name):
    """Servo FLEX'leri (FLEX-14..19) MAVSDK actuator parametreleridir ve
    Gazebo'da hicbir anlami yoktur -- bu backend onlari OKUMAMALI."""
    monkeypatch.setattr(payload_config, flex_name, None)
    client = _MockGzClient(clearance=0.1)
    assert _backend(client).is_in_capture_zone() is True


@pytest.mark.asyncio
async def test_deploy_refuses_when_outside_capture_envelope(calibrated):
    """KARAR 2: HookAttachSystem mesafe kontrolu YAPMAZ (payload'i 1 km
    oteden de kaynaklar), bu yuzden yakinlik kapisi tek korumadir. Envelope
    disindayken /hook/attach YAYINLANMAMALI."""
    client = _MockGzClient(clearance=_ENVELOPE + 0.01)
    assert await _backend(client).deploy() is False
    assert client.published == []


@pytest.mark.asyncio
async def test_deploy_publishes_exactly_at_envelope_boundary(calibrated):
    """Sinir dahil (<=): tam envelope mesafesinde yayin YAPILIR."""
    client = _MockGzClient(clearance=_ENVELOPE)
    assert await _backend(client).deploy() is True
    assert client.published == [("/hook/attach", _PAYLOAD_MODEL)]


@pytest.mark.asyncio
async def test_deploy_refuses_when_state_stream_not_ready(calibrated):
    """/hook/state latch'siz ve gecis basina TEK KEZ yayinlanir; plugin
    2.2 ms'de kaynaklarken taze bir abonelik ~2 s discovery ister. Abonelik
    hazir degilken attach yayinlamak, gozlenecek tek mesaji yapisal olarak
    kacirmak demektir -- joint olussa bile timeout alinirdi."""
    client = _MockGzClient(clearance=0.1, stream_ready=False)
    assert await _backend(client).deploy() is False
    assert client.published == []


@pytest.mark.asyncio
async def test_release_is_not_gated_on_state_stream(calibrated):
    """deploy()'un aksine release() gozlemlenebilirlik yuzunden
    ENGELLENMEZ: birakma komutunu bloke etmek payload'i araca takili
    birakirdi -- dogrulanamamis bir birakmadan daha kotu bir sonuc."""
    client = _MockGzClient(stream_ready=False)
    assert await _backend(client).release() is True
    assert client.published == [("/hook/detach", True)]


def test_capture_zone_is_false_when_clearance_unknown(calibrated):
    """'Bilmiyorum' asla 'yakinim' olarak okunmaz. Client poz okuyamadiginda
    _vertical_clearance() None doner ve backend bunu sayiya CEVIRMEZ."""
    assert _backend(_MockGzClient(clearance=None)).is_in_capture_zone() is False


# ---------------------------------------------------------------------------
# 4. Query primitifleri -- tek bit, belgelenmis sadakat kaybi
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query_name,state,expected", [
    ("has_captured", True, True),
    ("has_captured", False, False),
    ("has_captured", None, False),
    ("is_grappled", True, True),
    ("is_grappled", None, False),
    ("is_secured", True, True),
    ("is_secured", None, False),
    ("has_released", False, True),
    ("has_released", True, False),
    ("has_released", None, False),
])
def test_queries_read_the_single_hook_state_bit(calibrated, query_name, state, expected):
    """Dort query /hook/state'in tek bitini okur. None ('hic gecis
    gorulmedi') ne yakalandi ne birakildi sayilir -- `is True` / `is False`
    karsilastirmalari KASITLI."""
    backend = _backend(_MockGzClient(hook_state=state))
    assert getattr(backend, query_name)() is expected


def test_is_grappled_is_the_same_bit_as_has_captured(calibrated):
    """Belgelenmis SADAKAT KAYBI'ni sabitler: Gazebo'da yakalama ve kavrama
    tek bir CreateComponent cagrisidir, ayirt edilemezler. Bu test, ileride
    birinin var olmayan bir ayrimi 'implement' etmesini engeller."""
    for state in (True, False, None):
        backend = _backend(_MockGzClient(hook_state=state))
        assert backend.is_grappled() == backend.has_captured()


def test_is_secured_is_load_bearing_for_payload_manager(calibrated):
    """is_secured(), PayloadManager'in gercekten cagirdigi TEK query
    (catch_box_up). NotImplementedError olsaydi Gazebo yolunda catch_box_up()
    patlardi -- bu test onu somut olarak sabitler."""
    from payload.models.hook_behavior_model import HookBehaviourModel

    model = HookBehaviourModel(_backend(_MockGzClient(hook_state=True)))
    assert model.is_secured() is True


def test_is_deployed_is_not_implemented(calibrated):
    """is_deployed() KASITLI olarak NotImplementedError: Gazebo'da 'kanca
    indirildi' kavraminin karsiligi yok -- eksik olan bir SAYI degil,
    kavramin kendisi, bu yuzden FLEX ile cozulemez."""
    with pytest.raises(NotImplementedError, match="is_deployed"):
        _backend(_MockGzClient()).is_deployed()
