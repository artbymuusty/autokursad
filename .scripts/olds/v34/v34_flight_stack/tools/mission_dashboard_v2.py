"""KURSAD40 Mission Dashboard v2 -- BAGIMSIZ, SALT-OKUNUR izleme process'i.

NEDEN AYRI PROCESS
------------------
core/telemetry/dashboard.py (MissionOpsDashboard) mission process'inin ICINDE
calisir ve ADR-006'nin macOS ana-thread kisitina baglidir: mission coroutine'i
bir worker thread'e tasinmis, composed frame'ler paint_bridge uzerinden ana
thread'e devrediliyor. O tasarim ayakta ve dokunulmuyor.

Bu arac onun yerine gecmez, yaninda kosar. Mission runtime'ina HICBIR baglantisi
yoktur: ne import eder, ne publisher'a abone olur, ne de bir dosyaya yazar.
Uc kaynagi DISARIDAN, salt-okunur izler:

  1. logs/mission_<id>.jsonl     -- EventStore'un append-only JSONL akisi
                                    (event_store.py:59-60 her satirda flush
                                    ediyor, yani tail gecikmesi pratikte sifir)
  2. tcp://127.0.0.1:5555        -- camera_service.py'nin ZMQ PUB yayinina
                                    IKINCI abone. ZMQ PUB/SUB dogal olarak cok
                                    abonelidir; camera_service YENIDEN
                                    BASLATILMAZ (bind tek sahiplidir).
  3. logs/mission_positions_<id>.json -- PositionStore'un hedef kayitlari

Boylece dashboard cokse mission etkilenmez, mission bitse dashboard acik kalir,
ve ayni anda birden fazla izleyici kosabilir.

TESPIT KUTULARI YOK -- BILINEN VE KABUL EDILEN SINIRLAMA
--------------------------------------------------------
Detection overlay'i FrameChannel uzerinden yalnizca mission process'inin
icinde mevcuttur (vision_runtime.py:149-161 kareyi tespitlerle birlikte
FrameChannel'a publish eder; ZMQ'ya giden yayin HAM karedir). Disaridan sadece
ham JPEG alinabilir. Tespit burada YENIDEN CALISTIRILMAZ -- bu, ikinci bir
detect() cagiricisi yaratmamak icin bilincli bir karardir (bkz. ADR-008 B1 /
core/detection/detection_feed.py: tek-dongu invaryanti).

JSONL BASTAN OKUNUR (kasitli sapma)
-----------------------------------
Sartname "dosyayi ac, sonuna git" diyordu. Bunun yerine dosya BASTAN okunur,
sonra tail'e gecilir. Sebep: dashboard gorev basladiktan 30 s sonra acilirsa
"sona git" davranisi CHECKPOINT_SAVED / MISSION_START event'lerini kacirir ve
stepper o adimlari sonsuza kadar "bekliyor" gosterir -- yani gec baglanan
izleyici icin YANLIS bir tablo cizer. Bastan okumak bunu tamamen cozer ve
bedeli yok: tam bir gorev ~4200 event / ~1.5 MB, bir kerelik parse birkac
on milisaniye surer.
"""
import glob
import json
import os
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import zmq

# core.navigation.geo AYNEN kullanilir (kopyalanmaz): checkpoint'e gore
# (north, east) metre delta'si uretir. Yarisma alani olceginde <%0.5 hata --
# modulun kendi beyani (geo.py:10-14).
_STACK_ROOT = Path(__file__).resolve().parent.parent
if str(_STACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_STACK_ROOT))
from core.navigation.geo import gps_to_ned_delta  # noqa: E402

# --------------------------------------------------------------------------
# Yapilandirma
# --------------------------------------------------------------------------
DEFAULT_LOG_DIR = str(_STACK_ROOT.parent / "logs")   # .scripts/olds/v34/logs
DEFAULT_ZMQ = "tcp://127.0.0.1:5555"

WINDOW = "KURSAD40 - Mission Dashboard v2 (read-only)"

CAM_W, CAM_H = 960, 720          # kamera 1280x960 (4:3) -> tam oturur
COL_W = 470                      # sag sutun; dashboard.py'nin 460'ina yakin
MAP_H = 372                      # Panel 1
STATUS_H = CAM_H - MAP_H         # Panel 2

JSONL_POLL_S = 0.15              # tail araligi
POSITIONS_POLL_S = 1.0           # mission_positions_*.json mtime kontrolu
MISSION_SCAN_S = 2.0             # yeni mission dosyasi tarama araligi
CAMERA_STALE_S = 2.0             # camera_client.py:113 ile ayni esik
RENDER_HZ = 15.0

TRAIL_MAX = 600                  # iz icin saklanan nokta sayisi
TRAIL_MIN_STEP_M = 0.25          # bu kadar hareket etmeden yeni nokta eklenmez

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
# Sekil renkleri dashboard.py:107-108 ile ayni.
COL_HEX = (255, 120, 0)          # MAVI_ALTIGEN
COL_TRI = (0, 0, 255)            # KIRMIZI_UCGEN

FONT = cv2.FONT_HERSHEY_SIMPLEX

TERMINAL_OK = "MISSION_COMPLETE"
TERMINAL_BAD = ("MISSION_FAILED", "MISSION_ABORTED", "MISSION_TIMEOUT")


# --------------------------------------------------------------------------
# Kamera -- gz_system/camera_client.py'nin salt-okunur ikizi
# --------------------------------------------------------------------------
class CameraSubscriber:
    """camera_client.CameraClient ile AYNI soket ayarlari ve AYNI bayatlik
    sozlesmesi (RCVHWM=2, CONFLATE=1, SUBSCRIBE=b"", 2 s -> reconnect).

    Neden kopya, neden import degil: bu process'in v34_flight_stack'in
    calisma zamanindan (gz_system paketi, gz binding'leri) bagimsiz kalmasi
    isteniyor -- tek bagimlilik core.navigation.geo, o da saf matematik.
    camera_service'i BASLATMAZ; yalnizca mevcut yayina abone olur.
    """

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
            s.setsockopt(zmq.CONFLATE, 1)   # yalniz en yeni kare, sifir gecikme
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
        except Exception as e:  # noqa: BLE001 -- izleyici asla cokmemeli
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
            except Exception:  # noqa: BLE001 -- akis hatasi izleyiciyi oldurmez
                time.sleep(0.1)

    def get_frame(self):
        """En son kare, ya da bayat/henuz yoksa None (camera_client.py:109-123
        ile ayni sozlesme -- 2 s sessizlik reconnect tetikler)."""
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
# JSONL tail
# --------------------------------------------------------------------------
class JsonlTail:
    """`tail -f` esdegeri, ama BASTAN baslar (modul docstring'indeki gerekce).

    Yarim yazilmis son satir (EventStore write + flush arasinda yakalanirsa)
    tamponda bekletilir, tam satir haline gelince islenir -- bozuk JSON
    yuzunden izleyici asla cokmez.
    """

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
        """Yeni tam satirlardan parse edilmis dict'leri dondurur."""
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
# Her adim: (etiket, mod). Durum, MissionState.step_states() tarafindan
# event akisindan turetilir.
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

    aggregator.RuntimeStateAggregator'in yaptigi isin kucuk, salt-okunur bir
    alt kumesi -- o sinifi import ETMEK yerine burada yeniden turetilir,
    cunku o sinif mission process'inin nesne grafigine (Event dataclass'i,
    EventBus) baglidir; burada elimizde yalnizca duz dict'ler var.
    """

    def __init__(self):
        self.mission_id = ""
        self.first_ts = None
        self.last_ts = None
        self.phase = "-"
        self.checkpoint = None          # (lat, lon, alt)
        self.vehicle_gps = None         # (lat, lon, rel_alt)
        self.flight_mode = "UNKNOWN"
        self.connected = False
        self.trail = []                 # [(east_m, north_m)]
        self.event_count = 0
        self._first_vehicle = None      # checkpoint gelmeden onceki gecici origin

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
        # Bu ayrim olmadan, pickup'ta olen bir kosuda "grapple" adimi yesil
        # gorunur (sonraki adima -- donuse -- gecilmis oldugu icin), yani
        # ekran basarisiz bir kavramayi basarili gibi raporlar.
        self.g3_failed = set()
        self.return_seen = False
        self.landing_seen = False
        self.terminal = None            # MISSION_COMPLETE / _FAILED / ...

    # -- event folding ----------------------------------------------------
    def apply(self, e: dict) -> None:
        self.event_count += 1
        ts = e.get("ts")
        if isinstance(ts, (int, float)):
            if self.first_ts is None:
                self.first_ts = ts
            self.last_ts = ts
        if not self.mission_id:
            self.mission_id = e.get("mission_id") or ""

        code = e.get("code")
        data = e.get("data") or {}

        if code == "MISSION_PHASE_CHANGED":
            to_phase = data.get("to_phase")
            from_phase = data.get("from_phase")
            if to_phase:
                self.phase = to_phase
            if to_phase == "MISSION_START":
                self.mission_start_seen = True
            # "mission continue": GPS_SAVE -> SEARCHING geri donusu
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
            ph = (e.get("data") or {}).get("phase") or e.get("message") or ""
            if ph:
                self.g3_failed.add(ph)
        elif code == "GOREV3_COMPLETE":
            self.g3_complete = True

    # -- turetilmis gorunumler --------------------------------------------
    def origin(self):
        """Minimap origin'i: checkpoint. Henuz kaydedilmediyse ilk gorulen
        arac konumu gecici origin olur (aksi halde kalkis boyunca ~25 s
        bos bir harita gosterilirdi). Panel bunu 'provisional' diye
        isaretler -- uydurulmus bir checkpoint gibi gorunmesin."""
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
        ise ve DAHA SONRAKI bir adim da reached ise, o adim DONE sayilir --
        boylece anlik tetikleyiciler (ornegin GOREV3_PHASE_STARTED) yarim
        kalmis gibi gorunmez."""
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
        # Ulasilan EN SON adim aktif, ondan oncekiler tamamlanmis sayilir.
        # Tetikleyicilerin bir kismi anlik olay (CHECKPOINT_SAVED,
        # GOREV3_PHASE_STARTED) oldugu icin "bitti"yi olaydan degil, BIR
        # SONRAKI adima gecilmis olmasindan turetmek tek tutarli yol.
        last_reached = max((i for i, r in enumerate(reached) if r), default=-1)

        states = []
        for i in range(len(STEPS)):
            if not reached[i]:
                states.append(PENDING)
            elif i < last_reached:
                states.append(DONE)
            else:
                states.append(ACTIVE)

        # Gorev 3 fazi acikca basarisiz olduysa, sonrasina gecilmis olsa bile
        # o adim yesil gosterilemez.
        if "pickup" in self.g3_failed:
            states[7] = FAILED
        if "redrop" in self.g3_failed:
            states[8] = FAILED

        if self.terminal == TERMINAL_OK:
            # Inis tamamlandi: ulasilan her adim kesin tamamlanmistir.
            for i in range(len(STEPS)):
                if states[i] == ACTIVE:
                    states[i] = DONE
        elif self.terminal in TERMINAL_BAD:
            # Basarisiz bitis: tamamlananlar yesil kalir, aktif olan dahil
            # geri kalan her sey kirmizi.
            for i in range(len(STEPS)):
                if states[i] != DONE:
                    states[i] = FAILED
        return states


# --------------------------------------------------------------------------
# Kaynak takibi: hangi mission, hangi dosyalar
# --------------------------------------------------------------------------
def newest_mission_jsonl(log_dir: str):
    files = glob.glob(os.path.join(log_dir, "mission_*.jsonl"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def mission_id_from_path(path: str) -> str:
    return os.path.basename(path)[len("mission_"):-len(".jsonl")]


class PositionsFile:
    """mission_positions_<id>.json -- mtime degistiyse yeniden yukle.

    PositionStore'a yalnizca MAVI_ALTIGEN / KIRMIZI_UCGEN girer
    (gorev2_orchestrator.py:560-563 search adayini bu ikisiyle sinirlar),
    bu yuzden burada sekil filtresi GEREKMEZ -- dosya yapisal olarak zaten
    dikdortgen icermez.
    """

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
            pass  # yazim ortasinda yakalandi; bir sonraki poll'de tekrar dener


# --------------------------------------------------------------------------
# Cizim yardimcilari (dashboard.py:436-445 tarzi)
# --------------------------------------------------------------------------
def text(img, s, x, y, color=COL_TEXT, scale=0.45, thick=1):
    cv2.putText(img, s, (int(x), int(y)), FONT, scale, color, thick, cv2.LINE_AA)


def panel(img, x0, y0, w, h, title, accent=COL_ACCENT):
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
    """Start/Finish: ev silueti (govde + cati)."""
    s = 7
    cv2.rectangle(img, (cx - s, cy - 1), (cx + s, cy + s + 1), color, -1)
    roof = np.array([(cx - s - 2, cy - 1), (cx, cy - s - 3), (cx + s + 2, cy - 1)], dtype=np.int32)
    cv2.fillPoly(img, [roof], color)
    cv2.rectangle(img, (cx - s, cy - 1), (cx + s, cy + s + 1), (255, 255, 255), 1)


def nice_scale_m(span_m, px_per_m, target_px=90.0):
    """Olcek cubugu icin 'yuvarlak' bir metre degeri sec."""
    if px_per_m <= 0:
        return 1.0
    raw = target_px / px_per_m
    for cand in (0.5, 1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000):
        if cand >= raw:
            return float(cand)
    return 1000.0


# --------------------------------------------------------------------------
# Panel 1 -- MAP CONTROL
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

    pts = [(0.0, 0.0)]                       # origin (start/finish)
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
    # dinamik zoom: tum noktalar sabit kenar boslugu ile sigsin
    span_e = max(max_e - min_e, 6.0)
    span_n = max(max_n - min_n, 6.0)
    margin = 26
    scale = min((iw - 2 * margin) / span_e, (ih - 2 * margin) / span_n)
    ce, cn = (min_e + max_e) / 2.0, (min_n + max_n) / 2.0
    cx0, cy0 = ix0 + iw / 2.0, iy0 + ih / 2.0

    def px(e, n):
        return int(round(cx0 + (e - ce) * scale)), int(round(cy0 - (n - cn) * scale))

    # izgara (origin'den gecen eksenler)
    ox, oy = px(0.0, 0.0)
    if ix0 <= ox <= ix0 + iw:
        cv2.line(img, (ox, iy0), (ox, iy0 + ih), COL_GRID, 1)
    if iy0 <= oy <= iy0 + ih:
        cv2.line(img, (ix0, oy), (ix0 + iw, oy), COL_GRID, 1)

    # iz
    if len(st.trail) > 1:
        arr = np.array([px(e, n) for e, n in st.trail], dtype=np.int32)
        cv2.polylines(img, [arr], False, COL_TRAIL, 1, cv2.LINE_AA)

    # hedefler
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

    # start/finish
    home_icon(img, ox, oy, COL_ACCENT)
    text(img, "START/FINISH" if is_real_cp else "START (gecici)",
         ox + 12, oy + 15, COL_ACCENT if is_real_cp else COL_TEXT_DIM, 0.36)

    # arac
    if veh is not None:
        vx, vy = px(*veh)
        cv2.circle(img, (vx, vy), 9, COL_VEHICLE, 1, cv2.LINE_AA)
        cv2.circle(img, (vx, vy), 4, COL_WARN, -1, cv2.LINE_AA)

    # olcek cubugu
    bar_m = nice_scale_m(span_e, scale)
    bar_px = int(round(bar_m * scale))
    bx, by = ix0 + 12, iy0 + ih - 12
    cv2.line(img, (bx, by), (bx + bar_px, by), COL_TEXT_DIM, 2)
    cv2.line(img, (bx, by - 4), (bx, by + 4), COL_TEXT_DIM, 2)
    cv2.line(img, (bx + bar_px, by - 4), (bx + bar_px, by + 4), COL_TEXT_DIM, 2)
    text(img, f"{bar_m:g} m", bx + bar_px + 8, by + 4, COL_TEXT_DIM, 0.38)

    # kuzey oku
    nx, ny = ix0 + iw - 22, iy0 + 26
    cv2.arrowedLine(img, (nx, ny + 14), (nx, ny - 8), COL_TEXT_DIM, 1, cv2.LINE_AA, tipLength=0.4)
    text(img, "N", nx - 4, ny - 12, COL_TEXT_DIM, 0.4)

    if st.vehicle_gps is not None:
        text(img, f"alt {st.vehicle_gps[2]:+.1f} m   {st.flight_mode}",
             ix0 + 12, iy0 + 18, COL_TEXT_DIM, 0.4)


# --------------------------------------------------------------------------
# Panel 2 -- Current Status
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

        # grapple aktifken tasima alt-metni
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
# Kamera paneli
# --------------------------------------------------------------------------
def draw_camera(canvas, frame, cam: CameraSubscriber):
    cv2.rectangle(canvas, (0, 0), (CAM_W, CAM_H), (12, 12, 14), -1)
    if frame is None:
        msg = ("camera disconnected" if cam.frames_received
               else "waiting for camera stream...")
        sub = f"ZMQ SUB {cam.zmq_addr}  (camera_service.py yayini)"
        text(canvas, msg, 40, CAM_H // 2 - 8, COL_BAD if cam.frames_received else COL_TEXT_DIM, 0.7, 2)
        text(canvas, sub, 40, CAM_H // 2 + 22, COL_TEXT_DIM, 0.45)
        return
    h, w = frame.shape[:2]
    s = min(CAM_W / w, CAM_H / h)
    nw, nh = int(w * s), int(h * s)
    resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
    ox, oy = (CAM_W - nw) // 2, (CAM_H - nh) // 2
    canvas[oy:oy + nh, ox:ox + nw] = resized
    # tespit kutulari YOK -- ham yayin (modul docstring'i)
    cv2.rectangle(canvas, (10, 10), (300, 34), (0, 0, 0), -1)
    text(canvas, "RAW FEED - no detection overlay", 18, 27, COL_TEXT_DIM, 0.45)


def draw_waiting(canvas, log_dir):
    canvas[:] = COL_BG
    text(canvas, "waiting for mission...", 60, CAM_H // 2 - 20, COL_ACCENT, 1.0, 2)
    text(canvas, f"izlenen dizin: {log_dir}", 60, CAM_H // 2 + 16, COL_TEXT_DIM, 0.5)
    text(canvas, "mission_*.jsonl bekleniyor  |  run_mission_v34_gz.sh",
         60, CAM_H // 2 + 42, COL_TEXT_DIM, 0.5)
    text(canvas, "q / ESC = cikis", 60, CAM_H // 2 + 74, COL_TEXT_DIM, 0.45)


# --------------------------------------------------------------------------
# Ana dongu
# --------------------------------------------------------------------------
def main() -> int:
    log_dir = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "KURSAD40_LOG_DIR", DEFAULT_LOG_DIR)
    zmq_addr = sys.argv[2] if len(sys.argv) > 2 else os.environ.get(
        "KURSAD40_ZMQ", DEFAULT_ZMQ)

    print(f"[DASHBOARD] log_dir = {log_dir}")
    print(f"[DASHBOARD] zmq     = {zmq_addr}")
    print("[DASHBOARD] read-only: hicbir dosyaya yazilmaz, camera_service baslatilmaz.")

    cam = CameraSubscriber(zmq_addr)
    cam.start()

    total_w = CAM_W + COL_W
    canvas = np.zeros((CAM_H, total_w, 3), dtype=np.uint8)
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, total_w, CAM_H)

    cur_path = None
    tail = None
    positions = None
    st = MissionState()

    last_scan = 0.0
    last_jsonl = 0.0
    last_pos = 0.0
    last_render = 0.0

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
                    draw_waiting(canvas, log_dir)
                else:
                    canvas[:] = COL_BG
                    draw_camera(canvas[:, :CAM_W], cam.get_frame(), cam)
                    pts = positions.points if positions else []
                    draw_minimap(canvas, CAM_W, 0, COL_W, MAP_H, st, pts)
                    draw_status(canvas, CAM_W, MAP_H, COL_W, STATUS_H, st, pts)
                cv2.imshow(WINDOW, canvas)

            key = cv2.waitKey(15) & 0xFF
            if key in (ord("q"), 27):
                print("[DASHBOARD] cikis istendi")
                break
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
        if tail is not None:
            tail.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
