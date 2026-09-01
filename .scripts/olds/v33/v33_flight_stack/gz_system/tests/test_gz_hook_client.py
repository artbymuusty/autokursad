"""PHASE 5.5 ADIM B testleri: GzHookClient.

Üç şeyi kanıtlar:
  1. PARSER: gz.msgs.Boolean'ın GERÇEK text encoding'i (data:false hiçbir
     satır üretmez -- protobuf default-value omission) doğru çözülüyor.
     true -> false -> true dizisi tam olarak bu şekilde algılanmalı. Bu,
     ADIM A'da ölçülen ve legacy HookStateMonitor'ü bozan bug'ın yeni
     kodda TEKRARLANMADIĞININ kanıtıdır.
  2. RACE: abonelik publish'i BEKLEMEZ; is_state_stream_ready() gerçekten
     discovery yerleşmesini bekler; hazır değilken attach YAYINLANMAZ.
  3. Protokol: GazeboPayloadBackend'in çağırdığı her metod doğru gz topic
     komutunu üretir.

Gerçek subprocess yok: `_FakeExec` enjekte edilir ve `gz topic` çağrılarını
ayırt ederek sahte süreçler döndürür.
"""
import asyncio

import pytest

from gz_system.gz_hook_client import (
    HOOK_ATTACH_TOPIC,
    HOOK_DETACH_TOPIC,
    HOOK_STATE_TOPIC,
    GzHookClient,
)

_PAYLOAD = "payload_red"
_VEHICLE = "x500_mono_cam_down_0"

# gz.msgs.Boolean'in ADIM A'da CANLI OLCULEN text encoding'i.
# /test/boolshape topic'ine true -> false -> true yayinlandi, `gz topic -e`
# ciktisi `cat -A` ile soyle geldi:
#     data:·true<LF>  <LF>  <LF>  data:·true<LF>  <LF>
# Yani: true = "data: true" + ayirici; false = SADECE ayirici (bos govde).
_REAL_TRUE = ["data: true\n", "\n"]
_REAL_FALSE = ["\n"]


class _FakeStdout:
    """readline() ile satir satir beslenen sahte stdout. Satirlar bitince
    asla donmeyen bir bekleyise girer (gercek `gz topic -e` gibi: topic
    sessizse surec kapanmaz)."""

    def __init__(self, lines):
        self._lines = list(lines)

    async def readline(self):
        if self._lines:
            return self._lines.pop(0).encode()
        await asyncio.Event().wait()  # sonsuza kadar bekle


class _FakeProc:
    def __init__(self, lines=None, stdout_bytes=b"", returncode=0):
        self.stdout = _FakeStdout(lines) if lines is not None else None
        self._stdout_bytes = stdout_bytes
        self.returncode = returncode
        self.terminated = False

    async def communicate(self):
        return self._stdout_bytes, b""

    def terminate(self):
        self.terminated = True

    async def wait(self):
        return self.returncode


class _FakeExec:
    """Enjekte edilen subprocess fabrikasi. `gz topic` cagrilarini ayirt
    eder ve hepsini SIRAYLA kaydeder."""

    def __init__(self, state_lines=None, topics=(HOOK_STATE_TOPIC,), publish_rc=0):
        self.calls = []
        self.published = []
        self._state_lines = state_lines if state_lines is not None else []
        self._topics = topics
        self._publish_rc = publish_rc
        self.subscribe_started = False

    async def __call__(self, *args, **kwargs):
        self.calls.append(args)
        if "-e" in args:
            self.subscribe_started = True
            return _FakeProc(lines=self._state_lines)
        if "-l" in args:
            return _FakeProc(stdout_bytes="\n".join(self._topics).encode())
        # publish: ["gz","topic","-t",topic,"-m",type,"-p",payload]
        topic = args[args.index("-t") + 1]
        payload = args[args.index("-p") + 1]
        self.published.append((topic, payload))
        return _FakeProc(returncode=self._publish_rc)


def _client(fake_exec, **kw):
    kw.setdefault("discovery_settle_s", 0.01)
    return GzHookClient(payload_model_name=_PAYLOAD, vehicle_model_name=_VEHICLE,
                        pose_monitor=_FakePoseMonitor(), subprocess_exec=fake_exec, **kw)


class _FakePoseMonitor:
    def __init__(self, poses=None):
        self._poses = poses or {}

    def get(self, name):
        return self._poses.get(name)


# ---------------------------------------------------------------------------
# 1. PARSER -- protobuf default-value omission (ZORUNLU TEST)
# ---------------------------------------------------------------------------

def test_parser_decodes_real_boolean_encoding_true_false_true():
    """ZORUNLU KANIT: gz.msgs.Boolean{data:false} text encoding'de HİÇBİR
    satır üretmez (protobuf default-value omission) -- `false`'un tek
    işareti BOŞ bir mesaj gövdesidir.

    Legacy gz_payload_actuator.py::HookStateMonitor `data:` satırı aradığı
    için _attached'i asla False yapamıyor. Bu test, aynı hatanın burada
    TEKRARLANMADIĞINI true -> false -> true dizisiyle kanıtlar."""
    client = _client(_FakeExec())
    seen = []

    for line in _REAL_TRUE + _REAL_FALSE + _REAL_TRUE:
        client._consume_line(line)
        seen.append(client.hook_state())

    # Her mesaj ayiricisinda state guncellenir: True, False, True.
    assert client.hook_state() is True
    transitions = [s for i, s in enumerate(seen)
                   if i == 0 or s is not seen[i - 1]]
    assert transitions == [None, True, False, True]


def test_parser_never_looks_for_a_data_false_line():
    """`data: false` satiri HIC GELMEZ; sadece bos govde gelir. Parser bunu
    False olarak cozmeli."""
    client = _client(_FakeExec())
    client._consume_line("data: true\n")
    client._consume_line("\n")
    assert client.hook_state() is True

    client._consume_line("\n")  # bos govde = false
    assert client.hook_state() is False


def test_parser_accepts_dash_separator_variant():
    """Bazi gz surumleri ayirici olarak `---` basar; ikisi de taninmali."""
    client = _client(_FakeExec())
    for line in ["data: true\n", "---\n", "---\n"]:
        client._consume_line(line)
    assert client.hook_state() is False


def test_unrecognised_body_does_not_corrupt_state():
    """Beklenmedik bir govde state'i BOZMAMALI -- 'bilmiyorum' asla
    'birakildi' olarak okunmamali."""
    client = _client(_FakeExec())
    client._consume_line("data: true\n")
    client._consume_line("\n")
    client._consume_line("garbage: 42\n")
    client._consume_line("\n")
    assert client.hook_state() is True


@pytest.mark.asyncio
async def test_read_loop_decodes_stream_end_to_end():
    """Parser, gercek okuma dongusunun ardinda da ayni sonucu vermeli."""
    exec_ = _FakeExec(state_lines=_REAL_TRUE + _REAL_FALSE)
    client = _client(exec_)
    await client.start()
    await asyncio.sleep(0.05)
    assert client.hook_state() is False
    await client.stop()


# ---------------------------------------------------------------------------
# 2. RACE -- abonelik publish'i beklemez, hazirlik gercek
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_subscription_starts_at_creation_not_at_publish():
    """RACE FIX'in ozu: /hook/state aboneligi create() aninda acilir,
    publish_attach() cagrilmasini BEKLEMEZ. Aksi halde plugin'in 2.485 ms'de
    yayinladigi tek mesaj, ~2 s discovery bitmeden kacirilirdi."""
    exec_ = _FakeExec(state_lines=_REAL_TRUE)
    client = await GzHookClient.create(
        payload_model_name=_PAYLOAD, vehicle_model_name=_VEHICLE,
        pose_monitor=_FakePoseMonitor(), subprocess_exec=exec_,
        discovery_settle_s=0.01)

    assert exec_.subscribe_started is True
    assert exec_.published == [], "create() hicbir sey YAYINLAMAMALI"
    await client.stop()


@pytest.mark.asyncio
async def test_is_state_stream_ready_waits_for_discovery_settle():
    """is_state_stream_ready(), abonelik surecinin dogmasiyla degil,
    discovery yerlesme suresi DOLDUKTAN sonra True donmeli."""
    exec_ = _FakeExec(state_lines=_REAL_TRUE)
    client = _client(exec_, discovery_settle_s=0.3)
    assert client.is_state_stream_ready() is False

    task = asyncio.create_task(client.start())
    await asyncio.sleep(0.05)
    assert exec_.subscribe_started is True, "abonelik hemen acilmali"
    assert client.is_state_stream_ready() is False, \
        "settle suresi dolmadan hazir DENMEMELI"

    await task
    assert client.is_state_stream_ready() is True
    await client.stop()


@pytest.mark.asyncio
async def test_publish_attach_refuses_before_stream_is_ready():
    """Hazir degilken attach YAYINLANMAZ: onayi gozlenemeyecek bir attach,
    joint olussa bile timeout'la biterdi."""
    exec_ = _FakeExec()
    client = _client(exec_)
    assert await client.publish_attach() is False
    assert exec_.published == []


@pytest.mark.asyncio
async def test_publish_detach_is_not_gated_on_readiness():
    """Birakma gozlemlenebilirlik yuzunden ENGELLENMEZ -- payload'i araca
    takili birakmak daha kotu bir sonuc."""
    exec_ = _FakeExec()
    client = _client(exec_)
    assert await client.publish_detach() is True
    assert exec_.published == [(HOOK_DETACH_TOPIC, "data: true")]


@pytest.mark.asyncio
async def test_hook_state_is_buffered_after_the_single_shot_publish():
    """/hook/state latch'siz ve gecis basina TEK KEZ yayinlanir; client
    degeri cache'lemeli ki sonraki okumalar kaybetmesin."""
    exec_ = _FakeExec(state_lines=_REAL_TRUE)
    client = _client(exec_)
    await client.start()
    await asyncio.sleep(0.05)
    assert client.hook_state() is True
    assert client.hook_state() is True  # tekrar okuma da True
    await client.stop()


@pytest.mark.asyncio
async def test_wait_for_hook_state_resolves_on_transition_without_polling():
    """wait_for_hook_state() olay guduml: state daha sonra gelse bile
    cozulmeli, ve backend'de/burada poll dongusu OLMAMALI."""
    exec_ = _FakeExec()
    client = _client(exec_)
    waiter = asyncio.create_task(client.wait_for_hook_state(True))
    await asyncio.sleep(0.01)
    assert not waiter.done()

    client._consume_line("data: true\n")
    client._consume_line("\n")
    assert await asyncio.wait_for(waiter, timeout=1.0) is True


@pytest.mark.asyncio
async def test_wait_for_hook_state_returns_immediately_if_already_there():
    exec_ = _FakeExec()
    client = _client(exec_)
    client._consume_line("data: true\n")
    client._consume_line("\n")
    assert await asyncio.wait_for(client.wait_for_hook_state(True), timeout=1.0) is True


@pytest.mark.asyncio
async def test_wait_for_hook_state_is_cancellable_by_payload_manager():
    """Zaman asimi client'ta DEGIL: PayloadManager'in wait_for'u iptal eder.
    Bekleyis iptal edilebilir olmali."""
    client = _client(_FakeExec())
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(client.wait_for_hook_state(True), timeout=0.05)


# ---------------------------------------------------------------------------
# 3. Protokol yuzeyi
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_attach_sends_stringmsg_with_model_name():
    exec_ = _FakeExec(state_lines=_REAL_TRUE)
    client = _client(exec_)
    await client.start()
    assert await client.publish_attach() is True
    assert exec_.published == [(HOOK_ATTACH_TOPIC, f'data: "{_PAYLOAD}"')]
    await client.stop()


@pytest.mark.asyncio
async def test_publish_returns_false_when_gz_cli_fails():
    exec_ = _FakeExec(publish_rc=1)
    client = _client(exec_)
    assert await client.publish_detach() is False


@pytest.mark.asyncio
async def test_publish_returns_false_when_gz_missing():
    async def _missing(*a, **kw):
        raise FileNotFoundError("gz")
    client = _client(_FakeExec())
    client._subprocess_exec = _missing
    assert await client.publish_detach() is False


def test_distance_reads_from_pose_cache():
    client = GzHookClient(
        payload_model_name=_PAYLOAD, vehicle_model_name=_VEHICLE,
        pose_monitor=_FakePoseMonitor({_PAYLOAD: (0.0, 0.0, 0.0),
                                       _VEHICLE: (0.0, 0.0, 0.9)}),
        subprocess_exec=_FakeExec())
    assert client.read_vehicle_payload_distance() == pytest.approx(0.9)


@pytest.mark.parametrize("poses", [{}, {_PAYLOAD: (0.0, 0.0, 0.0)}, {_VEHICLE: (0.0, 0.0, 0.0)}])
def test_distance_is_none_when_pose_unknown(poses):
    """'Bilmiyorum' asla bir sayiya donusturulmez."""
    client = GzHookClient(payload_model_name=_PAYLOAD, vehicle_model_name=_VEHICLE,
                          pose_monitor=_FakePoseMonitor(poses),
                          subprocess_exec=_FakeExec())
    assert client.read_vehicle_payload_distance() is None


@pytest.mark.parametrize("payload_name,vehicle_name", [
    ("", _VEHICLE), (None, _VEHICLE), (_PAYLOAD, ""), (_PAYLOAD, None)])
def test_constructor_requires_explicit_model_names(payload_name, vehicle_name):
    with pytest.raises(ValueError):
        GzHookClient(payload_model_name=payload_name, vehicle_model_name=vehicle_name)


@pytest.mark.asyncio
async def test_stop_does_not_stop_an_injected_pose_monitor():
    """ADIM C invaryanti: main_gz.py client'a KENDI pose_monitor'unu enjekte
    eder (dynamic_pose/info'ya ikinci bir abonelik acilmasin diye). Client o
    monitor'un SAHIBI degildir -- stop() paylasilan cache'i kapatMAMALI,
    yoksa ayni monitor'u kullanan GzPayloadActuator sessizce poz okuyamaz
    hale gelirdi."""
    class _OwnedMonitor(_FakePoseMonitor):
        def __init__(self):
            super().__init__()
            self.stopped = False

        async def stop(self):
            self.stopped = True

    monitor = _OwnedMonitor()
    exec_ = _FakeExec(state_lines=_REAL_TRUE)
    client = GzHookClient(payload_model_name=_PAYLOAD, vehicle_model_name=_VEHICLE,
                          pose_monitor=monitor, subprocess_exec=exec_,
                          discovery_settle_s=0.01)
    await client.start()
    await client.stop()

    assert monitor.stopped is False, "client enjekte edilen pose_monitor'u durdurdu"
    assert client.is_state_stream_ready() is False


def test_vertical_clearance_is_measured_from_payload_top_not_centre():
    """FLEX-20'nin kapiladigi buyukluk: arac altindan payload USTUNE.
    Phase 5.5 Adim D'nin gercek olcumuyle: arac z=0.339, payload z=0.025,
    yari-yukseklik 0.025 -> aciklik 0.289 (3B merkez-merkez ise 0.317'ydi
    ve 0.30 esigini gecemiyordu)."""
    from gz_system.gz_hook_client import _vertical_clearance

    clearance = _vertical_clearance((0.047, 0.0, 0.025), (0.0, 0.0, 0.339))
    assert clearance == pytest.approx(0.289, abs=1e-6)
    # Esik sabitini KOPYALAMA -- config'ten oku ki FLEX-20 revize
    # edildiginde bu test sessizce eski sayiyi savunmaya devam etmesin.
    from payload import payload_config
    assert clearance < payload_config.FLEX_20_GAZEBO_CAPTURE_ENVELOPE_M, \
        "uretim irtifasinda kapi ACILMALI"


def test_clearance_ignores_horizontal_offset_by_design():
    """Aciklik DIKEYdir: yatay sapma onu degistirmez. Bu kasitli -- 3B
    mesafe semantiginde yatay sapma esigi sisirip kapiyi kapatiyordu
    (Adim D tur 1: yatay 0.292 -> 3B 0.343)."""
    from gz_system.gz_hook_client import _vertical_clearance

    near = _vertical_clearance((0.0, 0.0, 0.025), (0.0, 0.0, 0.339))
    far = _vertical_clearance((5.0, 5.0, 0.025), (0.0, 0.0, 0.339))
    assert near == far


@pytest.mark.parametrize("a,b", [(None, (0.0, 0.0, 0.0)), ((0.0, 0.0, 0.0), None)])
def test_clearance_never_invents_a_number(a, b):
    from gz_system.gz_hook_client import _vertical_clearance

    assert _vertical_clearance(a, b) is None


def test_clearance_goes_through_the_single_module_level_formula(monkeypatch):
    """Backend kendi hesabini tutmadigi icin: client'in metodu modul
    seviyesindeki TEK _vertical_clearance()'a delege etmeli."""
    from gz_system import gz_hook_client as mod

    monkeypatch.setattr(mod, "_vertical_clearance", lambda p, v: 7.0)
    client = GzHookClient(
        payload_model_name=_PAYLOAD, vehicle_model_name=_VEHICLE,
        pose_monitor=_FakePoseMonitor({_PAYLOAD: (0.0, 0.0, 0.0),
                                       _VEHICLE: (0.0, 0.0, 0.9)}),
        subprocess_exec=_FakeExec())
    assert client.read_vehicle_payload_clearance() == 7.0


def test_client_satisfies_the_backend_protocol():
    """GazeboPayloadBackend'in cagirdigi HER isim burada var olmali --
    duck-typing'in sessizce kirilmamasi icin."""
    required = ["publish_attach", "publish_detach", "wait_for_hook_state",
                "hook_state", "is_state_stream_ready",
                "read_vehicle_payload_distance",
                "read_vehicle_payload_clearance"]
    client = _client(_FakeExec())
    for name in required:
        assert callable(getattr(client, name, None)), f"{name} eksik"
    # pose() backend'in protokolunde DEGIL (backend mesafe formulu tutmuyor),
    # ama client'in kendi ic kullanimi ve tani/script'ler icin duruyor.
    assert callable(client.pose)


def test_distance_goes_through_the_single_module_level_formula(monkeypatch):
    """Mesafe formulu TEK yerde: read_vehicle_payload_distance() modul
    seviyesindeki _distance()'a delege etmeli.

    Backend de kendi math.dist'ini tutmayip bu metodu cagirdigi icin, bu test
    'formul degisirse iki yol ayrisir' riskini kapatir: _distance degistirilince
    client'in dondurdugu deger de degisiyor."""
    from gz_system import gz_hook_client as mod

    monkeypatch.setattr(mod, "_distance", lambda a, b: 42.0)
    client = GzHookClient(
        payload_model_name=_PAYLOAD, vehicle_model_name=_VEHICLE,
        pose_monitor=_FakePoseMonitor({_PAYLOAD: (0.0, 0.0, 0.0),
                                       _VEHICLE: (0.0, 0.0, 0.9)}),
        subprocess_exec=_FakeExec())
    assert client.read_vehicle_payload_distance() == 42.0


@pytest.mark.parametrize("a,b", [(None, (0.0, 0.0, 0.0)), ((0.0, 0.0, 0.0), None), (None, None)])
def test_shared_distance_helper_never_invents_a_number(a, b):
    """_distance() None'i sayiya CEVIRMEZ -- 'bilmiyorum' asla 'yakinim'
    olarak okunamaz. Her iki cagiran da bu davranisi miras alir."""
    from gz_system.gz_hook_client import _distance

    assert _distance(a, b) is None
