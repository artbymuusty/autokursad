"""
Mission Flow V3 — F0 DoD: state/config iskeleti birim testleri (uçuş YOK).

Kapsam: core/mission/mission_v3_state.py + mission_v3_types.py. PayloadInterlock
zaten kendi testlerine sahip (varsa) -- burada sadece MissionV3State'in onu
doğru sardığı ve GERÇEK yarışma kuralını (Mavi Altıgen -> Kırmızı Üçgen sabit
sırası, Görev 2 Rapor Bölüm 11.1) bozmadığı doğrulanıyor.
"""
import json

import pytest

from core.mission.interlock import PayloadInterlock
from core.mission.mission_v3_state import HEXAGON_SHAPE, TRIANGLE_SHAPE, MissionV3State
from core.mission.mission_v3_types import GpsPos
from core.telemetry.event_bus import EventBus
from core.telemetry.event_store import EventStore, replay


def _gps(alt: float) -> GpsPos:
    return GpsPos(lat=41.0, lon=29.0, rel_alt_m=alt, timestamp_utc="2026-08-20T00:00:00+00:00")


class _Collector:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


def _state() -> tuple[MissionV3State, _Collector]:
    collector = _Collector()
    return MissionV3State(PayloadInterlock(publisher=collector), publisher=collector), collector


def test_initial_state_is_all_false_zero():
    state, _ = _state()
    assert state.hexagon_done is False
    assert state.triangle_done is False
    assert state.completed_count == 0
    assert state.rectangle_scan_enabled is False
    assert state.mission_order == {}


def test_hexagon_then_triangle_completes_in_detection_order():
    """YENİDEN YAZILDI (2026-08-24): eskiden "fixed order" idi. Altıgen
    önce tespit edilirse 1st_mission altıgen olur -- artık sabit olduğu
    için değil, GERÇEKTEN önce tamamlandığı için."""
    state, collector = _state()

    state.record_payload_ortalama(HEXAGON_SHAPE, _gps(5.0))
    state.mark_hexagon_done()
    assert state.hexagon_done is True
    assert state.completed_count == 1
    assert state.rectangle_scan_enabled is False  # henüz 2 değil
    assert "1st_mission" in state.mission_order
    assert state.mission_order["1st_mission"].shape == HEXAGON_SHAPE
    assert state.mission_order["1st_mission"].pos_5m.rel_alt_m == 5.0

    state.record_payload_ortalama(TRIANGLE_SHAPE, _gps(5.0))
    state.mark_triangle_done()
    assert state.completed_count == 2
    assert state.rectangle_scan_enabled is True
    assert state.mission_order["2nd_mission"].shape == TRIANGLE_SHAPE

    codes = [e.code for e in collector.events]
    assert codes.count("GOREV_V3_SUCCESS") == 2


def test_triangle_first_is_now_accepted_and_becomes_1st_mission():
    """YENİDEN YAZILDI (2026-08-24) -- eskiden bu test üçgen-önce'nin
    REDDEDİLDİĞİNİ doğruluyordu. Artık asıl istenen davranış budur:
    Kırmızı Üçgen önce tespit edilirse 1st_mission ÜÇGEN olur."""
    state, collector = _state()

    state.record_payload_ortalama(TRIANGLE_SHAPE, _gps(5.0))
    state.mark_triangle_done()

    assert state.completed_count == 1
    assert state.mission_order["1st_mission"].shape == TRIANGLE_SHAPE
    assert state.first_mission_shape == TRIANGLE_SHAPE
    assert "2nd_mission" not in state.mission_order
    assert not any(e.code == "INTERLOCK_VIOLATION_BLOCKED" for e in collector.events)

    state.mark_hexagon_done()
    assert state.mission_order["2nd_mission"].shape == HEXAGON_SHAPE
    assert state.second_mission_shape == HEXAGON_SHAPE


@pytest.mark.parametrize("first,second", [
    (HEXAGON_SHAPE, TRIANGLE_SHAPE),
    (TRIANGLE_SHAPE, HEXAGON_SHAPE),
])
def test_mission_order_follows_real_detection_order(first, second):
    """SPEC md.11: "İlk başarı completed_count==0 iken 1st_mission, ikinci
    başarı completed_count==1 iken 2nd_mission." Her iki sıra da geçerli
    ve etiketler GERÇEK sırayı yansıtır."""
    state, _ = _state()
    marks = {HEXAGON_SHAPE: state.mark_hexagon_done,
             TRIANGLE_SHAPE: state.mark_triangle_done}

    marks[first]()
    assert state.mission_order["1st_mission"].shape == first
    marks[second]()
    assert state.mission_order["2nd_mission"].shape == second
    assert state.completed_count == 2
    assert state.rectangle_scan_enabled is True


def test_same_shape_marked_twice_does_not_duplicate_order():
    """Savunma: aynı şekil iki kez işaretlenirse sıraya iki kez
    eklenmemeli, yoksa 2nd_mission yanlış şekli gösterirdi."""
    state, _ = _state()
    state.mark_triangle_done()
    state.mark_triangle_done()
    assert state.first_mission_shape == TRIANGLE_SHAPE
    assert state.second_mission_shape is None


def test_payload_ortalama_round_trip():
    state, _ = _state()
    assert state.get_payload_ortalama(HEXAGON_SHAPE) is None
    state.record_payload_ortalama(HEXAGON_SHAPE, _gps(5.0))
    recorded = state.get_payload_ortalama(HEXAGON_SHAPE)
    assert recorded.rel_alt_m == 5.0
    assert recorded.lat == 41.0


def test_events_persist_to_jsonl_via_existing_event_store(tmp_path):
    """DoD: örnek JSONL çıktısı -- mevcut EventBus/EventStore mekanizması
    üzerinden, yeni bir persist yolu icat etmeden."""
    bus = EventBus(mission_id="v3-f0-test")
    store = EventStore(mission_id="v3-f0-test", log_dir=str(tmp_path))
    bus.subscribe(store.on_event)
    store.start()

    state = MissionV3State(PayloadInterlock(), publisher=bus)
    state.record_payload_ortalama(HEXAGON_SHAPE, _gps(5.0))
    state.mark_hexagon_done()

    store.stop(timeout_s=2.0)

    records = list(replay(store.path))
    assert any(r["code"] == "GOREV_V3_SUCCESS" for r in records)
    success = next(r for r in records if r["code"] == "GOREV_V3_SUCCESS")
    assert success["data"]["completed_count"] == 1
    assert success["data"]["label"] == "1st_mission"
    assert success["data"]["shape"] == HEXAGON_SHAPE
    assert success["data"]["pos_5m"]["rel_alt_m"] == 5.0

    # Dosya gerçekten JSONL (satır satır geçerli JSON)
    with open(store.path, "r", encoding="utf-8") as f:
        for line in f:
            json.loads(line)
