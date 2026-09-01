"""PHASE 0 unit testleri: PayloadManager orkestrasyonu.

payload_state.py'nin testleri (test_payload_state.py) sadece geçiş
grafiğini sınıyordu -- bu dosya PayloadManager'ın backend'i nasıl
çağırdığını, PayloadResult'ı nasıl kurduğunu ve 2026-08-22 kararlarını
(FLEX-13 ile retract timeout'u, STOW_FAILED dallanması) gerçek (sahte
backend'li) bir orkestrasyon üzerinden doğrular. Gerçek fizik yok --
_FakeBackend her action için anında dönen, kontrol edilebilir bir sahte.
"""
import asyncio

import pytest

from payload import payload_config
from payload.backends.payload_backend import PayloadBackend
from payload.payload_manager import PayloadManager
from payload.payload_state import IllegalPayloadTransitionError
from payload.payload_types import PayloadState


class _FakeBackend(PayloadBackend):
    """Her action/query sonucu constructor'da kontrol edilebilir. slow_*
    parametreleri, FLEX-XX zaman aşımı sarmalamasının gerçekten devrede
    olduğunu kanıtlamak için backend'i kasıtlı olarak yavaşlatır."""

    def __init__(self, deploy_ok=True, capture_ok=True, grapple_ok=True,
                 retract_ok=True, secured=True, lower_ok=True, release_ok=True, stow_ok=True,
                 slow_retract_s=None):
        self.deploy_ok = deploy_ok
        self.capture_ok = capture_ok
        self.grapple_ok = grapple_ok
        self.retract_ok = retract_ok
        self.secured = secured
        self.lower_ok = lower_ok
        self.release_ok = release_ok
        self.stow_ok = stow_ok
        self.slow_retract_s = slow_retract_s
        self.calls = []

    def select_payload(self, target_shape: str) -> None:
        self.selected_payload = target_shape

    async def deploy(self) -> bool:
        self.calls.append("deploy")
        return self.deploy_ok

    async def await_capture(self) -> bool:
        self.calls.append("await_capture")
        return self.capture_ok

    async def grapple(self) -> bool:
        self.calls.append("grapple")
        return self.grapple_ok

    async def retract(self) -> bool:
        self.calls.append("retract")
        if self.slow_retract_s is not None:
            await asyncio.sleep(self.slow_retract_s)
        return self.retract_ok

    async def lower_for_release(self) -> bool:
        self.calls.append("lower_for_release")
        return self.lower_ok

    async def release(self) -> bool:
        self.calls.append("release")
        return self.release_ok

    async def stow(self) -> bool:
        self.calls.append("stow")
        return self.stow_ok

    def is_deployed(self) -> bool:
        return True

    def is_in_capture_zone(self) -> bool:
        return True

    def has_captured(self) -> bool:
        return True

    def is_grappled(self) -> bool:
        return True

    def is_secured(self) -> bool:
        return self.secured

    def has_released(self) -> bool:
        return True


async def _walk_to_transporting(backend) -> PayloadManager:
    """4 komutun her testte tekrar yazılmasını önlemek için ortak kurulum:
    TRANSPORTING'e kadar mutlu yoldan ilerler."""
    mgr = PayloadManager(backend)
    await mgr.catch_box_down()
    await mgr.grapple()
    await mgr.catch_box_up()
    assert mgr.get_state() is PayloadState.TRANSPORTING
    return mgr


async def _drive_to_transporting(manager):
    """FSM'i mesru yoldan TRANSPORTING'e goturur (release() oradan cagrilabilir)."""
    await manager.catch_box_down()
    await manager.grapple()
    await manager.catch_box_up()


@pytest.mark.asyncio
async def test_catch_box_down_happy_path_reaches_captured():
    mgr = PayloadManager(_FakeBackend())
    result = await mgr.catch_box_down()
    assert result.success is True
    assert result.final_state is PayloadState.CAPTURED
    assert result.error_reason is None
    assert mgr.get_state() is PayloadState.CAPTURED


@pytest.mark.asyncio
async def test_catch_box_down_deploy_failure_reaches_deploy_timeout():
    mgr = PayloadManager(_FakeBackend(deploy_ok=False))
    result = await mgr.catch_box_down()
    assert result.success is False
    assert result.final_state is PayloadState.DEPLOY_TIMEOUT
    assert mgr.get_state() is PayloadState.DEPLOY_TIMEOUT


@pytest.mark.asyncio
async def test_catch_box_down_capture_failure_reaches_capture_timeout():
    backend = _FakeBackend(capture_ok=False)
    mgr = PayloadManager(backend)
    result = await mgr.catch_box_down()
    assert result.success is False
    assert result.final_state is PayloadState.CAPTURE_TIMEOUT
    # deploy denendi, capture denendi -- deploy basarisiz olsaydi capture'a hic gecilmeyecekti.
    assert backend.calls == ["deploy", "await_capture"]


@pytest.mark.asyncio
async def test_grapple_before_catch_box_down_is_illegal():
    """State machine, komut sırasını PayloadManager kod yazmadan da
    zorunlu kılıyor mu?"""
    mgr = PayloadManager(_FakeBackend())
    with pytest.raises(IllegalPayloadTransitionError):
        await mgr.grapple()


@pytest.mark.asyncio
async def test_catch_box_up_happy_path_reaches_transporting():
    backend = _FakeBackend()
    mgr = PayloadManager(backend)
    await mgr.catch_box_down()
    await mgr.grapple()
    result = await mgr.catch_box_up()
    assert result.success is True
    assert result.final_state is PayloadState.TRANSPORTING
    assert mgr.get_state() is PayloadState.TRANSPORTING


@pytest.mark.asyncio
async def test_catch_box_up_not_secured_reaches_payload_not_secured():
    """retract() BAŞARILI ama is_secured() False -- ayrı bir failure
    modu, RETRACT_TIMEOUT ile karıştırılmamalı."""
    backend = _FakeBackend(secured=False)
    mgr = PayloadManager(backend)
    await mgr.catch_box_down()
    await mgr.grapple()
    result = await mgr.catch_box_up()
    assert result.success is False
    assert result.final_state is PayloadState.PAYLOAD_NOT_SECURED


@pytest.mark.asyncio
async def test_catch_box_up_retract_failure_reaches_retract_timeout():
    backend = _FakeBackend(retract_ok=False)
    mgr = PayloadManager(backend)
    await mgr.catch_box_down()
    await mgr.grapple()
    result = await mgr.catch_box_up()
    assert result.success is False
    assert result.final_state is PayloadState.RETRACT_TIMEOUT


@pytest.mark.asyncio
async def test_flex_13_retract_timeout_is_actually_enforced(monkeypatch):
    """2026-08-22 karari: retract() artik FLEX-13 ile sarmalaniyor. FLEX-13
    su an TBD (None) oldugu icin burada gecici olarak kucuk bir deger
    monkeypatch'leniyor -- backend'i o degerden daha yavas yaparak
    asyncio.wait_for'in GERCEKTEN devrede oldugunu kanitliyoruz (sadece
    backend'in kendi donus degerine guvenmiyoruz)."""
    monkeypatch.setattr(payload_config, "FLEX_13_RETRACT_TIMEOUT_S", 0.05)
    backend = _FakeBackend(slow_retract_s=1.0)  # FLEX-13'ten kasitli olarak cok yavas
    mgr = PayloadManager(backend)
    await mgr.catch_box_down()
    await mgr.grapple()
    result = await mgr.catch_box_up()
    assert result.success is False
    assert result.final_state is PayloadState.RETRACT_TIMEOUT


@pytest.mark.asyncio
async def test_release_happy_path_reaches_retracted():
    mgr = await _walk_to_transporting(_FakeBackend())
    result = await mgr.release()
    assert result.success is True
    assert result.final_state is PayloadState.RETRACTED
    assert result.error_reason is None
    assert mgr.get_state() is PayloadState.RETRACTED


@pytest.mark.asyncio
async def test_release_failure_reaches_release_timeout():
    mgr = await _walk_to_transporting(_FakeBackend(release_ok=False))
    result = await mgr.release()
    assert result.success is False
    assert result.final_state is PayloadState.RELEASE_TIMEOUT


@pytest.mark.asyncio
async def test_release_with_stow_failure_reaches_stow_failed_but_reports_success():
    """THE 2026-08-22 karari: payload fiziksel olarak birakildi
    (release()=True), ama mekanizma toparlanamadi (stow()=False) --
    PayloadResult.success YINE DE True kalmali (birincil islem basarili),
    ama state STOW_FAILED olmali (get_state() ile gorulebilir) ve
    error_reason anomaliyi anlatmali."""
    mgr = await _walk_to_transporting(_FakeBackend(stow_ok=False))
    result = await mgr.release()

    assert result.success is True
    assert result.final_state is PayloadState.STOW_FAILED
    assert result.error_reason is not None
    assert mgr.get_state() is PayloadState.STOW_FAILED


@pytest.mark.asyncio
async def test_get_state_does_not_mutate_across_repeated_calls():
    mgr = PayloadManager(_FakeBackend())
    await mgr.catch_box_down()
    before = mgr.get_state()
    mgr.get_state()
    mgr.get_state()
    after = mgr.get_state()
    assert before is after is PayloadState.CAPTURED


# ---------------------------------------------------------------------------
# V33 md.17/20: teslimat dizisinin ILK adimi (SERVO2_DOWN)
# Spesifikasyon denetimi (2026-08-24) bunun eksik oldugunu buldu.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_release_lowers_before_releasing():
    """V33 md.17: '45cm'de Servo2 yuku asagi indirir, Servo3 yuku birakir,
    Servo2 ters yonde calisir.' Uc adimin UCU de, bu SIRAYLA calismali."""
    backend = _FakeBackend()
    manager = PayloadManager(backend)
    await _drive_to_transporting(manager)
    backend.calls.clear()

    result = await manager.release()

    assert result.success is True
    assert backend.calls == ["lower_for_release", "release", "stow"]


@pytest.mark.asyncio
async def test_release_aborts_when_lowering_fails():
    """Ilk adim duserse SERVO3_RELEASE DENENMEZ -- indirilmemis bir yuku
    birakmak, onu teslimat irtifasindan dusurmek olurdu."""
    backend = _FakeBackend(lower_ok=False)
    manager = PayloadManager(backend)
    await _drive_to_transporting(manager)
    backend.calls.clear()

    result = await manager.release()

    assert result.success is False
    assert manager.get_state() is PayloadState.RELEASE_TIMEOUT
    assert backend.calls == ["lower_for_release"], \
        f"indirme basarisizken dizi devam etti: {backend.calls}"
    assert "lower_for_release" in result.error_reason


@pytest.mark.asyncio
async def test_lowering_is_not_the_same_call_as_deploy():
    """KRITIK: deploy() YENIDEN CAGRILMAMALI. Gazebo'da deploy()
    /hook/attach yayinlar; teslimat aninda onu cagirmak 'yakala' komutunu
    tekrar gondermek olurdu."""
    backend = _FakeBackend()
    manager = PayloadManager(backend)
    await _drive_to_transporting(manager)
    backend.calls.clear()

    await manager.release()

    assert "deploy" not in backend.calls, \
        "teslimat dizisi deploy() cagirdi -- Gazebo'da attach yeniden yayinlanirdi"
