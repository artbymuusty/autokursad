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


# --------------------------------------------------------------------
# ARANAN SINIF -- canli B1 kosumunda yakalanan kusur
# --------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("shape,beklenen", [
    ("MAVI_ALTIGEN", "KIRMIZI_DIKDORTGEN"),   # altigene KIRMIZI yuk
    ("KIRMIZI_UCGEN", "MAVI_DIKDORTGEN"),     # ucgene MAVI yuk
])
async def test_aranan_dikdortgen_sinifi_YUKUN_rengine_gore(shape, beklenen, tmp_path):
    """B1 kosumu (2026-09-04): ucgen once birakildi, faz DOGRU hedefe gitti
    ama RectangleAlignmentStrategy sabit KIRMIZI_DIKDORTGEN ariyordu;
    transit_complete'ten 8.6 s sonra 'bulunamadi' ile dustu ve dis deneme
    dongusu HIC calisamadi."""
    from core.mission.gorev3_pickup import Gorev3PickupPhase
    from core.mission.rectangle_alignment_strategy import RectangleAlignmentStrategy
    from core.position_log.position_store import PositionStore
    from mocks.mock_flight_backend import MockFlightBackend
    from mocks.mock_camera_source import MockCameraSource
    from mocks.mock_payload_actuator import MockPayloadActuator

    strateji = RectangleAlignmentStrategy()
    faz = Gorev3PickupPhase(MockFlightBackend(), MockCameraSource(), None,
                            MockPayloadActuator(),
                            PositionStore(str(tmp_path / "p.json")),
                            strateji, centering=None)
    try:
        await faz.run(shape)          # konum kayitli degil -> erken RuntimeError
    except Exception:
        pass
    assert faz._rect_class == beklenen
    assert strateji._rect_class == beklenen, \
        "strateji hala eski sinifi ariyor -- B1 kusuru geri geldi"


# --------------------------------------------------------------------
# O-A -- AKTUATOR de dogru yuku olcmeli (B2 kosumunda olculen kusur)
# --------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("shape,beklenen_renk,beklenen_sinif", [
    ("MAVI_ALTIGEN", "red", "KIRMIZI_DIKDORTGEN"),
    ("KIRMIZI_UCGEN", "blue", "MAVI_DIKDORTGEN"),
])
async def test_aktuator_ALMA_hedefinin_rengini_olcer(shape, beklenen_renk,
                                                     beklenen_sinif, tmp_path):
    """B2 kosumu (2026-09-04): aktuatorun oturma kapisi
    SHAPE_TO_COLOR['MAVI_ALTIGEN'] sabitiyle HER ZAMAN kirmizi yuku
    olcuyordu. Ucgen once birakildiginda arac DOGRU yukun uzerindeyken
    kapi 35.5 m otedeki yanlis yuku olcuyor, lateral 35497 mm okuyor
    (kapi 17.5 mm) ve yakalama HIC mumkun olmuyordu."""
    from core.mission.gorev3_pickup import Gorev3PickupPhase
    from core.mission.rectangle_alignment_strategy import RectangleAlignmentStrategy
    from core.position_log.position_store import PositionStore
    from mocks.mock_flight_backend import MockFlightBackend
    from mocks.mock_camera_source import MockCameraSource
    from mocks.mock_payload_actuator import MockPayloadActuator

    akt = MockPayloadActuator()
    faz = Gorev3PickupPhase(MockFlightBackend(), MockCameraSource(), None, akt,
                            PositionStore(str(tmp_path / "p.json")),
                            RectangleAlignmentStrategy(), centering=None)
    try:
        await faz.run(shape)          # konum kayitli degil -> erken cikis
    except Exception:
        pass
    assert faz._color == beklenen_renk
    assert faz._rect_class == beklenen_sinif
    assert akt._pickup_color == beklenen_renk, (
        "aktuator hala sabit rengi olcuyor -- B2 kusuru geri geldi")


@pytest.mark.parametrize("metot", ["activate_pickup_mechanism",
                                  "activate_drop_mechanism"])
def test_gz_aktuator_metotlarinda_SABIT_renk_kalmadi(metot):
    """Iki OLCUM YOLU da rengi self._pickup_color'dan almali.

    Sinif govdesindeki varsayilan atama ve aciklama yorumu mesru --
    bu test yalnizca metot GOVDELERINE bakar."""
    import inspect
    from gz_system.gz_payload_actuator import GzPayloadActuator
    src = inspect.getsource(getattr(GzPayloadActuator, metot))
    assert 'SHAPE_TO_COLOR["MAVI_ALTIGEN"]' not in src, \
        f"{metot} hala sabit rengi olcuyor -- B2 kusuru geri geldi"
    assert "self._pickup_color" in src, \
        f"{metot} alma renginden okumuyor"
