"""
GOREV I / A -- "first payload" kimligi SIRADAN turer, SEKILDEN degil.

KUSUR: sistem "ilk yuk = MAVI_ALTIGEN" diye sabit varsayiyordu (eski
ADR'den kalma). Gerceklik: ilk yuk, hangi sekil ONCE birakildiysa odur --
ucgen de olabilir (V33 spec madde 11).

Uc katmanda korunuyor:
  1. interlock : first_released / second_released / release_index
  2. gorev2_fsm: PAYLOAD_MISSION_*_COMPLETE olaylari order_index tasir
  3. gorev3    : alma hedefi first_released, tasima hedefi second_released
"""
import pytest

from core.mission.interlock import PayloadInterlock


# --------------------------------------------------------------------
# 1. KATMAN -- interlock kimligi
# --------------------------------------------------------------------
def test_once_ALTIGEN_birakilirsa_ilk_yuk_altigendir():
    il = PayloadInterlock()
    il.mark_released("MAVI_ALTIGEN")
    il.mark_released("KIRMIZI_UCGEN")
    assert il.first_released == "MAVI_ALTIGEN"
    assert il.second_released == "KIRMIZI_UCGEN"
    assert il.release_index("MAVI_ALTIGEN") == 1
    assert il.release_index("KIRMIZI_UCGEN") == 2


def test_once_UCGEN_birakilirsa_ilk_yuk_UCGENDIR():
    """Kusurun ta kendisi: eskiden bu senaryoda da 'ilk yuk altigen'
    varsayiliyordu."""
    il = PayloadInterlock()
    il.mark_released("KIRMIZI_UCGEN")
    il.mark_released("MAVI_ALTIGEN")
    assert il.first_released == "KIRMIZI_UCGEN"
    assert il.second_released == "MAVI_ALTIGEN"
    assert il.release_index("KIRMIZI_UCGEN") == 1
    assert il.release_index("MAVI_ALTIGEN") == 2


def test_birakma_yokken_kimlik_UYDURULMAZ():
    il = PayloadInterlock()
    assert il.first_released is None
    assert il.second_released is None
    assert il.release_index("MAVI_ALTIGEN") is None
    il.mark_released("KIRMIZI_UCGEN")
    assert il.first_released == "KIRMIZI_UCGEN"
    assert il.second_released is None, "ikinci birakma yokken uyduruldu"


def test_eski_SEKIL_tabanli_API_korundu():
    """Dashboard ve eski okuyucular kirilmamali."""
    il = PayloadInterlock()
    il.mark_released("KIRMIZI_UCGEN")
    assert il.payload_2_released is True
    assert il.payload_1_released is False
    assert il.both_released() is False


# --------------------------------------------------------------------
# 3. KATMAN -- Gorev 3 hedefleri (siraya gore)
# --------------------------------------------------------------------
class _KaydedenFaz:
    def __init__(self): self.gorulen = []
    async def run(self, target_shape=None):
        self.gorulen.append(target_shape)
        return False          # pickup basarisiz -> orkestrator erken doner


@pytest.mark.asyncio
@pytest.mark.parametrize("once,sonra", [("MAVI_ALTIGEN", "KIRMIZI_UCGEN"),
                                        ("KIRMIZI_UCGEN", "MAVI_ALTIGEN")])
async def test_gorev3_alma_hedefi_ILK_birakilan(once, sonra):
    from core.mission.gorev3_orchestrator import Gorev3Orchestrator
    il = PayloadInterlock()
    il.mark_released(once)
    il.mark_released(sonra)
    pickup = _KaydedenFaz()
    orch = Gorev3Orchestrator(il, pickup, _KaydedenFaz(), _KaydedenFaz(), _KaydedenFaz())
    await orch.run()
    assert pickup.gorulen == [once], (
        f"alma hedefi ilk birakilan olmaliydi ({once}), gecen: {pickup.gorulen}")


@pytest.mark.asyncio
async def test_gorev3_tasima_hedefi_IKINCI_birakilan():
    from core.mission.gorev3_orchestrator import Gorev3Orchestrator

    class _GecenPickup(_KaydedenFaz):
        async def run(self, target_shape=None):
            self.gorulen.append(target_shape)
            return True       # pickup gecsin ki transport'a ulasilsin

    il = PayloadInterlock()
    il.mark_released("KIRMIZI_UCGEN")
    il.mark_released("MAVI_ALTIGEN")
    pickup, transport = _GecenPickup(), _KaydedenFaz()

    class _GecenRedrop(_KaydedenFaz):
        async def run(self, target_shape=None):
            self.gorulen.append(target_shape); return True

    orch = Gorev3Orchestrator(il, pickup, transport, _GecenRedrop(), _KaydedenFaz())
    await orch.run()
    assert pickup.gorulen == ["KIRMIZI_UCGEN"]
    assert transport.gorulen == ["MAVI_ALTIGEN"], (
        f"tasima hedefi ikinci birakilan olmaliydi, gecen: {transport.gorulen}")
