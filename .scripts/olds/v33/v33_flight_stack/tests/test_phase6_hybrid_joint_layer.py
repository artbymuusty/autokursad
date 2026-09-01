"""PHASE 6 entegrasyon testleri: Hybrid Joint Layer (CI'da calisan surum).

Phase 6'nin acceptance kriteri: "Capture -> Validate -> Create Joint ->
Joint State -> Payload physically follows UAV." Gercek fizik dogrulamasi
SITL'de yapilir (tools/acceptance_phase6_gazebo.py); bu dosya AYNI zinciri
CI'da, gercek Gazebo olmadan surer.

Buradaki fake, joint'in GERCEK semantigini taklit eder:
  * /hook/state ancak attach yayinlandiktan SONRA true olur (uydurma bir
    "hep takili" degil).
  * Joint olustuktan sonra payload, aracin hareketini AYNI goreli konumu
    koruyarak izler -- HookAttachSystem'in "fixed" joint'i mevcut goreli
    donusumde kaynaklar, cocugu ebeveyne CEKMEZ (Phase 5.5 Adim D'de
    olculdu: 2.0 m'de bile payload kipirdamadi).
  * Attach yokken payload YERINDE KALIR -- takip iddiasi ancak joint
    varken dogru olabilsin diye.

Kritik: test payload pozunu araca ELLE KOPYALAMAZ. Fake, aracin
hareketini bagimsiz olarak uygular ve testler payload'in pozunu ayri bir
"gozlemci" okumasindan dogrular -- Phase 6'nin "payload pose'u elle UAV'a
kopyalanmaz" sartinin CI karsiligi.
"""
import asyncio

import pytest

from payload import PayloadManager, PayloadState
from payload.backends.gazebo_payload_backend import GazeboPayloadBackend
from gz_system.gz_hook_client import _vertical_clearance

_PAYLOAD = "payload_red"
_VEHICLE = "x500_mono_cam_down_0"


class _FakeJointWorld:
    """Gazebo'nun yerine gecen minik dunya: poz tutar, attach'liyken
    aracin hareketini payload'a JOINT UZERINDEN yansitir."""

    def __init__(self, payload_pose=(0.0, 0.0, 0.025), vehicle_pose=(0.0, 0.0, 0.30)):
        self.payload_pose = payload_pose
        self.vehicle_pose = vehicle_pose
        self.attached = False
        self._locked_offset = None

    def attach(self) -> None:
        # "fixed" joint MEVCUT goreli donusumde kaynaklar -- payload
        # CEKILMEZ, oldugu yerde kalir ve ofset dondurulur.
        self._locked_offset = tuple(
            p - v for p, v in zip(self.payload_pose, self.vehicle_pose))
        self.attached = True

    def detach(self) -> None:
        self.attached = False
        self._locked_offset = None

    def move_vehicle_to(self, new_pose) -> None:
        """Araci tasir. Attach'liyse payload joint uzerinden IZLER."""
        self.vehicle_pose = new_pose
        if self.attached:
            self.payload_pose = tuple(
                v + o for v, o in zip(new_pose, self._locked_offset))


class _FakeHookClient:
    """GzHookClient'in protokol yuzeyi, _FakeJointWorld uzerine."""

    def __init__(self, world: _FakeJointWorld, stream_ready=True):
        self.world = world
        self._stream_ready = stream_ready
        self._state = None
        self._event = asyncio.Event()
        self.published = []

    async def publish_attach(self, model_name=None):
        self.published.append("attach")
        if not self._stream_ready:
            return False
        self.world.attach()
        self._set(True)
        return True

    async def publish_detach(self):
        self.published.append("detach")
        self.world.detach()
        self._set(False)
        return True

    def _set(self, value):
        self._state = value
        self._event.set()

    async def wait_for_hook_state(self, expected):
        while True:
            self._event.clear()
            if self._state is expected:
                return True
            await self._event.wait()

    def hook_state(self):
        return self._state

    def is_state_stream_ready(self):
        return self._stream_ready

    def pose(self, model_name):
        return (self.world.payload_pose if model_name == _PAYLOAD
                else self.world.vehicle_pose)

    def read_vehicle_payload_distance(self):
        from gz_system.gz_hook_client import _distance
        return _distance(self.world.payload_pose, self.world.vehicle_pose)

    def read_vehicle_payload_clearance(self):
        return _vertical_clearance(self.world.payload_pose, self.world.vehicle_pose)


def _manager(world, **kw):
    backend = GazeboPayloadBackend(_FakeHookClient(world, **kw),
                                   payload_model_name=_PAYLOAD,
                                   vehicle_model_name=_VEHICLE)
    return PayloadManager(backend), backend._client


# ---------------------------------------------------------------------------
# Zincir: catch_box_down -> grapple -> catch_box_up -> SECURED/TRANSPORTING
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_catch_box_down_captures_at_production_altitude():
    """Uretim irtifasinda (arac z=0.339, Adim D'nin gercek olcumu) kapi
    ACILMALI ve yakalama tamamlanmali. Bu, FLEX-20'nin dikey aciklik
    semantiginin somut regresyon testidir: 3B merkez-merkez semantiginde
    ayni konumda mesafe 0.317 > 0.30 cikip yakalama HIC olmuyordu."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 0.339))
    manager, client = _manager(world)

    result = await manager.catch_box_down()

    assert result.success is True, result.error_reason
    assert manager.get_state() is PayloadState.CAPTURED
    assert client.published == ["attach"]
    assert world.attached is True


@pytest.mark.asyncio
async def test_full_chain_reaches_transporting_via_get_state():
    """Phase 11'in erken surumu: PayloadManager UZERINDEN, backend'e hic
    dokunmadan SECURED'dan gecip TRANSPORTING'e ulasildigi get_state() ile
    dogrulanir."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 0.339))
    manager, _ = _manager(world)

    assert manager.get_state() is PayloadState.IDLE
    assert (await manager.catch_box_down()).success is True
    assert (await manager.grapple()).success is True
    assert manager.get_state() is PayloadState.GRAPPLED
    result = await manager.catch_box_up()

    assert result.success is True, result.error_reason
    # catch_box_up SECURED'dan gecip TRANSPORTING'e ilerler; is_secured()
    # gercek joint bitini okur, uydurma bir True degil.
    assert result.final_state is PayloadState.TRANSPORTING
    assert manager.get_state() is PayloadState.TRANSPORTING


@pytest.mark.asyncio
async def test_catch_box_up_fails_when_joint_absent():
    """is_secured() gercek joint bitini okuyor mu? Joint'i arkadan
    kaldirinca catch_box_up() PAYLOAD_NOT_SECURED'a dusmeli -- yoksa
    "test edilmemis success" varsayilmis olurdu."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 0.339))
    manager, client = _manager(world)
    await manager.catch_box_down()
    await manager.grapple()

    world.detach()
    client._set(False)
    result = await manager.catch_box_up()

    assert result.success is False
    assert manager.get_state() is PayloadState.PAYLOAD_NOT_SECURED


# ---------------------------------------------------------------------------
# ACCEPTANCE: payload UAV'i GERCEKTEN takip ediyor mu
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_payload_follows_uav_after_capture():
    """Phase 6 acceptance'in CI karsiligi: yakalamadan sonra arac 0.5 m
    tirmanir ve payload onu IZLER.

    Payload pozu araca ELLE KOPYALANMAZ: _FakeJointWorld hareketi joint
    uzerinden uygular, test sonucu bagimsiz bir poz okumasindan dogrular."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 0.339))
    manager, client = _manager(world)
    await manager.catch_box_down()

    payload_before = client.pose(_PAYLOAD)
    world.move_vehicle_to((0.0, 0.0, 0.839))   # +0.5 m tirmanis
    payload_after = client.pose(_PAYLOAD)

    assert payload_after[2] == pytest.approx(payload_before[2] + 0.5, abs=1e-6)
    # Goreli konum korunur: "fixed" joint cocugu CEKMEZ, ofseti dondurur.
    assert client.read_vehicle_payload_clearance() == pytest.approx(
        _vertical_clearance(payload_before, (0.0, 0.0, 0.339)), abs=1e-6)


@pytest.mark.asyncio
async def test_payload_does_not_follow_without_capture():
    """Negatif kontrol -- testin kendisi yalan soylemesin: joint YOKKEN
    ayni tirmanista payload YERINDE KALMALI. Bu olmadan yukaridaki test,
    her kosulda gecen bos bir iddia olurdu."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 0.339))
    _, client = _manager(world)

    payload_before = client.pose(_PAYLOAD)
    world.move_vehicle_to((0.0, 0.0, 0.839))

    assert client.pose(_PAYLOAD) == payload_before


@pytest.mark.asyncio
async def test_payload_follows_only_until_release():
    """Birakmadan sonra takip BITMELI."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 0.339))
    manager, client = _manager(world)
    await manager.catch_box_down()
    await manager.grapple()
    await manager.catch_box_up()
    await manager.release()

    payload_before = client.pose(_PAYLOAD)
    world.move_vehicle_to((0.0, 0.0, 2.0))

    assert client.pose(_PAYLOAD) == payload_before
    assert manager.get_state() is PayloadState.RETRACTED


# ---------------------------------------------------------------------------
# Kapi davranisi
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_capture_refused_when_vehicle_too_high():
    """Envelope disinda attach YAYINLANMAZ ve joint OLUSMAZ."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 2.0))
    manager, client = _manager(world)

    result = await manager.catch_box_down()

    assert result.success is False
    assert manager.get_state() is PayloadState.DEPLOY_TIMEOUT
    assert client.published == [], "envelope disinda simulasyona komut gitti"
    assert world.attached is False


@pytest.mark.asyncio
async def test_capture_refused_when_state_stream_not_ready():
    """Abonelik hazir degilken de joint OLUSMAMALI -- Phase 5.5'te bulunan
    race'in bu katmanda tekrarlanmadiginin kaniti."""
    world = _FakeJointWorld(vehicle_pose=(0.0, 0.0, 0.339))
    manager, _ = _manager(world, stream_ready=False)

    result = await manager.catch_box_down()

    assert result.success is False
    assert world.attached is False
