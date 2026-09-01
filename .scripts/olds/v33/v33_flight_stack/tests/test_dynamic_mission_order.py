"""Dinamik tespit sırası (2026-08-24 operatör kararı) — uçtan uca kapsam.

V33 spec md.6/11: hangi şekil önce tespit edilip kilitlenirse o işlenir,
1st_mission/2nd_mission etiketleri GERÇEK sırayı yansıtır.

Bu dosya HER İKİ SIRAYI da simetrik olarak sürer -- SITL'de üçgen-önce
senaryosu üretilemese bile kod seviyesinde iki yönün de kapsandığının
kanıtıdır (bkz. payload/KNOWN_ISSUES.md).
"""
import pytest

from core.mission.interlock import PayloadInterlock
from core.mission.gorev3_pickup import Gorev3PickupPhase
from core.mission.gorev3_redrop import Gorev3RedropPhase
from core.mission.mission_v3_state import MissionV3State
from core.mission.rectangle_alignment_strategy import RectangleAlignmentStrategy
from core.config.parameters import VERIFICATION_MARKER
from core.position_log.position_store import PositionStore
from payload.backends.gazebo_payload_backend import GazeboPayloadBackend

from mocks.mock_camera_source import MockCameraSource
from mocks.mock_flight_backend import MockFlightBackend
from mocks.mock_payload_manager import MockPayloadManager
from test_gorev3_pickup import _RecordingCentering

HEX = "MAVI_ALTIGEN"
TRI = "KIRMIZI_UCGEN"
_MODELS = {HEX: "payload_red", TRI: "payload_blue"}


class _Detector:
    """Verilen dikdörtgeni gorunur tutar; alindiktan sonra kaybolur."""

    def __init__(self, rectangle):
        self.rectangle = rectangle
        self.picked_up = False

    async def detect(self, frame):
        if self.picked_up:
            return []
        from core.detection.types import Detection
        return [Detection(shape_type=self.rectangle, confidence=0.9,
                          center_px=(320, 240), bbox_px=(300, 220, 340, 260),
                          rotation_deg=15.0)]


class _Triggering(MockPayloadManager):
    def __init__(self, detector, **kw):
        super().__init__(**kw)
        self._detector = detector

    async def catch_box_up(self):
        result = await super().catch_box_up()
        if result.success:
            self._detector.picked_up = True
            self._still_secured = True
        return result


def _state_with_order(first: str, second: str) -> MissionV3State:
    state = MissionV3State(PayloadInterlock())
    marks = {HEX: state.mark_hexagon_done, TRI: state.mark_triangle_done}
    marks[first]()
    marks[second]()
    return state


def _store(tmp_path, *shapes):
    store = PositionStore(str(tmp_path / "p.json"))
    for i, shape in enumerate(shapes):
        store.try_save(shape, 0.9, True, True, (41.0 + i, 29.0 + i, 15.0), "ilk" if i == 0 else "ikinci")
    return store


# ---------------------------------------------------------------------------
# 1. mission_order iki yönde de gerçek sırayı yansıtır
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("first,second", [(HEX, TRI), (TRI, HEX)])
def test_labels_follow_detection_order(first, second):
    state = _state_with_order(first, second)
    assert state.first_mission_shape == first
    assert state.second_mission_shape == second
    assert state.mission_order["1st_mission"].shape == first
    assert state.mission_order["2nd_mission"].shape == second


# ---------------------------------------------------------------------------
# 2. Görev 3 alma: 1st_mission'a göre hedef + dikdörtgen + payload seçimi
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("first,second", [(HEX, TRI), (TRI, HEX)])
async def test_pickup_targets_the_real_first_mission(tmp_path, first, second):
    """KRİTİK: üçgen önce tamamlandıysa Görev 3 ÜÇGEN'e döner ve MAVİ
    dikdörtgeni arar -- eskiden ikisi de sabitti."""
    state = _state_with_order(first, second)
    detector = _Detector(VERIFICATION_MARKER[first])
    manager = _Triggering(detector)
    centering = _RecordingCentering()
    phase = Gorev3PickupPhase(MockFlightBackend(), MockCameraSource(), detector,
                              manager, _store(tmp_path, first, second),
                              RectangleAlignmentStrategy(), centering,
                              mission_v3_state=state)

    assert await phase.run() is True

    assert phase.target_rectangle == VERIFICATION_MARKER[first]
    assert centering.center_calls[0][0] == VERIFICATION_MARKER[first]
    assert manager.selected_payload == first, \
        "backend'e yanlis payload bildirildi"


@pytest.mark.asyncio
@pytest.mark.parametrize("first,second", [(HEX, TRI), (TRI, HEX)])
async def test_redrop_targets_the_real_second_mission(tmp_path, first, second):
    state = _state_with_order(first, second)
    manager = MockPayloadManager()
    centering = _RecordingCentering()
    phase = Gorev3RedropPhase(None, manager, _store(tmp_path, first, second),
                              centering, mission_v3_state=state)

    assert await phase.run() is True
    assert centering.center_calls[-1][0] == second, \
        f"birakma hedefi {second} olmaliydi"


# ---------------------------------------------------------------------------
# 3. Backend hedef seçimi (select_payload) iki yönde de doğru modele çevirir
# ---------------------------------------------------------------------------

class _Client:
    def __init__(self):
        self.payload_model_name = "payload_red"

    def set_payload_model_name(self, name):
        self.payload_model_name = name


@pytest.mark.parametrize("shape,expected", [(HEX, "payload_red"), (TRI, "payload_blue")])
def test_select_payload_translates_shape_to_model(shape, expected):
    client = _Client()
    backend = GazeboPayloadBackend(client, payload_model_name="payload_red",
                                   vehicle_model_name="x500",
                                   payload_models_by_shape=_MODELS)

    backend.select_payload(shape)

    assert backend._payload_model_name == expected
    assert client.payload_model_name == expected, \
        "client guncellenmedi -- backend ile sessizce ayrisirdi"


def test_select_payload_rejects_unknown_shape_when_map_configured():
    """Harita doluyken bilinmeyen sekil SESSIZ bir varsayilana DUSMEMELI --
    yanlis payload'a kaynaklanma riski."""
    backend = GazeboPayloadBackend(_Client(), payload_model_name="payload_red",
                                   vehicle_model_name="x500",
                                   payload_models_by_shape=_MODELS)
    with pytest.raises(KeyError):
        backend.select_payload("KIRMIZI_DIKDORTGEN")


def test_select_payload_keeps_current_model_when_no_map():
    """Harita hic enjekte edilmemisse (eski/test yolu) mevcut model korunur."""
    client = _Client()
    backend = GazeboPayloadBackend(client, payload_model_name="payload_red",
                                   vehicle_model_name="x500")
    backend.select_payload(TRI)
    assert backend._payload_model_name == "payload_red"
