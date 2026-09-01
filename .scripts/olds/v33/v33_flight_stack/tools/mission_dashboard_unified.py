"""KURSAD40 Mission Dashboard UNIFIED -- tek pencere, uc kolon, tam ekran.

tools/mission_dashboard_v2.py'nin uzerine insa edilmistir; o dosya OLDUGU
GIBI durur ve calismaya devam eder. Buradaki fark uc baslikta toplanir:

  1. TESPIT OVERLAY'I. v2 ham JPEG gosteriyordu, cunku tespitler yalnizca
     mission process'inin ICINDE (FrameChannel) mevcuttu. Artik
     core/detection/detection_publisher.py tespit GEOMETRISINI ayri bir ZMQ
     PUB soketinden (tcp://127.0.0.1:5556) disariya yayinliyor; bu izleyici
     kareyi 5555'ten, uzerine cizecegini 5556'dan alir ve
     core/telemetry/dashboard.py'nin kontur/lock/mesafe cizimini AYNEN
     uygular.
  2. ONBOARD/OFFBOARD ROZETI. dashboard.py:402-421'in rozeti, kamera
     panelinin sag ust kosesine sabitlenmis halde.
  3. EVENT TIMELINE. dashboard.py:571-581'in paneli ucuncu kolon olarak,
     JSONL uzerinden ve GURULTU FILTRESI ile.

MIMARI DEGISMEDI: bu hala tamamen ayri, SALT-OKUNUR bir process'tir. Mission
runtime'ina tek bir cagri yapmaz, hicbir dosyaya yazmaz, camera_service'i
baslatmaz -- yalnizca uc yayina/dosyaya disaridan abone olur. Coktugunde
mission etkilenmez; mission bittiginde acik kalir.

NEDEN 5556 AYRI BIR SOKET
-------------------------
Kamera yayinina (5555) DOKUNULMADI. O soket JPEG tasiyor ve camera_service
tarafindan bind ediliyor; icine tespit gomek hem formati bozar hem de o
servisi tespit boru hattina bagimli hale getirirdi. Ayri soket, ayri
yasam dongusu: 5556 hic yayin yapmasa da (mission kapali, tespit yok, port
dolu) bu ekran ham kareyi gostermeye devam eder -- overlay sessizce yok
olur, hicbir sey cokmez.

GURULTU FILTRESI -- OLCULDU, VARSAYILANI ACIK
---------------------------------------------
Ham timeline pratikte okunamaz. mission_66435794241a (5626 olay, 364 s)
uzerinde uc secenek olculdu:

    ham                          5626 olay
    A) 3 kod haric (rapordaki)   1347 olay -> ring'in 48/80'i
                                 LOW_ALT_OPEN_LOOP_STEP; yalnizca son 132 s
    B) severity != DEBUG          184 olay -> ring son 223 s'yi kapsiyor
    C) A + B                      184 olay -> B ile AYNI

A tek basina yetmiyor: eleme listesindeki uc kod DEBUG seviyesindeki tek
gurultu kaynagi degil (LOW_ALT_OPEN_LOOP_STEP ve CENTERING_STEP de 10 Hz
akiyor ve listede yok). C, B ile ayni sonucu verir -- cunku uc kod zaten
DEBUG'dur -- ama ileride INFO seviyesinde gurultulu bir kod eklenirse onu da
yakalar. Bu yuzden varsayilan C'dir. TIMELINE_FILTER_NOISE = False ile ham
akisa donulur.
"""
import glob
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import zmq

# core/ modulleri AYNEN kullanilir (kopyalanmaz) -- ucu de saf, bagimliliksiz:
# geo.py duz matematik, parameters.py hicbir sey import etmiyor,
# camera_intrinsics.py yalnizca stdlib + SDF okuyor (cwd'den bagimsiz,
# __file__'dan yukari yuruyor).
_STACK_ROOT = Path(__file__).resolve().parent.parent
if str(_STACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_STACK_ROOT))
from core.config.parameters import (CENTERING_TOLERANCE_X_NORM,  # noqa: E402
                                    CENTERING_TOLERANCE_Y_NORM,
                                    DETECTION_STALE_AFTER_S,
                                    RELEASED_OVERLAY_DURATION_S)
from core.detection.camera_intrinsics import default_camera_intrinsics  # noqa: E402
from core.navigation.geo import gps_to_ned_delta  # noqa: E402

# --------------------------------------------------------------------------
# Yapilandirma
# --------------------------------------------------------------------------
DEFAULT_LOG_DIR = str(_STACK_ROOT.parent / "logs")
DEFAULT_ZMQ = "tcp://127.0.0.1:5555"
DEFAULT_DETECTION_ZMQ = "tcp://127.0.0.1:5556"

WINDOW = "KURSAD40 - Mission Dashboard (unified)"

# Ekran cozunurlugu bulunamazsa kullanilacak deger (bu makinede olculen
# mantiksal masaustu boyutu: 2560x1664 Retina -> 1710x1112 nokta).
FALLBACK_SCREEN = (1710, 1112)

COL_W = 470                      # orta kolon -- v2 ile ayni, panel davranisi degismesin
TIMELINE_W = 330                 # ucuncu kolon; en uzun timeline satiri olculdu:
                                 # scale 0.43'te 292 px + 14 px sol bosluk = 306
STATUS_H = 424                   # 11 adim x 27 px + baslik/alt satir icin olculen yukseklik
MIN_CAM_W = 560
MIN_MAP_H = 240

JSONL_POLL_S = 0.15
POSITIONS_POLL_S = 1.0
MISSION_SCAN_S = 2.0
CAMERA_STALE_S = 2.0
RENDER_HZ = 15.0

TRAIL_MAX = 600
TRAIL_MIN_STEP_M = 0.25

# -- EVENT TIMELINE ---------------------------------------------------------
RECENT_EVENTS_MAX = 80           # aggregator.py:23 ile ayni
TIMELINE_FILTER_NOISE = True     # False -> ham akis (filtre yok)
TIMELINE_DROP_SEVERITIES = frozenset({"DEBUG"})
TIMELINE_DROP_CODES = frozenset({
    "VISION_FRAME_PROCESSED", "VEHICLE_TELEMETRY", "WATCHDOG_UPDATED",
})
TIMELINE_SCALE = 0.43            # dashboard.py 0.36 idi; orada DISPLAY_SCALE=1.2
TIMELINE_LINE_H = 18             # vardi, burada 1:1 cizildigi icin buyutuldu

# Palet -- core/telemetry/dashboard.py:56-79 ile ayni aile (BGR).
COL_BG = (22, 22, 24)
COL_PANEL_BG = (34, 34, 38)
COL_PANEL_BORDER = (58, 58, 64)
COL_HEADER_BG = (48, 48, 54)
COL_ACCENT = (235, 178, 60)
COL_TEXT = (232, 232, 232)
COL_TEXT_DIM = (150, 150, 156)
COL_GOOD = (110, 220, 120)
COL_WARN = (60, 210, 235)
COL_BAD = (70, 70, 235)
COL_GRID = (52, 52, 58)
COL_TRAIL = (150, 150, 90)
COL_VEHICLE = (235, 235, 235)
COL_HEX = (255, 120, 0)          # MAVI_ALTIGEN
COL_TRI = (0, 0, 255)            # KIRMIZI_UCGEN
# Overlay renkleri -- dashboard.py:72-78 ile birebir.
COL_VECTOR = (0, 255, 255)
COL_LOCKED = (0, 0, 0)
COL_CONTOUR = (0, 255, 0)

# dashboard.py:95-101'in AYNISI, ama string anahtarlarla: JSONL zaten
# Severity.X.value ("DEBUG", "INFO", ...) yaziyor, o yuzden enum import
# edilmez (bu process mission runtime'indan bagimsiz kalir).
SEVERITY_COLOR = {
    "DEBUG": COL_TEXT_DIM,
    "INFO": COL_TEXT,
    "WARN": COL_WARN,
    "CRITICAL": COL_BAD,
    "FATAL": COL_BAD,
}

FONT = cv2.FONT_HERSHEY_SIMPLEX

TERMINAL_OK = "MISSION_COMPLETE"
TERMINAL_BAD = ("MISSION_FAILED", "MISSION_ABORTED", "MISSION_TIMEOUT")


# --------------------------------------------------------------------------
# Yerlesim -- gercek ekran boyutundan turetilir
# --------------------------------------------------------------------------
def detect_screen_size():
    """(genislik, yukseklik) MANTIKSAL nokta olarak.

    Sirasiyla: KURSAD40_DASH_SIZE ortam degiskeni ("1710x1112"), macOS'ta
    Finder'in masaustu penceresi (Retina olceklemesini zaten cozulmus nokta
    cinsinden verir; cv2 pencereleri de nokta biriminde konumlanir), sonra
    sabit yedek. Hicbir kosulda yukselmez -- ekran sorgusu bir izleyiciyi
    baslatmaktan alikoyamaz."""
    env = os.environ.get("KURSAD40_DASH_SIZE", "").strip().lower()
    if "x" in env:
        try:
            w, h = env.split("x", 1)
            return max(900, int(w)), max(600, int(h))
        except ValueError:
            pass
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["osascript", "-e",
                 'tell application "Finder" to get bounds of window of desktop'],
                capture_output=True, text=True, timeout=4.0)
            parts = [int(p.strip()) for p in out.stdout.strip().split(",")]
            if len(parts) == 4 and parts[2] > 900 and parts[3] > 600:
                return parts[2], parts[3]
        except Exception:  # noqa: BLE001 -- osascript yoksa/yavassa yedege dus
            pass
    return FALLBACK_SCREEN


class Layout:
    """Tek yerde hesaplanan piksel yerlesimi.

    Kamera 4:3 (1280x960), ekran ~1.54:1 -- yani kamera tam yukseklige
    cekilirse geriye kalan iki kolona yer kalmaz. Bu yuzden kamera KENDI
    panelinin icinde mektup-kutulanir (v2'nin draw_camera'si zaten bunu
    yapiyordu) ve olusan ust/alt bantlar bos birakilmaz: rozet ve kamera
    durum seridi oraya yerlesir."""

    def __init__(self, screen_w: int, screen_h: int):
        self.W, self.H = screen_w, screen_h
        tl = TIMELINE_W
        col = COL_W
        cam = self.W - col - tl
        if cam < MIN_CAM_W:                      # dar ekran: iki kolonu kis
            over = MIN_CAM_W - cam
            take_tl = min(over, tl - 260)
            tl -= take_tl
            col -= (over - take_tl)
            cam = self.W - col - tl
        self.cam_w, self.cam_h = cam, self.H
        self.col_x, self.col_w = cam, col
        self.tl_x, self.tl_w = cam + col, tl
        self.status_h = min(STATUS_H, max(200, self.H - MIN_MAP_H))
        self.map_h = self.H - self.status_h

    def describe(self) -> str:
        return (f"{self.W}x{self.H}  |  kamera {self.cam_w}x{self.cam_h}  "
                f"map/status {self.col_w} ({self.map_h}/{self.status_h})  "
                f"timeline {self.tl_w}")


# --------------------------------------------------------------------------
# Kamera -- gz_system/camera_client.py'nin salt-okunur ikizi (v2 ile ayni)
# --------------------------------------------------------------------------
class CameraSubscriber:
    """camera_client.CameraClient ile AYNI soket ayarlari ve AYNI bayatlik
    sozlesmesi (RCVHWM=2, CONFLATE=1, SUBSCRIBE=b"", 2 s -> reconnect).
    camera_service'i BASLATMAZ; yalnizca mevcut yayina abone olur."""

    def __init__(self, zmq_addr: str):
        self.zmq_addr = zmq_addr
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.context = zmq.Context()
        self.socket = self._new_socket()
        self.running = False
        self.thread = None
        self.last_receive_time = time.time()
        self.reconnect_requested = False
        self.frames_received = 0

    def _new_socket(self):
        s = self.context.socket(zmq.SUB)
        s.setsockopt(zmq.RCVHWM, 2)
        s.setsockopt(zmq.SUBSCRIBE, b"")
        try:
            s.setsockopt(zmq.CONFLATE, 1)
        except AttributeError:
            pass
        return s

    def start(self):
        self.running = True
        self.last_receive_time = time.time()
        self.thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.thread.start()

    def _receive_loop(self):
        try:
            self.socket.connect(self.zmq_addr)
        except Exception as e:  # noqa: BLE001
            print(f"[DASHBOARD] ZMQ connect failed: {e}")
            self.running = False
            return

        while self.running:
            if self.reconnect_requested:
                try:
                    self.socket.close()
                    self.socket = self._new_socket()
                    self.socket.connect(self.zmq_addr)
                    self.reconnect_requested = False
                    self.last_receive_time = time.time()
                except Exception:  # noqa: BLE001
                    time.sleep(1.0)
                    continue
            try:
                if self.socket.poll(100):
                    raw = self.socket.recv()
                    arr = np.frombuffer(raw, np.uint8)
                    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        with self.frame_lock:
                            self.latest_frame = frame
                            self.last_receive_time = time.time()
                            self.frames_received += 1
            except Exception:  # noqa: BLE001
                time.sleep(0.1)

    def get_frame(self):
        with self.frame_lock:
            if time.time() - self.last_receive_time > CAMERA_STALE_S:
                if not self.reconnect_requested:
                    self.reconnect_requested = True
                self.latest_frame = None
                return None
            return None if self.latest_frame is None else self.latest_frame.copy()

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        try:
            self.socket.close()
            self.context.term()
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# Tespit yayini -- YENI (core/detection/detection_publisher.py'nin karsiligi)
# --------------------------------------------------------------------------
class DetectionSubscriber:
    """5556'daki tespit geometrisine abone. Kamera abonesiyle AYNI desen
    (RCVHWM=2, CONFLATE=1, SUBSCRIBE=b"") -- tek fark, JPEG yerine JSON.

    Yayin hic gelmiyorsa (mission kapali, tespit publisher devre disi, port
    bos) `get()` None doner ve kamera paneli ham kareyi cizer. Bu bir hata
    degil, beklenen bir durumdur: overlay opsiyoneldir."""

    def __init__(self, zmq_addr: str):
        self.zmq_addr = zmq_addr
        self.lock = threading.Lock()
        self.payload = None
        self.payload_at = 0.0
        self.messages = 0
        self.context = zmq.Context.instance()
        self.socket = None
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        try:
            s = self.context.socket(zmq.SUB)
            s.setsockopt(zmq.RCVHWM, 2)
            s.setsockopt(zmq.SUBSCRIBE, b"")
            try:
                s.setsockopt(zmq.CONFLATE, 1)
            except AttributeError:
                pass
            s.connect(self.zmq_addr)
            self.socket = s
        except Exception as e:  # noqa: BLE001 -- overlay opsiyonel, izleyici yasar
            print(f"[DASHBOARD] tespit yayinina baglanilamadi ({self.zmq_addr}): {e}")
            self.running = False
            return

        while self.running:
            try:
                if self.socket.poll(100):
                    msg = self.socket.recv_string()
                    data = json.loads(msg)
                    with self.lock:
                        self.payload = data
                        self.payload_at = time.time()
                        self.messages += 1
            except Exception:  # noqa: BLE001 -- bozuk mesaj izleyiciyi oldurmez
                time.sleep(0.1)

    def get(self):
        """(payload, yas_saniye) ya da hic mesaj gelmediyse (None, None)."""
        with self.lock:
            if self.payload is None:
                return None, None
            return self.payload, time.time() - self.payload_at

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        try:
            if self.socket is not None:
                self.socket.close(linger=0)
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# JSONL tail (v2 ile ayni)
# --------------------------------------------------------------------------
class JsonlTail:
    """`tail -f` esdegeri, ama BASTAN baslar: dashboard gorev basladiktan
    sonra acilsa bile CHECKPOINT_SAVED / MISSION_START gibi gecmis olaylari
    kacirmaz. Yarim yazilmis son satir tamponda bekletilir."""

    def __init__(self, path: str):
        self.path = path
        self._fh = None
        self._buf = ""
        self.broken_lines = 0

    def _ensure_open(self) -> bool:
        if self._fh is not None:
            return True
        try:
            self._fh = open(self.path, "r", encoding="utf-8", errors="replace")
            return True
        except OSError:
            return False

    def poll(self):
        out = []
        if not self._ensure_open():
            return out
        try:
            chunk = self._fh.read()
        except OSError:
            return out
        if not chunk:
            return out
        self._buf += chunk
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                self.broken_lines += 1
        return out

    def close(self):
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None


# --------------------------------------------------------------------------
# Adim tanimlari (Panel 2)
# --------------------------------------------------------------------------
STEPS = [
    ("start / finish point", "onboard"),
    ("mission start", "onboard"),
    ("1st payload point", "offboard"),
    ("1st payload", "offboard"),
    ("mission continue", "onboard"),
    ("2nd payload point", "offboard"),
    ("2nd payload", "offboard"),
    ("grapple", "offboard"),
    ("3rd payload", "offboard"),
    ("go to start/finish", "offboard"),
    ("landing", "offboard"),
]

PENDING, ACTIVE, DONE, FAILED = 0, 1, 2, 3


class MissionState:
    """JSONL event akisini ekranin ihtiyac duydugu duruma katlar.

    v2'nin MissionState'i + uc ek: EVENT RING (timeline paneli icin),
    CENTERING durumu (lock gostergesi ve `d=` etiketi icin) ve PAYLOAD
    birakma damgasi (RELEASED etiketi icin). Ucu de aggregator.py'nin ayni
    event'lerden turettigi degerlerin salt-okunur karsiligidir."""

    def __init__(self):
        self.mission_id = ""
        self.first_ts = None
        self.last_ts = None
        self.phase = "-"
        self.checkpoint = None
        self.vehicle_gps = None
        self.flight_mode = "UNKNOWN"
        self.connected = False
        self.trail = []
        self.event_count = 0
        self._first_vehicle = None

        # adim tetikleyicileri
        self.checkpoint_saved = False
        self.mission_start_seen = False
        self.gps_save_count = 0
        self.payload1_complete = False
        self.payload2_complete = False
        self.mission_continue_seen = False
        self.g3_pickup = False
        self.g3_transport = False
        self.g3_redrop = False
        self.g3_complete = False
        # GOREV3_PHASE_FAILED: bir Gorev 3 fazi ULASILDI ama BASARISIZ bitti.
        # Bu ayrim olmadan pickup'ta olen bir kosuda "grapple" yesil gorunur.
        self.g3_failed = set()
        self.return_seen = False
        self.landing_seen = False
        self.terminal = None

        # -- EVENT TIMELINE ring'i (aggregator.py:41-46 deseni) ------------
        # IKI ring tutulur: filtrelenmis ve ham. Ikisi de her olayda
        # guncellendigi icin 'f' tusuyla gecis ANINDA olur ve gecmis
        # kaybolmaz -- aksi halde filtre acilip kapandiginda 5626 satirlik
        # JSONL'i bastan okumak gerekirdi.
        self.events = []
        self.events_all = []
        self.events_dropped = 0

        # -- CENTERING (CENTERING_STEP, centering_controller.py:972-991) ---
        # dashboard.py overlay'i bunlari snap.centering'den okuyordu.
        self.c_shape = ""
        self.c_converged = False
        self.c_ground_distance_m = None
        self.c_center_px = None
        self.c_updated_at = None

        # -- PAYLOAD birakma (PAYLOAD_STATE, aggregator.py:185-190) --------
        self.p_released_at = None
        self.p_released_shape = ""

    # -- event folding ----------------------------------------------------
    def _ring_push(self, e: dict) -> None:
        """Filtreden gecen olayi ring'e koy. aggregator.py'nin AYNI deseni
        (append + tasinca pop(0)), tek fark: orada filtre YOKTU, cunku ring
        ayni zamanda replay/tani icin tam gecmis tutuyordu. Burada ring
        yalnizca ekranı besliyor; tam gecmis zaten JSONL dosyasinin
        kendisidir, hicbir sey kaybolmaz."""
        self.events_all.append(e)
        if len(self.events_all) > RECENT_EVENTS_MAX:
            self.events_all.pop(0)

        if (e.get("severity") in TIMELINE_DROP_SEVERITIES
                or e.get("code") in TIMELINE_DROP_CODES):
            self.events_dropped += 1
            return
        self.events.append(e)
        if len(self.events) > RECENT_EVENTS_MAX:
            self.events.pop(0)

    def apply(self, e: dict) -> None:
        self.event_count += 1
        ts = e.get("ts")
        if isinstance(ts, (int, float)):
            if self.first_ts is None:
                self.first_ts = ts
            self.last_ts = ts
        if not self.mission_id:
            self.mission_id = e.get("mission_id") or ""

        self._ring_push(e)

        code = e.get("code")
        data = e.get("data") or {}

        if code == "MISSION_PHASE_CHANGED":
            to_phase = data.get("to_phase")
            from_phase = data.get("from_phase")
            if to_phase:
                self.phase = to_phase
            if to_phase == "MISSION_START":
                self.mission_start_seen = True
            if from_phase == "GPS_SAVE" and to_phase == "SEARCHING":
                self.mission_continue_seen = True
            if to_phase == "RETURN_TO_CHECKPOINT":
                self.return_seen = True
            if to_phase == "LANDING":
                self.landing_seen = True
            if to_phase == TERMINAL_OK or to_phase in TERMINAL_BAD:
                self.terminal = to_phase

        elif code == "CHECKPOINT_SAVED":
            cp = data.get("checkpoint")
            if isinstance(cp, (list, tuple)) and len(cp) >= 3:
                self.checkpoint = (float(cp[0]), float(cp[1]), float(cp[2]))
                self.checkpoint_saved = True

        elif code == "VEHICLE_TELEMETRY":
            pos = data.get("position")
            if isinstance(pos, (list, tuple)) and len(pos) >= 3:
                self.vehicle_gps = (float(pos[0]), float(pos[1]), float(pos[2]))
                self._push_trail()
            self.flight_mode = data.get("flight_mode") or self.flight_mode
            self.connected = bool(data.get("connected", self.connected))

        elif code == "GPS_SAVE_CONFIRMED":
            self.gps_save_count += 1

        elif code == "PAYLOAD_MISSION_1_COMPLETE":
            self.payload1_complete = True
        elif code == "PAYLOAD_MISSION_2_COMPLETE":
            self.payload2_complete = True

        elif code == "GOREV3_PHASE_STARTED":
            ph = data.get("phase") or e.get("message") or ""
            if ph == "pickup":
                self.g3_pickup = True
            elif ph == "transport":
                self.g3_transport = True
            elif ph == "redrop":
                self.g3_redrop = True
        elif code == "GOREV3_PHASE_FAILED":
            ph = data.get("phase") or e.get("message") or ""
            if ph:
                self.g3_failed.add(ph)
        elif code == "GOREV3_COMPLETE":
            self.g3_complete = True

        elif code == "CENTERING_STEP":
            # dashboard.py:304-307'nin sozlesmesi: "locked" DENETLEYICININ
            # kendi bayragidir, ekran onu pikselden YENIDEN TURETMEZ.
            self.c_shape = data.get("shape_type") or self.c_shape
            self.c_converged = bool(data.get("converged"))
            gd = data.get("ground_distance_m")
            self.c_ground_distance_m = float(gd) if isinstance(gd, (int, float)) else None
            cp = data.get("center_px")
            if isinstance(cp, (list, tuple)) and len(cp) >= 2:
                self.c_center_px = (float(cp[0]), float(cp[1]))
            self.c_updated_at = ts

        elif code == "PAYLOAD_STATE":
            if data.get("released"):
                self.p_released_at = data.get("released_at") or ts
                self.p_released_shape = data.get("shape_type") or self.p_released_shape

    # -- turetilmis gorunumler --------------------------------------------
    def origin(self):
        if self.checkpoint is not None:
            return self.checkpoint[0], self.checkpoint[1], True
        if self._first_vehicle is not None:
            return self._first_vehicle[0], self._first_vehicle[1], False
        return None

    def _push_trail(self):
        if self._first_vehicle is None:
            self._first_vehicle = self.vehicle_gps
        o = self.origin()
        if o is None:
            return
        n, e = gps_to_ned_delta(o[0], o[1], self.vehicle_gps[0], self.vehicle_gps[1])
        p = (e, n)
        if self.trail:
            le, ln = self.trail[-1]
            if (p[0] - le) ** 2 + (p[1] - ln) ** 2 < TRAIL_MIN_STEP_M ** 2:
                return
        self.trail.append(p)
        if len(self.trail) > TRAIL_MAX:
            del self.trail[: len(self.trail) - TRAIL_MAX]

    def step_states(self, positions):
        """11 adimin durumu. Adimlar sirali oldugu icin: bir adim 'reached'
        ise ve DAHA SONRAKI bir adim da reached ise, o adim DONE sayilir."""
        orders = {p.get("detection_order") for p in positions}

        reached = [
            self.checkpoint_saved,
            self.mission_start_seen,
            self.gps_save_count >= 1 or "ilk" in orders,
            self.payload1_complete,
            self.mission_continue_seen,
            self.gps_save_count >= 2 or "ikinci" in orders,
            self.payload2_complete,
            self.g3_pickup,
            self.g3_redrop,
            self.return_seen,
            self.landing_seen,
        ]
        last_reached = max((i for i, r in enumerate(reached) if r), default=-1)

        states = []
        for i in range(len(STEPS)):
            if not reached[i]:
                states.append(PENDING)
            elif i < last_reached:
                states.append(DONE)
            else:
                states.append(ACTIVE)

        if "pickup" in self.g3_failed:
            states[7] = FAILED
        if "redrop" in self.g3_failed:
            states[8] = FAILED

        if self.terminal == TERMINAL_OK:
            for i in range(len(STEPS)):
                if states[i] == ACTIVE:
                    states[i] = DONE
        elif self.terminal in TERMINAL_BAD:
            for i in range(len(STEPS)):
                if states[i] != DONE:
                    states[i] = FAILED
        return states


# --------------------------------------------------------------------------
# Kaynak takibi
# --------------------------------------------------------------------------
def newest_mission_jsonl(log_dir: str):
    files = glob.glob(os.path.join(log_dir, "mission_*.jsonl"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def mission_id_from_path(path: str) -> str:
    return os.path.basename(path)[len("mission_"):-len(".jsonl")]


class PositionsFile:
    """mission_positions_<id>.json -- mtime degistiyse yeniden yukle."""

    def __init__(self, path: str):
        self.path = path
        self._mtime = None
        self.points = []

    def poll(self):
        try:
            m = os.path.getmtime(self.path)
        except OSError:
            self.points = []
            self._mtime = None
            return
        if m == self._mtime:
            return
        self._mtime = m
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.points = data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            pass


# --------------------------------------------------------------------------
# Cizim yardimcilari (v2 ile ayni)
# --------------------------------------------------------------------------
def text(img, s, x, y, color=COL_TEXT, scale=0.45, thick=1):
    cv2.putText(img, s, (int(x), int(y)), FONT, scale, color, thick, cv2.LINE_AA)


def panel(img, x0, y0, w, h, title, accent=COL_ACCENT):
    """DIKKAT (rapordaki (e) maddesi): dashboard.py'nin _panel'i x1'i MUTLAK
    aliyor ve govdeyi y+36'da basliyordu; bu surum genislik (w) aliyor ve
    govdeyi y0+24'te basliyor. Timeline taşinirken body_y bu farka gore
    duzeltildi."""
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), COL_PANEL_BG, -1)
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), COL_PANEL_BORDER, 1)
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + 24), COL_HEADER_BG, -1)
    cv2.line(img, (x0, y0 + 24), (x0 + w, y0 + 24), COL_PANEL_BORDER, 1)
    text(img, title, x0 + 10, y0 + 17, accent, 0.5, 1)
    return y0 + 24


def poly_icon(img, cx, cy, r, sides, color, rot_deg=0.0, filled=True, thick=2):
    pts = []
    for i in range(sides):
        a = np.deg2rad(rot_deg + i * 360.0 / sides)
        pts.append((int(round(cx + r * np.sin(a))), int(round(cy - r * np.cos(a)))))
    arr = np.array(pts, dtype=np.int32)
    if filled:
        cv2.fillPoly(img, [arr], color)
        cv2.polylines(img, [arr], True, (255, 255, 255), 1, cv2.LINE_AA)
    else:
        cv2.polylines(img, [arr], True, color, thick, cv2.LINE_AA)


def home_icon(img, cx, cy, color):
    s = 7
    cv2.rectangle(img, (cx - s, cy - 1), (cx + s, cy + s + 1), color, -1)
    roof = np.array([(cx - s - 2, cy - 1), (cx, cy - s - 3), (cx + s + 2, cy - 1)], dtype=np.int32)
    cv2.fillPoly(img, [roof], color)
    cv2.rectangle(img, (cx - s, cy - 1), (cx + s, cy + s + 1), (255, 255, 255), 1)


def nice_scale_m(span_m, px_per_m, target_px=90.0):
    if px_per_m <= 0:
        return 1.0
    raw = target_px / px_per_m
    for cand in (0.5, 1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000):
        if cand >= raw:
            return float(cand)
    return 1000.0


# --------------------------------------------------------------------------
# Kolon 2 / Panel 1 -- MAP CONTROL  (v2'den davranisi degismeden)
# --------------------------------------------------------------------------
def draw_minimap(img, x0, y0, w, h, st: MissionState, positions):
    body_y = panel(img, x0, y0, w, h, "KURSAD40 MAP CONTROL")
    ix0, iy0 = x0 + 1, body_y + 1
    iw, ih = w - 2, h - (body_y - y0) - 2

    o = st.origin()
    if o is None:
        text(img, "konum verisi bekleniyor...", ix0 + 12, iy0 + ih // 2, COL_TEXT_DIM, 0.45)
        return

    olat, olon, is_real_cp = o

    def to_ne(lat, lon):
        n, e = gps_to_ned_delta(olat, olon, lat, lon)
        return e, n

    pts = [(0.0, 0.0)]
    tgt = []
    for p in positions:
        try:
            e, n = to_ne(float(p["gps_lat"]), float(p["gps_lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        tgt.append((e, n, p.get("shape_type", ""), bool(p.get("payload_released"))))
        pts.append((e, n))
    veh = None
    if st.vehicle_gps is not None:
        veh = to_ne(st.vehicle_gps[0], st.vehicle_gps[1])
        pts.append(veh)
    pts.extend(st.trail)

    es = [p[0] for p in pts]
    ns = [p[1] for p in pts]
    min_e, max_e, min_n, max_n = min(es), max(es), min(ns), max(ns)
    span_e = max(max_e - min_e, 6.0)
    span_n = max(max_n - min_n, 6.0)
    margin = 26
    scale = min((iw - 2 * margin) / span_e, (ih - 2 * margin) / span_n)
    ce, cn = (min_e + max_e) / 2.0, (min_n + max_n) / 2.0
    cx0, cy0 = ix0 + iw / 2.0, iy0 + ih / 2.0

    def px(e, n):
        return int(round(cx0 + (e - ce) * scale)), int(round(cy0 - (n - cn) * scale))

    ox, oy = px(0.0, 0.0)
    if ix0 <= ox <= ix0 + iw:
        cv2.line(img, (ox, iy0), (ox, iy0 + ih), COL_GRID, 1)
    if iy0 <= oy <= iy0 + ih:
        cv2.line(img, (ix0, oy), (ix0 + iw, oy), COL_GRID, 1)

    if len(st.trail) > 1:
        arr = np.array([px(e, n) for e, n in st.trail], dtype=np.int32)
        cv2.polylines(img, [arr], False, COL_TRAIL, 1, cv2.LINE_AA)

    for e, n, shape, released in tgt:
        x, y = px(e, n)
        if shape == "MAVI_ALTIGEN":
            poly_icon(img, x, y, 8, 6, COL_HEX)
            lbl = "ALTIGEN"
        elif shape == "KIRMIZI_UCGEN":
            poly_icon(img, x, y, 9, 3, COL_TRI)
            lbl = "UCGEN"
        else:
            cv2.circle(img, (x, y), 6, COL_TEXT_DIM, -1)
            lbl = shape[:8]
        text(img, lbl + (" v" if released else ""), x + 11, y + 4, COL_TEXT, 0.36)

    home_icon(img, ox, oy, COL_ACCENT)
    text(img, "START/FINISH" if is_real_cp else "START (gecici)",
         ox + 12, oy + 15, COL_ACCENT if is_real_cp else COL_TEXT_DIM, 0.36)

    if veh is not None:
        vx, vy = px(*veh)
        cv2.circle(img, (vx, vy), 9, COL_VEHICLE, 1, cv2.LINE_AA)
        cv2.circle(img, (vx, vy), 4, COL_WARN, -1, cv2.LINE_AA)

    bar_m = nice_scale_m(span_e, scale)
    bar_px = int(round(bar_m * scale))
    bx, by = ix0 + 12, iy0 + ih - 12
    cv2.line(img, (bx, by), (bx + bar_px, by), COL_TEXT_DIM, 2)
    cv2.line(img, (bx, by - 4), (bx, by + 4), COL_TEXT_DIM, 2)
    cv2.line(img, (bx + bar_px, by - 4), (bx + bar_px, by + 4), COL_TEXT_DIM, 2)
    text(img, f"{bar_m:g} m", bx + bar_px + 8, by + 4, COL_TEXT_DIM, 0.38)

    nx, ny = ix0 + iw - 22, iy0 + 26
    cv2.arrowedLine(img, (nx, ny + 14), (nx, ny - 8), COL_TEXT_DIM, 1, cv2.LINE_AA, tipLength=0.4)
    text(img, "N", nx - 4, ny - 12, COL_TEXT_DIM, 0.4)

    if st.vehicle_gps is not None:
        text(img, f"alt {st.vehicle_gps[2]:+.1f} m   {st.flight_mode}",
             ix0 + 12, iy0 + 18, COL_TEXT_DIM, 0.4)


# --------------------------------------------------------------------------
# Kolon 2 / Panel 2 -- Current Status  (v2'den davranisi degismeden)
# --------------------------------------------------------------------------
def draw_status(img, x0, y0, w, h, st: MissionState, positions):
    body_y = panel(img, x0, y0, w, h, "Current Status")
    y = body_y + 8

    failed = st.terminal in TERMINAL_BAD
    hdr_col = COL_BAD if failed else (COL_GOOD if st.terminal == TERMINAL_OK else COL_TEXT)
    mid = st.mission_id or "-"
    elapsed = (st.last_ts - st.first_ts) if (st.first_ts and st.last_ts) else 0.0
    y += 14
    text(img, f"mission {mid}", x0 + 12, y, COL_TEXT_DIM, 0.42)
    text(img, f"T+{elapsed:6.1f}s", x0 + w - 92, y, COL_TEXT_DIM, 0.42)
    y += 17
    text(img, f"phase  {st.phase}", x0 + 12, y, hdr_col, 0.46)
    y += 8

    states = st.step_states(positions)
    row_h = 27
    for i, ((label, mode), state) in enumerate(zip(STEPS, states)):
        ry = y + i * row_h
        if state == DONE:
            col, mark = COL_GOOD, "x"
        elif state == ACTIVE:
            col, mark = COL_WARN, ">"
        elif state == FAILED:
            col, mark = COL_BAD, "!"
        else:
            col, mark = COL_TEXT_DIM, "."

        if state == ACTIVE:
            cv2.rectangle(img, (x0 + 6, ry + 2), (x0 + w - 6, ry + row_h - 2),
                          (44, 48, 40), -1)
            cv2.rectangle(img, (x0 + 6, ry + 2), (x0 + 9, ry + row_h - 2), COL_WARN, -1)

        cv2.circle(img, (x0 + 22, ry + 15), 7, col, 1, cv2.LINE_AA)
        text(img, mark, x0 + 19, ry + 19, col, 0.42, 1)
        text(img, f"{i + 1:2d}. {label}", x0 + 38, ry + 19, col, 0.46)
        text(img, mode, x0 + w - 74, ry + 19,
             COL_TEXT_DIM if state != ACTIVE else col, 0.38)

        if i == 7 and state == ACTIVE and st.g3_transport and not st.g3_redrop:
            text(img, "tasiniyor...", x0 + 200, ry + 19, COL_TEXT_DIM, 0.38)

    fy = y + len(STEPS) * row_h + 16
    if failed:
        cv2.rectangle(img, (x0 + 6, fy - 14), (x0 + w - 6, fy + 8), (30, 30, 60), -1)
        text(img, f"! {st.terminal}", x0 + 14, fy + 2, COL_BAD, 0.5, 1)
    elif st.terminal == TERMINAL_OK:
        text(img, "MISSION COMPLETE", x0 + 14, fy + 2, COL_GOOD, 0.5, 1)
    else:
        text(img, f"{st.event_count} olay  |  hedef {len(positions)}/2",
             x0 + 14, fy + 2, COL_TEXT_DIM, 0.4)


# --------------------------------------------------------------------------
# Kolon 1 -- KAMERA + TESPIT OVERLAY
# core/telemetry/dashboard.py:240-421'in disaridan calisan karsiligi.
# --------------------------------------------------------------------------
# lru_cache'li; SDF bir kez okunur. None donebilir (SDF bulunamazsa) --
# o zaman `d=` etiketi cizilmez, uydurma bir sayi gosterilmez.
_INTRINSICS = default_camera_intrinsics()


def _contour_points(det: dict, to_panel):
    """Tespitin poligonu, panel koordinatinda int32 (N,2). Kontur yoksa ya da
    bozuksa None -- cagiran bbox'a duser. dashboard.py:81-93 ile ayni
    sozlesme: ekran BOZULUR ama ASLA cokmez."""
    pts = det.get("contour_px")
    if not pts or len(pts) < 3:
        return None
    try:
        return np.array([to_panel(x, y) for x, y in pts], dtype=np.int32)
    except (TypeError, ValueError):
        return None


def draw_ground_distance(img, det, st: MissionState, agl_m, centre_n, target_n,
                         to_panel, fw: int, fh: int, clip):
    """`<TARGET> d=X.X m`, vektorun sag altinda (dashboard.py:357-401).

    Merkezlenen hedef icin deger CENTERING_STEP'ten AYNEN alinir -- boylece
    etiket ile log birebir ayni sayiyi soyler. Digerleri ayni intrinsics ile
    burada hesaplanir. Ne intrinsics ne de AGL varsa etiket CIZILMEZ."""
    cxn, cyn = centre_n
    txn, tyn = target_n

    distance_m = None
    if st.c_shape == det.get("shape_type") and st.c_ground_distance_m is not None:
        distance_m = st.c_ground_distance_m
    elif _INTRINSICS is not None and agl_m is not None:
        distance_m = _INTRINSICS.scaled_to(fw, fh).ground_distance_m(txn - cxn, tyn - cyn, agl_m)

    if distance_m is None:
        return

    label = f"{det.get('shape_type','?')} d={distance_m:.1f} m"
    (tw, th), _ = cv2.getTextSize(label, FONT, 0.5, 1)

    ax, ay = to_panel(max(cxn, txn), max(cyn, tyn))
    x = min(ax + 8, clip[2] - tw - 4)
    y = min(ay + th + 10, clip[3] - 4)
    x = max(x, clip[0] + 4)
    y = max(y, clip[1] + th + 4)

    # Plaka + acik metin: lock gostergesi vektoru siyaha cevirdiginde etiket
    # kendi zeminine karisamasin (dashboard.py:397-400).
    cv2.rectangle(img, (x - 4, y - th - 4), (x + tw + 4, y + 4), (0, 0, 0), -1)
    cv2.putText(img, label, (x, y), FONT, 0.5, COL_TEXT, 1, cv2.LINE_AA)


def draw_detection_overlay(img, payload: dict, st: MissionState, ox: int, oy: int,
                           s: float, disp_w: int, disp_h: int):
    """dashboard.py:262-345'in birebir tasinmis hali.

    TEK YAPISAL FARK: orada kare KENDI cozunurlugunde ciziliyordu; burada
    kare panele sigacak sekilde kucultuldugu icin her koordinat `to_panel`
    ile olceklenir. Cizgi kalinliklari ve yazi boyutlari olceklenmez --
    onlar geometri degil, arayuz agirligidir; kucultulseydi 0.71 carpanla
    okunamaz hale gelirdi."""
    fw = int(payload.get("frame_w") or 0)
    fh = int(payload.get("frame_h") or 0)
    if fw <= 0 or fh <= 0:
        return
    clip = (ox, oy, ox + disp_w, oy + disp_h)

    def to_panel(x, y):
        return (int(round(ox + float(x) * s)), int(round(oy + float(y) * s)))

    # Merkez: denetleyicinin CENTERING_STEP'te bildirdigi degeri TERCIH ET
    # (dashboard.py:251-256) -- ekran ile kontrol dongusu ayni nokta uzerinde
    # anlasmali. Ilk adim gelmeden karenin kendi merkezine dusulur.
    cxn, cyn = st.c_center_px or (fw / 2.0, fh / 2.0)
    cx, cy = to_panel(cxn, cyn)
    cv2.line(img, (cx - 20, cy), (cx + 20, cy), (255, 255, 255), 1, cv2.LINE_AA)
    cv2.line(img, (cx, cy - 20), (cx, cy + 20), (255, 255, 255), 1, cv2.LINE_AA)

    # Yakinsama toleransi GERCEK elips olarak (dashboard.py:262-272): +/-0.01
    # normalize, her eksen KENDI yari-genisligiyle normalize edildigi icin
    # bolge bir elipstir (1280x960'ta 6.4 x 4.8 px), sonra panele olceklenir.
    semi_x = max(1, int(round(CENTERING_TOLERANCE_X_NORM * (fw / 2.0) * s)))
    semi_y = max(1, int(round(CENTERING_TOLERANCE_Y_NORM * (fh / 2.0) * s)))
    cv2.ellipse(img, (cx, cy), (semi_x, semi_y), 0, 0, 360, COL_ACCENT, 1, cv2.LINE_AA)

    agl_m = st.vehicle_gps[2] if st.vehicle_gps else None

    for d in payload.get("detections") or []:
        # ADR-010 P5: seklin KENDI dis hatti cizilir -- ucgen ucgen, altigen
        # altigen olarak. Dikdortgen sinir kutulari kaldirildi; kontur yoksa
        # (adapter fallback) bbox AYNI yesille cizilir.
        color = COL_CONTOUR
        contour = _contour_points(d, to_panel)
        if contour is not None:
            cv2.polylines(img, [contour], True, color, 2, cv2.LINE_AA)
            label_anchor = tuple(contour[contour[:, 1].argmin()])
        else:
            bbox = d.get("bbox_px") or [0, 0, 0, 0]
            x1, y1, x2, y2 = bbox
            if x2 > x1 and y2 > y1:
                p1, p2 = to_panel(x1, y1), to_panel(x2, y2)
                cv2.rectangle(img, p1, p2, color, 2, cv2.LINE_AA)
            label_anchor = to_panel(x1, y1)

        cen = d.get("center_px") or [0, 0]
        txn, tyn = float(cen[0]), float(cen[1])
        tx, ty = to_panel(txn, tyn)
        cv2.circle(img, (tx, ty), 5, color, -1, cv2.LINE_AA)

        # Lock gostergesi: hedef merkezlenirken SARI, denetleyici yakinsadigini
        # bildirdiginde SIYAH. Bayrak CENTERING_STEP'ten aynen alinir --
        # ekran "locked"i kendi esigiyle YENIDEN KARAR VERMEZ, bu yuzden lock
        # kaybi (converged=False) otomatik olarak sariya doner.
        locked = st.c_converged and st.c_shape == d.get("shape_type")
        vector_color = COL_LOCKED if locked else COL_VECTOR
        cv2.line(img, (cx, cy), (tx, ty), vector_color, 2 if locked else 1, cv2.LINE_AA)

        label = f"{d.get('shape_type','?')} {float(d.get('confidence', 0.0)):.2f}"
        cv2.putText(img, label,
                    (int(label_anchor[0]), max(oy + 12, int(label_anchor[1]) - 8)),
                    FONT, 0.55, color, 2, cv2.LINE_AA)

        draw_ground_distance(img, d, st, agl_m, (cxn, cyn), (txn, tyn),
                             to_panel, fw, fh, clip)

        # W4.4: servo atesledikten sonra RELEASED_OVERLAY_DURATION_S boyunca,
        # uzerine birakilan hedefi etiketle. Kontura tutturulur (kareye degil)
        # ve zaman kutuludur -- canli bir durum sanilamaz.
        if (st.p_released_at and st.p_released_shape == d.get("shape_type")
                and (time.time() - st.p_released_at) <= RELEASED_OVERLAY_DURATION_S):
            rx = int(label_anchor[0])
            ry = max(oy + 28, int(label_anchor[1]) - 28)
            cv2.putText(img, "RELEASED", (rx, ry), FONT, 0.6, COL_GOOD, 2, cv2.LINE_AA)


def draw_flight_mode_badge(img, st: MissionState, panel_w: int):
    """dashboard.py:402-421 birebir; tek fark konum -- kare uzerine degil,
    KAMERA PANELININ sag ust kosesine sabit (operator istegi). Kare
    kucultuldugunde rozetin de kuculmemesi icin panele cizilir."""
    mode = st.flight_mode or "UNKNOWN"
    is_offboard = mode == "OFFBOARD"
    badge_text = f"OFFBOARD  ({mode})" if is_offboard else f"ONBOARD  ({mode})"
    badge_color = (0, 200, 255) if is_offboard else (120, 220, 120)  # BGR: amber vs yesil
    badge_w = 250
    x0, y0 = panel_w - badge_w - 10, 10
    cv2.rectangle(img, (x0, y0), (x0 + badge_w, y0 + 30), (20, 20, 20), -1)
    cv2.rectangle(img, (x0, y0), (x0 + badge_w, y0 + 30), badge_color, 2)
    text(img, badge_text, x0 + 10, y0 + 21, badge_color, 0.55, 2)


def draw_camera(img, frame, cam: CameraSubscriber, det: DetectionSubscriber,
                st: MissionState, lay: Layout):
    """img: canvas'in kamera kolonu dilimi (cam_h x cam_w)."""
    img[:] = (12, 12, 14)
    if frame is None:
        msg = ("camera disconnected" if cam.frames_received
               else "waiting for camera stream...")
        text(img, msg, 40, lay.cam_h // 2 - 8,
             COL_BAD if cam.frames_received else COL_TEXT_DIM, 0.7, 2)
        text(img, f"ZMQ SUB {cam.zmq_addr}  (camera_service.py yayini)",
             40, lay.cam_h // 2 + 22, COL_TEXT_DIM, 0.45)
        draw_flight_mode_badge(img, st, lay.cam_w)
        return

    h, w = frame.shape[:2]
    s = min(lay.cam_w / w, lay.cam_h / h)
    nw, nh = int(w * s), int(h * s)
    resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
    ox, oy = (lay.cam_w - nw) // 2, (lay.cam_h - nh) // 2
    img[oy:oy + nh, ox:ox + nw] = resized

    payload, age = det.get()
    stale = payload is None or age is None or age > DETECTION_STALE_AFTER_S
    if payload is not None and not stale:
        draw_detection_overlay(img, payload, st, ox, oy, s, nw, nh)

    # Ince bilgi seridi -- dashboard.py:331-352'nin karsiligi. ADR-008 B1:
    # BAYAT TESPIT ile BAYAT KARE ayri ayri raporlanir; ikisi zit anlamlar
    # tasir (donmus video vs. canli video + olu detektor) ve bunlari
    # birlestirmek 2026-08-16 kosusunda ekranin 82 saniye boyunca saglikli
    # gorunmesinin sebebiydi.
    cv2.rectangle(img, (ox, oy), (ox + nw, oy + 26), (0, 0, 0), -1)
    if det.messages == 0:
        text(img, "no detection feed (5556) -- raw frame only",
             ox + 8, oy + 18, COL_TEXT_DIM, 0.5, 1)
    elif stale:
        age_txt = f" {age:.1f}s" if age is not None else ""
        text(img, f"VISION FEED STALE{age_txt} -- detections not drawn",
             ox + 8, oy + 18, COL_BAD, 0.5, 1)
    else:
        n = len(payload.get("detections") or [])
        text(img, f"{n} detection(s)   seq {payload.get('seq','?')}",
             ox + 8, oy + 18, COL_TEXT, 0.5, 1)

    # Alt bant (mektup-kutulama bosluğu) -- kaynak/olcek bilgisi
    if oy + nh + 26 <= lay.cam_h:
        text(img, f"{w}x{h} -> {nw}x{nh} (x{s:.2f})   cam {cam.frames_received} frame"
                  f"   det {det.messages} msg",
             ox + 4, oy + nh + 20, COL_TEXT_DIM, 0.42)

    draw_flight_mode_badge(img, st, lay.cam_w)


# --------------------------------------------------------------------------
# Kolon 3 -- EVENT TIMELINE (core/telemetry/dashboard.py:571-581)
# --------------------------------------------------------------------------
def draw_timeline(img, x0, y0, w, h, st: MissionState, filtered: bool):
    body_y = panel(img, x0, y0, w, h, "EVENT TIMELINE")
    note = "filtreli" if filtered else "ham akis"
    text(img, note, x0 + w - 74, y0 + 17, COL_TEXT_DIM, 0.38)

    events = st.events if filtered else st.events_all
    # dashboard.py: max_lines = (h - 30) // 15, govde y+36'da basliyordu.
    # Burada govde y0+24'te basliyor (panel() imza farki) ve satir 18 px.
    max_lines = max(1, (h - 24 - 16) // TIMELINE_LINE_H)
    yy = body_y + 20
    t0 = st.first_ts or 0.0

    if not events:
        text(img, "olay bekleniyor...", x0 + 14, yy, COL_TEXT_DIM, TIMELINE_SCALE)
        return

    # En yeni ALTTA, [-max_lines:] -- dashboard.py ile ayni kaydirma davranisi.
    for ev in events[-max_lines:]:
        color = SEVERITY_COLOR.get(ev.get("severity"), COL_TEXT)
        ts = ev.get("ts")
        t_rel = (ts - t0) if isinstance(ts, (int, float)) else 0.0
        text(img, f"[{t_rel:6.1f}s] {ev.get('code', '')}", x0 + 14, yy,
             color, TIMELINE_SCALE)
        yy += TIMELINE_LINE_H


def draw_waiting(canvas, log_dir, lay: Layout, cam, det):
    canvas[:] = COL_BG
    cy = lay.H // 2
    text(canvas, "waiting for mission...", 60, cy - 40, COL_ACCENT, 1.0, 2)
    text(canvas, f"izlenen dizin: {log_dir}", 60, cy - 4, COL_TEXT_DIM, 0.5)
    text(canvas, "mission_*.jsonl bekleniyor  |  run_mission_v33_gz.sh",
         60, cy + 22, COL_TEXT_DIM, 0.5)
    text(canvas, f"kamera {cam.zmq_addr}: {cam.frames_received} kare   |   "
                 f"tespit {det.zmq_addr}: {det.messages} mesaj",
         60, cy + 48, COL_TEXT_DIM, 0.5)
    text(canvas, "q / ESC = cikis    f = timeline filtresi    s = ekran goruntusu",
         60, cy + 80, COL_TEXT_DIM, 0.45)


# --------------------------------------------------------------------------
# Ana dongu
# --------------------------------------------------------------------------
def main() -> int:
    log_dir = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "KURSAD40_LOG_DIR", DEFAULT_LOG_DIR)
    zmq_addr = sys.argv[2] if len(sys.argv) > 2 else os.environ.get(
        "KURSAD40_ZMQ", DEFAULT_ZMQ)
    det_addr = sys.argv[3] if len(sys.argv) > 3 else os.environ.get(
        "KURSAD40_DETECTION_ZMQ", DEFAULT_DETECTION_ZMQ)

    fullscreen = os.environ.get("KURSAD40_DASH_FULLSCREEN", "1").strip() not in ("0", "false", "no")
    snap_path = os.environ.get("KURSAD40_DASH_SNAPSHOT", "").strip()
    snap_every_s = float(os.environ.get("KURSAD40_DASH_SNAPSHOT_EVERY_S", "5") or 5)

    sw, sh = detect_screen_size()
    lay = Layout(sw, sh)

    print(f"[DASHBOARD] log_dir   = {log_dir}")
    print(f"[DASHBOARD] kamera    = {zmq_addr}")
    print(f"[DASHBOARD] tespit    = {det_addr}")
    print(f"[DASHBOARD] yerlesim  = {lay.describe()}")
    print(f"[DASHBOARD] timeline filtresi = {'ACIK' if TIMELINE_FILTER_NOISE else 'KAPALI'}"
          f"  (ring {RECENT_EVENTS_MAX})")
    print("[DASHBOARD] read-only: hicbir dosyaya yazilmaz, camera_service baslatilmaz.")
    if snap_path:
        print(f"[DASHBOARD] anlik goruntu: her {snap_every_s:g}s -> {snap_path}")

    cam = CameraSubscriber(zmq_addr)
    cam.start()
    det = DetectionSubscriber(det_addr)
    det.start()

    canvas = np.zeros((lay.H, lay.W, 3), dtype=np.uint8)
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, lay.W, lay.H)
    if fullscreen:
        try:
            cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        except cv2.error as e:  # noqa: BLE001 -- tam ekran yoksa pencereli devam
            print(f"[DASHBOARD] tam ekran ayarlanamadi, pencereli devam: {e}")

    cur_path = None
    tail = None
    positions = None
    st = MissionState()
    filtered = TIMELINE_FILTER_NOISE

    last_scan = last_jsonl = last_pos = last_render = last_snap = 0.0

    def save_snapshot(path):
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            cv2.imwrite(path, canvas)
            print(f"[DASHBOARD] anlik goruntu yazildi: {path}")
        except Exception as e:  # noqa: BLE001 -- goruntu yazimi izleyiciyi oldurmez
            print(f"[DASHBOARD] anlik goruntu yazilamadi: {e}")

    try:
        while True:
            now = time.time()

            # -- yeni mission dosyasi var mi
            if now - last_scan >= MISSION_SCAN_S:
                last_scan = now
                newest = newest_mission_jsonl(log_dir)
                if newest and newest != cur_path:
                    if tail is not None:
                        tail.close()
                    cur_path = newest
                    mid = mission_id_from_path(cur_path)
                    tail = JsonlTail(cur_path)
                    positions = PositionsFile(
                        os.path.join(log_dir, f"mission_positions_{mid}.json"))
                    st = MissionState()
                    st.mission_id = mid
                    print(f"[DASHBOARD] mission takip ediliyor: {mid}  ({cur_path})")

            # -- JSONL tail
            if tail is not None and now - last_jsonl >= JSONL_POLL_S:
                last_jsonl = now
                for e in tail.poll():
                    st.apply(e)

            # -- hedef noktalari
            if positions is not None and now - last_pos >= POSITIONS_POLL_S:
                last_pos = now
                positions.poll()

            # -- render
            if now - last_render >= 1.0 / RENDER_HZ:
                last_render = now
                if tail is None:
                    draw_waiting(canvas, log_dir, lay, cam, det)
                else:
                    canvas[:] = COL_BG
                    draw_camera(canvas[:, :lay.cam_w], cam.get_frame(), cam, det, st, lay)
                    pts = positions.points if positions else []
                    draw_minimap(canvas, lay.col_x, 0, lay.col_w, lay.map_h, st, pts)
                    draw_status(canvas, lay.col_x, lay.map_h, lay.col_w, lay.status_h, st, pts)
                    draw_timeline(canvas, lay.tl_x, 0, lay.tl_w, lay.H, st, filtered)
                cv2.imshow(WINDOW, canvas)

                if snap_path and now - last_snap >= snap_every_s:
                    last_snap = now
                    save_snapshot(snap_path)

            key = cv2.waitKey(15) & 0xFF
            if key in (ord("q"), 27):
                print("[DASHBOARD] cikis istendi")
                break
            if key == ord("f"):
                # Iki ring de her zaman doldurulur, bu yuzden gecis ANINDA ve
                # gecmisi kaybetmeden calisir (yeniden okuma gerekmez).
                filtered = not filtered
                print(f"[DASHBOARD] timeline filtresi -> {'ACIK' if filtered else 'KAPALI'}")
            if key == ord("s"):
                save_snapshot(snap_path or f"dashboard_snapshot_{int(now)}.png")

            try:
                if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    print("[DASHBOARD] pencere kapatildi")
                    break
            except cv2.error:
                break
    except KeyboardInterrupt:
        print("\n[DASHBOARD] interrupted")
    finally:
        cam.stop()
        det.stop()
        if tail is not None:
            tail.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
