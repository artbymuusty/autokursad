"""PHASE 6.5: DualPayloadBackend -- Real ve Gazebo backend'lerini birlikte sürer.

dual_system/dual_backend_adapter.py::DualPayloadActuator'ın payload/ paketindeki
karşılığıdır ve o desenin BİREBİR yansımasıdır (yeni bir seçim mekanizması
icat edilmedi -- repoda zaten seçim yok, main_real/main_gz/main_dual
ayrımı entry point düzeyinde yapılıyor):

  * her komut iki backend'e AYNI ANDA (asyncio.gather) gönderilir,
  * sonuçlar farklıysa "DUAL UYUMSUZLUK" uyarısı loglanır,
  * REAL sonucu otoriter kabul edilip döndürülür.

NEDEN REAL OTORİTER: dual mod bir hardware-in-the-loop DOĞRULAMA aracıdır --
sim, gerçeğin ne yaptığını kontrol etmek için yanında koşar, onun yerine
karar vermez. DualPayloadActuator'daki aynı seçim.

Query primitifleri: REAL'e sorulur. Real backend'in query'leri şu an
NotImplementedError'dır (sensör yolu yok, bkz. real_payload_backend.py
TODO(SAFETY)) -- bu KASITLI olarak gizlenmez. Sim'in cevabını "gerçek"
diye sunmak, dual modun tüm amacını (gerçeği gözlemek) tersine çevirirdi:
donanımın durumu bilinmiyorsa, bilinmiyor olarak yükselmelidir.
"""
import asyncio
import logging

from payload.backends.payload_backend import PayloadBackend

logger = logging.getLogger(__name__)


class DualPayloadBackend(PayloadBackend):
    """Real + Gazebo backend'lerini birlikte süren fan-out backend."""

    def __init__(self, real: PayloadBackend, sim: PayloadBackend) -> None:
        self._real = real
        self._sim = sim

    def select_payload(self, target_shape: str) -> None:
        """Her iki backend'e de yansitilir -- ikisi farkli hedefe bakarsa
        dual modun karsilastirmasi anlamsizlasirdi."""
        self._real.select_payload(target_shape)
        self._sim.select_payload(target_shape)

    async def _both(self, name: str) -> bool:
        real_result, sim_result = await asyncio.gather(
            getattr(self._real, name)(), getattr(self._sim, name)())
        if real_result != sim_result:
            logger.warning(
                "DUAL UYUMSUZLUK [%s]: real=%s sim=%s -- gercek ve simule sonuc "
                "farkli, saha ekibi incelemeli", name, real_result, sim_result)
        return real_result

    async def deploy(self) -> bool:
        return await self._both("deploy")

    async def await_capture(self) -> bool:
        return await self._both("await_capture")

    async def grapple(self) -> bool:
        return await self._both("grapple")

    async def retract(self) -> bool:
        return await self._both("retract")

    async def lower_for_release(self) -> bool:
        return await self._both("lower_for_release")

    async def release(self) -> bool:
        return await self._both("release")

    async def stow(self) -> bool:
        return await self._both("stow")

    # -- Query primitifleri: REAL otoriter (bkz. modul docstring'i) --------

    def is_deployed(self) -> bool:
        return self._real.is_deployed()

    def is_in_capture_zone(self) -> bool:
        return self._real.is_in_capture_zone()

    def has_captured(self) -> bool:
        return self._real.has_captured()

    def is_grappled(self) -> bool:
        return self._real.is_grappled()

    def is_secured(self) -> bool:
        return self._real.is_secured()

    def has_released(self) -> bool:
        return self._real.has_released()
