"""
Mission Flow V3 — F1 (Vision Dry-Run, uçuş YOK).

DoD: "4 sınıf için örnek bbox+confidence çıktısı; rectangle_scan_enabled=False
iken dikdörtgen sınıflarının filtrelendiği gösterilir."

Dürüstlük notu (Article 10 ruhu — sonuç fabrike edilmez): repoda KURSAD40'ın
4 sınıfıyla (MAVI_ALTIGEN/KIRMIZI_UCGEN/KIRMIZI_DIKDORTGEN/MAVI_DIKDORTGEN)
eğitilmiş bir YOLO modeli YOK -- yalnızca stok COCO-eğitimli `yolov8n.pt`
var (bkz. core/detection/yolo_detector.py:12-19 FOOTGUN GUARD). Bu dosya bu
yüzden YOLO için GERÇEK pozitif tespit iddia ETMEZ; onun yerine:

  1. YoloDetector'ın kablolamasının (model yükleme, gerçek inference çağrısı,
     FOOTGUN GUARD, allowlist filtresi) doğru ve GÜVENLİ çalıştığını -- stok
     modelle hiçbir zaman yanlış-pozitif üretmediğini -- kanıtlar.
  2. Gerçek bir eğitilmiş model bir gün geldiğinde çıktısının doğru
     ayrıştırılacağını, allowlist'ten geçmiş SENTETİK bir ultralytics
     sonucuyla (mock) kanıtlar -- bu bir tahmin değil, kodun kendi ayrıştırma
     mantığının testidir.
  3. "4 sınıf için örnek bbox+confidence çıktısı" DoD'sini, şu an GERÇEKTEN
     ÇALIŞAN detector (HSVContourDetector, 3 entrypoint'te de aktif) ile,
     mevcut test_hsv_contour_detector.py'nin sentetik-görüntü desenini
     genişleterek karşılar -- 4 sınıfın hepsi için gerçek bbox+confidence
     üretir.
  4. rectangle_scan_enabled=False iken dikdörtgen sınıflarının filtrelendiğini
     MissionV3State.filter_candidates() ile (F0'da eklendi) doğrudan gösterir.
"""
from pathlib import Path

import cv2
import numpy as np
import pytest

from core.detection.hsv_contour_detector import HSVContourDetector
from core.detection.types import Detection
from core.detection.yolo_detector import YoloDetector, _ALLOWED_CLASSES
from core.config.parameters import HSV_STREAK_FRAMES
from core.mission.interlock import PayloadInterlock
from core.mission.mission_v3_state import MissionV3State

STOCK_YOLO_WEIGHTS = Path(__file__).resolve().parents[2] / "yolov8n.pt"


# ---------------------------------------------------------------- 1. YOLO kablolaması

@pytest.mark.skipif(not STOCK_YOLO_WEIGHTS.is_file(), reason="yolov8n.pt bu makinede yok")
@pytest.mark.asyncio
async def test_yolo_wiring_loads_and_runs_without_crashing(caplog):
    """Gerçek model yükleme + gerçek inference çağrısı. Stok COCO modeli
    hiçbir KURSAD40 sınıfı bilmediği için sonuç boş liste OLMALI -- bu bir
    hata değil, allowlist filtresinin doğru çalıştığının kanıtı (aşağıya
    bkz: test_footgun_guard_warns_on_class_mismatch)."""
    detector = YoloDetector(str(STOCK_YOLO_WEIGHTS))
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    detections = await detector.detect(frame)

    assert detections == []  # stok model KURSAD40 sınıflarını hiç bilmiyor


@pytest.mark.skipif(not STOCK_YOLO_WEIGHTS.is_file(), reason="yolov8n.pt bu makinede yok")
def test_footgun_guard_warns_on_class_mismatch(caplog):
    """core/detection/yolo_detector.py:47-64 -- stok modelin sınıfları
    _ALLOWED_CLASSES ile hiç kesişmiyorsa yüksek sesle uyarmalı, sessizce
    'çalışıyormuş gibi' davranmamalı."""
    with caplog.at_level("WARNING"):
        YoloDetector(str(STOCK_YOLO_WEIGHTS))

    assert any("ORTUSMUYOR" in r.message for r in caplog.records)


def test_stock_model_classes_do_not_overlap_kursad40_classes():
    """Bu iddiayı çalışma zamanında (varsayımla değil) doğrula: stok
    yolov8n.pt'nin COCO sınıfları gerçekten 4 KURSAD40 sınıfıyla kesişmiyor
    mu? Kesişseydi FOOTGUN GUARD hiç tetiklenmezdi."""
    if not STOCK_YOLO_WEIGHTS.is_file():
        pytest.skip("yolov8n.pt bu makinede yok")
    from ultralytics import YOLO
    model = YOLO(str(STOCK_YOLO_WEIGHTS))
    model_classes = set(model.names.values())
    assert not (model_classes & _ALLOWED_CLASSES)


# ------------------------------------------------- 2. Ayrıştırma mantığı (mock)

class _FakeBox:
    def __init__(self, conf, cls_id, xyxy):
        import torch
        self.conf = torch.tensor([conf])
        self.cls = torch.tensor([cls_id])
        self.xyxy = torch.tensor([xyxy])


class _FakeBoxes(list):
    pass


class _FakeResult:
    def __init__(self, boxes, names):
        self.boxes = boxes
        self.names = names


@pytest.mark.asyncio
async def test_detection_parsing_when_a_real_trained_model_exists(monkeypatch):
    """Gerçek bir eğitilmiş model henüz yok -- ama VAR OLSAYDI, YoloDetector
    onun çıktısını doğru ayrıştırır mı? SENTETİK bir ultralytics sonucuyla
    (gerçek tespit iddiası YOK, sadece ayrıştırma kodunun testi) kanıtla."""
    detector = YoloDetector.__new__(YoloDetector)  # _load_model'i atla (gerçek dosya gerekmesin)
    detector.confidence_threshold = 0.70
    detector.model_path = "hypothetical_trained_model.pt"

    names = {0: "MAVI_ALTIGEN", 1: "KIRMIZI_UCGEN", 2: "KIRMIZI_DIKDORTGEN", 3: "person"}
    fake_result = _FakeResult(
        boxes=_FakeBoxes([
            _FakeBox(conf=0.91, cls_id=0, xyxy=(10.0, 20.0, 110.0, 120.0)),   # MAVI_ALTIGEN, kabul
            _FakeBox(conf=0.55, cls_id=1, xyxy=(0.0, 0.0, 10.0, 10.0)),        # eşik altı, RED
            _FakeBox(conf=0.99, cls_id=3, xyxy=(0.0, 0.0, 50.0, 50.0)),        # allowlist dışı, RED
        ]),
        names=names,
    )
    detector._model = lambda frame, verbose: [fake_result]

    detections = await detector.detect(np.zeros((10, 10, 3), dtype=np.uint8))

    assert len(detections) == 1
    d = detections[0]
    assert d.shape_type == "MAVI_ALTIGEN"
    assert d.confidence == pytest.approx(0.91)
    assert d.bbox_px == (10.0, 20.0, 110.0, 120.0)
    assert d.center_px == (60.0, 70.0)


# ------------------------------------------- 3. Gerçek çalışan detector: HSV, 4 sınıf

def _frame_with_all_four_shapes() -> np.ndarray:
    """test_hsv_contour_detector.py::_frame_with_shapes deseninin 4 sınıfa
    genişletilmiş hali -- ayrı kadranlarda üçgen, altıgen ve iki dikdörtgen."""
    frame = np.zeros((800, 800, 3), dtype=np.uint8)

    tri_pts = np.array([[120, 80], [40, 240], [200, 240]], dtype=np.int32)
    cv2.fillPoly(frame, [tri_pts], (0, 0, 255))  # kırmızı üçgen

    center = (600, 150)
    radius = 90
    hex_pts = np.array(
        [(int(center[0] + radius * np.cos(np.pi / 3 * i)),
          int(center[1] + radius * np.sin(np.pi / 3 * i))) for i in range(6)],
        dtype=np.int32,
    )
    cv2.fillPoly(frame, [hex_pts], (255, 0, 0))  # mavi altıgen

    red_rect = cv2.boxPoints(((180, 620), (160, 70), 20.0)).astype(np.int32)
    cv2.fillPoly(frame, [red_rect], (0, 0, 255))  # kırmızı dikdörtgen

    blue_rect = cv2.boxPoints(((620, 620), (160, 70), -15.0)).astype(np.int32)
    cv2.fillPoly(frame, [blue_rect], (255, 0, 0))  # mavi dikdörtgen

    return frame


@pytest.mark.asyncio
async def test_hsv_detector_produces_real_bbox_confidence_for_all_four_classes():
    """DoD: 4 sınıf için örnek bbox+confidence çıktısı -- YOLO'da eğitilmiş
    model olmadığı için, şu an GERÇEKTEN uçan detector (HSV) ile."""
    detector = HSVContourDetector()
    frame = _frame_with_all_four_shapes()

    detections = []
    for _ in range(max(HSV_STREAK_FRAMES, 3)):
        detections = await detector.detect(frame)

    shape_types = {d.shape_type for d in detections}
    assert shape_types == {"MAVI_ALTIGEN", "KIRMIZI_UCGEN", "KIRMIZI_DIKDORTGEN", "MAVI_DIKDORTGEN"}
    for d in detections:
        assert 0.0 <= d.confidence <= 1.0
        assert len(d.bbox_px) == 4


# ------------------------------------------------- 4. rectangle_scan_enabled gating

def _synthetic_detections() -> list[Detection]:
    return [
        Detection(shape_type="MAVI_ALTIGEN", confidence=0.9, center_px=(1, 1), bbox_px=(0, 0, 2, 2)),
        Detection(shape_type="KIRMIZI_UCGEN", confidence=0.9, center_px=(1, 1), bbox_px=(0, 0, 2, 2)),
        Detection(shape_type="KIRMIZI_DIKDORTGEN", confidence=0.9, center_px=(1, 1), bbox_px=(0, 0, 2, 2)),
        Detection(shape_type="MAVI_DIKDORTGEN", confidence=0.9, center_px=(1, 1), bbox_px=(0, 0, 2, 2)),
    ]


def test_rectangle_classes_filtered_while_scan_disabled():
    state = MissionV3State(PayloadInterlock())
    assert state.rectangle_scan_enabled is False

    filtered = state.filter_candidates(_synthetic_detections())

    assert {d.shape_type for d in filtered} == {"MAVI_ALTIGEN", "KIRMIZI_UCGEN"}


def test_rectangle_classes_allowed_once_both_payloads_done():
    state = MissionV3State(PayloadInterlock())
    state.mark_hexagon_done()
    state.mark_triangle_done()
    assert state.rectangle_scan_enabled is True

    filtered = state.filter_candidates(_synthetic_detections())

    assert {d.shape_type for d in filtered} == {
        "MAVI_ALTIGEN", "KIRMIZI_UCGEN", "KIRMIZI_DIKDORTGEN", "MAVI_DIKDORTGEN",
    }
