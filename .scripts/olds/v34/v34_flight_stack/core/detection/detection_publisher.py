"""Tespit sonuclarinin process DISINA, salt-izleme amacli ZMQ yayini.

NEDEN VAR
---------
FrameChannel (core/telemetry/frame_channel.py) kareyi tespitlerle BIRLIKTE
tasir, ama yalnizca mission process'inin ICINDE: MissionOpsDashboard ile
VisionRuntime ayni nesne grafigini paylasir. camera_service.py'nin
tcp://127.0.0.1:5555 yayini ise tam tersi -- process disina cikar ama HAM
JPEG'dir, tespit tasimaz. Sonuc olarak disaridan baglanan bir izleyici
(tools/mission_dashboard_v2.py) kareyi gorebiliyor, uzerindeki kutulari
goremiyordu.

Bu modul o boslugu kapatir: tespit listesi -- kare DEGIL -- kucuk bir JSON
olarak AYRI bir PUB soketinden (varsayilan tcp://127.0.0.1:5556) yayinlanir.
Izleyici kareyi 5555'ten, uzerine cizecegi geometriyi buradan alir.

TASARIM KISITI: MISSION'I ASLA ETKILEYEMEZ
------------------------------------------
Bu yayin tamamen OPSIYONELDIR ve mission'in dogru calismasi icin GEREKSIZ.
Bunu kod duzeyinde garanti eden dort ozellik:

  1. NOBLOCK gonderim + SNDHWM=2 -- abone yoksa ya da yavassa mesaj sessizce
     DUSER; ZMQ PUB soketi zaten abonesizken gonderileni atar. Cagiran hicbir
     kosulda beklemez.
  2. Her cagri try/except ile sarili -- serilestirme hatasi, kapali soket,
     ZMQ ic hatasi... hicbiri _detection_loop'a sizamaz.
  3. bind() basarisiz olursa (port dolu, zmq kurulu degil) nesne sessizce
     DEVRE DISI kalir; publish() cagrilari no-op olur.
  4. LINGER=0 -- kapanista bekleyen mesaj mission'in cikisini geciktiremez.

Bu, camera_service.py:204-205'in (PUB + SNDHWM=2, "drop old frames if not
consumed fast enough") ayni sozlesmesidir; burada kare yerine geometri
tasindigi icin yuk birkac yuz bayttir.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_DETECTION_ZMQ = "tcp://127.0.0.1:5556"

try:
    import zmq
    _ZMQ_AVAILABLE = True
except Exception:  # noqa: BLE001 -- pyzmq yoksa yayin tamamen kapanir, mission calisir
    _ZMQ_AVAILABLE = False


class NullDetectionPublisher:
    """Varsayilan. Hicbir sey yapmaz -- VisionRuntime'in yayin kapaliyken
    `if self._pub is not None` gibi dallanmalar tasimasini engeller."""

    enabled = False

    def publish(self, detections, frame, seq: int, ts: float) -> None:
        pass

    def close(self) -> None:
        pass


class DetectionZmqPublisher:
    """Tespit geometrisini JSON olarak PUB eden, hata yutan yayinci."""

    def __init__(self, addr: str = DEFAULT_DETECTION_ZMQ):
        self.addr = addr
        self.enabled = False
        self.sent = 0
        self._dropped = 0
        self._ctx = None
        self._sock = None
        if not _ZMQ_AVAILABLE:
            logger.info("[DETECTION_PUB] pyzmq yok -- tespit yayini devre disi.")
            return
        try:
            self._ctx = zmq.Context.instance()
            self._sock = self._ctx.socket(zmq.PUB)
            self._sock.setsockopt(zmq.SNDHWM, 2)     # camera_service.py:205 ile ayni
            self._sock.setsockopt(zmq.LINGER, 0)     # kapanisi geciktirme
            self._sock.bind(self.addr)
            self.enabled = True
            logger.info("[DETECTION_PUB] tespit yayini acik: %s", self.addr)
        except Exception as e:  # noqa: BLE001 -- yayin acilamadi, mission etkilenmez
            logger.info("[DETECTION_PUB] yayin acilamadi (%s) -- devre disi, "
                        "mission etkilenmez: %s", self.addr, e)
            self._safe_close()

    # ------------------------------------------------------------------
    @staticmethod
    def _detection_to_dict(d) -> dict:
        """core/detection/types.py:Detection -> JSON'a uygun sozluk.

        contour_px approxPolyDP ciktisi oldugu icin tipik olarak 3-8 nokta;
        1 ondalik yeterli (cizim zaten int'e yuvarlıyor) ve yuk kucuk kalir."""
        contour = getattr(d, "contour_px", None)
        return {
            "shape_type": d.shape_type,
            "confidence": round(float(d.confidence), 4),
            "center_px": [round(float(d.center_px[0]), 1), round(float(d.center_px[1]), 1)],
            "bbox_px": [round(float(v), 1) for v in d.bbox_px],
            "contour_px": ([[round(float(x), 1), round(float(y), 1)] for x, y in contour]
                           if contour else None),
            "rotation_deg": (round(float(d.rotation_deg), 2)
                             if getattr(d, "rotation_deg", None) is not None else None),
        }

    def publish(self, detections, frame, seq: int, ts: float) -> None:
        """Tek bir detect() sonucunu yayinlar. ASLA yukselmez, ASLA bloklamaz."""
        if not self.enabled:
            return
        try:
            h, w = (frame.shape[0], frame.shape[1]) if frame is not None else (0, 0)
            payload = {
                "ts": ts,
                "seq": seq,
                "frame_w": int(w),
                "frame_h": int(h),
                "detections": [self._detection_to_dict(d) for d in detections],
            }
            self._sock.send_string(json.dumps(payload), flags=zmq.NOBLOCK)
            self.sent += 1
        except Exception:  # noqa: BLE001 -- izleyici yayini mission'i asla etkilemez
            self._dropped += 1
            if self._dropped in (1, 100, 1000):
                logger.debug("[DETECTION_PUB] gonderim atlandi (toplam %d) -- "
                             "mission etkilenmez.", self._dropped)

    # ------------------------------------------------------------------
    def _safe_close(self) -> None:
        self.enabled = False
        try:
            if self._sock is not None:
                self._sock.close(linger=0)
        except Exception:  # noqa: BLE001
            pass
        self._sock = None
        # Context.instance() paylasimlidir -- term() EDILMEZ, baska
        # kullanicilarin soketlerini oldururdu.

    def close(self) -> None:
        if self.enabled:
            logger.info("[DETECTION_PUB] yayin kapatiliyor (gonderilen=%d, atlanan=%d).",
                        self.sent, self._dropped)
        self._safe_close()


def build_detection_publisher():
    """VisionRuntime'in varsayilan fabrikasi.

    KURSAD40_DETECTION_PUB=0 ile tamamen kapatilabilir; adres
    KURSAD40_DETECTION_ZMQ ile degistirilebilir. Hicbir kosulda yukselmez --
    en kotu durumda NullDetectionPublisher doner."""
    if os.environ.get("KURSAD40_DETECTION_PUB", "1").strip() in ("0", "false", "False", "no"):
        return NullDetectionPublisher()
    try:
        pub = DetectionZmqPublisher(os.environ.get("KURSAD40_DETECTION_ZMQ", DEFAULT_DETECTION_ZMQ))
        return pub if pub.enabled else NullDetectionPublisher()
    except Exception:  # noqa: BLE001 -- fabrika bile patlarsa mission yine calisir
        return NullDetectionPublisher()
