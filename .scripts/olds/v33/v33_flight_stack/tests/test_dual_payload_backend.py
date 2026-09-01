"""PHASE 6.5: DualPayloadBackend testleri.

dual_backend_adapter.py::DualPayloadActuator'in kanitlanmis fan-out
sozlesmesinin payload/ tarafinda da AYNEN gecerli oldugunu sinar:
ikisini birden sur, uyumsuzlukta uyar, REAL'i otoriter dondur.
"""
import asyncio

import pytest

from payload.backends.dual_payload_backend import DualPayloadBackend
from payload.backends.payload_backend import PayloadBackend

_ACTIONS = ["deploy", "await_capture", "grapple", "retract",
            "lower_for_release", "release", "stow"]
_QUERIES = ["is_deployed", "is_in_capture_zone", "has_captured",
            "is_grappled", "is_secured", "has_released"]


class _FakeBackend(PayloadBackend):
    def __init__(self, result=True, query_result=True, query_raises=None, delay=0.0):
        self.result = result
        self.query_result = query_result
        self.query_raises = query_raises
        self.delay = delay
        self.calls = []

    async def _act(self, name):
        self.calls.append(name)
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.result

    def select_payload(self, target_shape: str) -> None:
        self.selected_payload = target_shape

    async def deploy(self): return await self._act("deploy")
    async def await_capture(self): return await self._act("await_capture")
    async def grapple(self): return await self._act("grapple")
    async def retract(self): return await self._act("retract")
    async def lower_for_release(self): return await self._act("lower_for_release")
    async def release(self): return await self._act("release")
    async def stow(self): return await self._act("stow")

    def _query(self, name):
        self.calls.append(name)
        if self.query_raises is not None:
            raise self.query_raises
        return self.query_result

    def is_deployed(self): return self._query("is_deployed")
    def is_in_capture_zone(self): return self._query("is_in_capture_zone")
    def has_captured(self): return self._query("has_captured")
    def is_grappled(self): return self._query("is_grappled")
    def is_secured(self): return self._query("is_secured")
    def has_released(self): return self._query("has_released")


def test_dual_backend_is_a_payload_backend():
    assert isinstance(DualPayloadBackend(_FakeBackend(), _FakeBackend()), PayloadBackend)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", _ACTIONS)
async def test_action_reaches_both_backends(action):
    real, sim = _FakeBackend(), _FakeBackend()
    await getattr(DualPayloadBackend(real, sim), action)()
    assert real.calls == [action] and sim.calls == [action]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", _ACTIONS)
async def test_real_result_is_authoritative(action):
    """Uyumsuzlukta REAL doner -- dual mod bir DOGRULAMA aracidir, sim
    gercegin yerine karar VERMEZ (DualPayloadActuator ile ayni secim)."""
    dual = DualPayloadBackend(_FakeBackend(result=False), _FakeBackend(result=True))
    assert await getattr(dual, action)() is False

    dual = DualPayloadBackend(_FakeBackend(result=True), _FakeBackend(result=False))
    assert await getattr(dual, action)() is True


@pytest.mark.asyncio
async def test_divergence_is_logged(caplog):
    dual = DualPayloadBackend(_FakeBackend(result=True), _FakeBackend(result=False))
    with caplog.at_level("WARNING"):
        await dual.deploy()
    assert "DUAL UYUMSUZLUK" in caplog.text


@pytest.mark.asyncio
async def test_agreement_is_not_logged(caplog):
    dual = DualPayloadBackend(_FakeBackend(result=True), _FakeBackend(result=True))
    with caplog.at_level("WARNING"):
        await dual.deploy()
    assert "DUAL UYUMSUZLUK" not in caplog.text


@pytest.mark.asyncio
async def test_both_run_concurrently_not_sequentially():
    """gather ile PARALEL surulmeli: iki 0.2s'lik backend toplamda
    0.4s'e yakin DEGIL, 0.2s'e yakin surmeli."""
    dual = DualPayloadBackend(_FakeBackend(delay=0.2), _FakeBackend(delay=0.2))
    start = asyncio.get_event_loop().time()
    await dual.deploy()
    assert asyncio.get_event_loop().time() - start < 0.35


@pytest.mark.parametrize("query", _QUERIES)
def test_queries_go_to_real_only(query):
    """Query'ler REAL'e sorulur -- sim'in cevabini 'gercek' diye sunmak
    dual modun amacini tersine cevirirdi."""
    real, sim = _FakeBackend(query_result=True), _FakeBackend(query_result=False)
    assert getattr(DualPayloadBackend(real, sim), query)() is True
    assert real.calls == [query] and sim.calls == []


@pytest.mark.parametrize("query", _QUERIES)
def test_real_query_gap_is_not_masked_by_sim(query):
    """Real'in NotImplementedError'i sim'in cevabiyla GIZLENMEZ: donanimin
    durumu bilinmiyorsa, bilinmiyor olarak yukselir."""
    dual = DualPayloadBackend(_FakeBackend(query_raises=NotImplementedError("sensor yok")),
                              _FakeBackend(query_result=True))
    with pytest.raises(NotImplementedError):
        getattr(dual, query)()
