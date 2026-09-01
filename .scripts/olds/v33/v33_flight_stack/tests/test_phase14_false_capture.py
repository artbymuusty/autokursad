"""PHASE 14 boslugu: YANLIS POZITIF YAKALAMA (false capture).

Test matrisinin C kategorisi payload/ yigininda hic ozel olarak test
edilmemisti. Bu dosya, "yakaladim" denip aslinda yakalanmamis olma
ihtimalinin HER bilinen vektorunu ayri ayri kapatir.

Neden onemli: bu hata sinifi bu projede GERCEKTEN yasandi. 2026-08-21 F3
notu (gz_payload_actuator.py) sunu belgeliyor -- attach, poz yakinligina
bakilarak "dogrulaniyordu"; gercek SITL'de vehicle_z=0.854, payload_z=0.031
olcuIdu, fark tolerans icindeydi ve attach HIC calismamisken mission
"Yuk Alma Basarili" ve ardindan "TUM GOREVLER BASARIYLA BITTI" dedi.
Payload canli sorguda hala orijinal yerindeydi.
"""
import pytest

from payload import PayloadManager, PayloadState
from payload.backends.gazebo_payload_backend import GazeboPayloadBackend
from payload.backends.payload_backend import PayloadBackend

from test_phase6_hybrid_joint_layer import _FakeHookClient, _FakeJointWorld

_PAYLOAD = "payload_red"
_VEHICLE = "x500_mono_cam_down_0"


def _gz(world, **kw):
    client = _FakeHookClient(world, **kw)
    backend = GazeboPayloadBackend(client, payload_model_name=_PAYLOAD,
                                   vehicle_model_name=_VEHICLE)
    return PayloadManager(backend), client


class _LyingBackend(PayloadBackend):
    """Her action'i BASARILI raporlayan ama sorgu tarafi kontrol edilebilen
    backend -- "mekanizma tamam dedi" ile "fiziksel gerceklik" ayrimini
    izole etmek icin."""

    def __init__(self, secured=True, captured=True, released=False):
        self._secured, self._captured, self._released = secured, captured, released

    def select_payload(self, target_shape: str) -> None:
        self.selected_payload = target_shape

    async def deploy(self): return True
    async def await_capture(self): return True
    async def grapple(self): return True
    async def retract(self): return True
    async def lower_for_release(self): return True
    async def release(self): return True
    async def stow(self): return True

    def is_deployed(self): return True
    def is_in_capture_zone(self): return True
    def has_captured(self): return self._captured
    def is_grappled(self): return self._captured
    def is_secured(self): return self._secured
    def has_released(self): return self._released


# ---------------------------------------------------------------------------
# C1. Mesafe yalani: envelope disindayken yakalama RAPORLANAMAZ
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_capture_reported_when_outside_envelope():
    """HookAttachSystem mesafe kontrolu YAPMAZ -- 1 km oteden de kaynaklar.
    Tek koruma FLEX-20 kapisi; gecilemezse CAPTURED'a ULASILMAMALI."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 5.0))
    manager, client = _gz(world)

    result = await manager.catch_box_down()

    assert result.success is False
    assert manager.get_state() is not PayloadState.CAPTURED
    assert client.published == [], "envelope disinda attach yayinlandi"
    assert world.attached is False


# ---------------------------------------------------------------------------
# C2. Gozlenemez yakalama: onay akisi hazir degilken yakalama iddia edilemez
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_capture_reported_when_confirmation_unobservable():
    """/hook/state latch'siz ve tek seferlik. Abonelik hazir degilken
    attach yayinlamak, onayi yapisal olarak kacirmak demekti -- ve bir
    sonraki bayat okuma "yakalandi" gibi gorunebilirdi."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 0.339))
    manager, client = _gz(world, stream_ready=False)

    result = await manager.catch_box_down()

    assert result.success is False
    assert manager.get_state() is not PayloadState.CAPTURED
    assert world.attached is False


# ---------------------------------------------------------------------------
# C3. "Bilmiyorum" asla "yakaladim" degildir
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", ["has_captured", "is_grappled", "is_secured"])
def test_unknown_state_never_reads_as_captured(query):
    """Hic gecis gorulmemisken (hook_state None) hicbir sorgu True
    DONMEMELI -- `is True` karsilastirmalari tam bunun icin."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 0.339))
    _, client = _gz(world)
    backend = GazeboPayloadBackend(client, payload_model_name=_PAYLOAD,
                                   vehicle_model_name=_VEHICLE)

    assert client.hook_state() is None
    assert getattr(backend, query)() is False


def test_unknown_state_never_reads_as_released():
    """Simetrik tuzak: None'i "birakildi" saymak, birakilmamis bir yuku
    birakilmis raporlardi."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 0.339))
    _, client = _gz(world)
    backend = GazeboPayloadBackend(client, payload_model_name=_PAYLOAD,
                                   vehicle_model_name=_VEHICLE)

    assert backend.has_released() is False


# ---------------------------------------------------------------------------
# C4. "Mekanizma tamam dedi" != "yuk elimde"  (2026-08-21 F3 hata sinifi)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mechanism_success_does_not_imply_payload_held():
    """retract() True donse BILE is_secured() False ise TRANSPORTING'e
    GECILMEZ. Bu, F3'te yasanan "hepsi basarili dedi, payload yerinde
    duruyordu" hatasinin dogrudan panzehiri."""
    manager = PayloadManager(_LyingBackend(secured=False))
    await manager.catch_box_down()
    await manager.grapple()

    result = await manager.catch_box_up()

    assert result.success is False
    assert manager.get_state() is PayloadState.PAYLOAD_NOT_SECURED
    assert manager.get_state() is not PayloadState.TRANSPORTING


@pytest.mark.asyncio
async def test_state_machine_cannot_reach_transporting_without_secured_check():
    """Yigin genelinde kanit: SECURED'a giden TEK yol is_secured()
    kontrolunden gecer."""
    manager = PayloadManager(_LyingBackend(secured=False))
    await manager.catch_box_down()
    await manager.grapple()
    await manager.catch_box_up()

    reached = {r.new_state for r in manager._state_machine.history}
    assert PayloadState.SECURED not in reached
    assert PayloadState.TRANSPORTING not in reached


# ---------------------------------------------------------------------------
# C5. Hayalet tasima: FSM tasiyorum der, fizik demez
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_carrying_a_phantom_is_detectable_mid_mission():
    """get_state() HAFIZADIR. Yuk transit sirasinda dusse bile TRANSPORTING
    gorunur; is_still_secured() backend'e sorup yalani bozar."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 0.339))
    manager, client = _gz(world)
    await manager.catch_box_down()
    await manager.grapple()
    await manager.catch_box_up()
    assert manager.get_state() is PayloadState.TRANSPORTING
    assert manager.is_still_secured() is True

    world.detach()                 # yuk transit sirasinda dustu
    client._set(False)

    assert manager.get_state() is PayloadState.TRANSPORTING, "FSM hala tasiyorum der"
    assert manager.is_still_secured() is False, "fiziksel sorgu yalani bozmali"


# ---------------------------------------------------------------------------
# C6. Yakaladim ama payload beni izlemiyor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_capture_without_physical_following_is_visible():
    """Yakalamanin FIZIKSEL testi: arac yukselince payload izliyor mu.
    Joint yokken izlemez -- ve bu, "yakaladim" iddiasinin yalanlandigi
    gozlemin ta kendisidir (Phase 6 acceptance'in olctugu sey)."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 0.339))
    manager, client = _gz(world)
    await manager.catch_box_down()
    payload_before = client.pose(_PAYLOAD)

    world.detach()                 # joint aslinda yok
    client._set(False)
    world.move_vehicle_to((0.0, 0.0, 0.839))

    assert client.pose(_PAYLOAD) == payload_before, "izlemedigi halde izliyor gorundu"
    assert manager.is_still_secured() is False


# ---------------------------------------------------------------------------
# C7. Bayat durum: onceki dongunun sonucu yeni yakalama sayilamaz
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_completed_cycle_leaves_no_stale_capture():
    """Tam bir dongu (al -> tasi -> birak) bittikten sonra durum
    'yakalanmis' olarak KALMAMALI -- kalsaydi sonraki dongu hic attach
    yapmadan yakaladim derdi."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 0.339))
    manager, client = _gz(world)
    await manager.catch_box_down()
    await manager.grapple()
    await manager.catch_box_up()
    await manager.release()

    assert manager.get_state() is PayloadState.RETRACTED
    assert client.hook_state() is False
    backend = GazeboPayloadBackend(client, payload_model_name=_PAYLOAD,
                                   vehicle_model_name=_VEHICLE)
    assert backend.has_captured() is False
    assert backend.is_secured() is False


# ---------------------------------------------------------------------------
# C8. Yakalama basarisizsa CAPTURED'a hic ulasilmaz
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_failed_await_capture_never_reaches_captured():
    class _NoCapture(_LyingBackend):
        async def await_capture(self): return False

    manager = PayloadManager(_NoCapture())
    result = await manager.catch_box_down()

    assert result.success is False
    assert manager.get_state() is PayloadState.CAPTURE_TIMEOUT
    reached = {r.new_state for r in manager._state_machine.history}
    assert PayloadState.CAPTURED not in reached
