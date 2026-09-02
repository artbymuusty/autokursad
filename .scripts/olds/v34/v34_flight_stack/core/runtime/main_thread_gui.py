"""macOS ana-thread boyama pompasi -- gorev worker thread'de, GUI ana thread'de.

NEDEN VAR (ADR-006): Cocoa HER cv2 GUI cagrisinin surecin ANA thread'inde
olmasini sart kosar. ADR-005 §3 dashboard'un durum/kompozisyon/yasam
dongusunu KENDI thread'inde tutar ve §8 tablosu gorev thread'inde dogrudan
cv2 cagrisini yasaklar. Gorev coroutine'ini bir WORKER thread'de kosmak ucunu
birden saglar: gorev thread'i cv2'ye hic dokunmaz, dashboard kendi thread'inde
besteler, boyama artik gorev thread'i OLMAYAN ana thread'de olur.

Kopru: MissionOpsDashboard macOS'ta cv2.imshow yerine MAIN_THREAD_PAINT'e
yayin yapar (dashboard.py:287 `_delegate_paint`). Kopruyu ANA THREAD'de
bosaltan bir pompa olmazsa kareler yazilir ve kimse okumaz -- yani hicbir
pencere acilmaz.

NEDEN ORTAK MODUL (denetim B3, 2026-09-02): bu pompa yalnizca main_gz.py'de
vardi. main_real.py `asyncio.run(_run(...))` diyordu ve icinde `darwin`,
`MAIN_THREAD_PAINT`, `threading` kelimelerinin hicbiri gecmiyordu -- yani
macOS'ta GERCEK UCUS dashboard'u hic acilmiyordu. Operatorun tek ekrani odur.

Gorev coroutine'i bir FABRIKA olarak alinir; boylece modul hangi
entrypoint'in kostuguna dair hicbir sey bilmez.
"""
import asyncio
import logging
import threading
import time

import cv2

from core.config.parameters import ABORT_RETURN_DEADLINE_S
from core.runtime.shutdown import install_signal_handlers
from core.telemetry.paint_bridge import MAIN_THREAD_PAINT

logger = logging.getLogger(__name__)

#: Boyama dongusunun hedef hizi. Dashboard'un KENDI (daha yavas) besteleme
#: temposundan bagimsizdir -- pompa yalnizca en yeni kareyi ekrana tasir.
PAINT_HZ = 30.0
#: Gorev bittikten sonra teardown icin taninan EK sure. Join'in kendisi
#: ABORT_RETURN_DEADLINE_S kadar da bekler (asagiya bakiniz).
TEARDOWN_MARGIN_S = 15.0


def run_with_main_thread_gui(mission_coro_factory, log=None) -> None:
    """Gorevi worker thread'de kosar, ana thread'de MAIN_THREAD_PAINT'i bosaltir.

    mission_coro_factory: cagrildiginda kosulacak coroutine'i DONDUREN callable
        (ornegin `lambda: _run(config, mission_id)`). Fabrika, cunku coroutine
        worker thread'in kendi event loop'unda yaratilmali.
    log: opsiyonel logger -- cagiran kendi modul adiyla loglamak isteyebilir.

    Gorev coroutine'i bir istisna ile biterse o istisna ANA THREAD'de yeniden
    firlatilir; boylece cikis kodu ve traceback normal bir kosumdaki gibi olur.
    """
    _log = log or logger
    holder = {}
    mission_error = {}

    async def _wrapped():
        holder["loop"] = asyncio.get_running_loop()
        holder["task"] = asyncio.current_task()
        await mission_coro_factory()

    def _mission_thread():
        try:
            asyncio.run(_wrapped())
        except asyncio.CancelledError:
            _log.info("Gorev iptal edildi (kapanma UI'dan istendi).")
        except BaseException as e:  # noqa: BLE001 -- asagida ana thread'de yuzeye cikar
            mission_error["exc"] = e
        finally:
            holder["done"] = True

    # daemon=True (ADR-007 madde 10): gorev coroutine'inin kendi teardown'u
    # takilirsa -- orn. MAVSDK'nin gRPC kanali coktan gitmisse, ki iptal
    # edilmis bir kosudan sonra yasandi -- daemon OLMAYAN bir thread
    # yorumlayici cikisini threading._shutdown'da sonsuza kadar bloklar ve
    # surec 14540/50051'i tutmaya devam eder; bir sonraki kosum "Address
    # already in use" alir. Daemonlastirmak bunu sinirlar.
    thread = threading.Thread(target=_mission_thread, name="MissionRuntime", daemon=True)
    thread.start()

    stop_state = {"requested": False}

    def _request_mission_stop():
        """ADR-008 B2: gorev task'ini iptal etmek kontrollu bir kapanmanin
        BASLANGICI, sonu degil. MasterMissionController.run() CancelledError'i
        yakalar ve araci baslangic/bitis checkpoint'ine goturup indirir
        (ABORT_RETURN_DEADLINE_S ile sinirli). Once bu iptal araci HAVADA
        birakiyordu: CancelledError BaseException'dan turedigi icin
        master_fsm'in `except Exception` bloklari onu hic gormuyordu."""
        stop_state["requested"] = True
        loop, task = holder.get("loop"), holder.get("task")
        if loop is not None and task is not None and not task.done():
            loop.call_soon_threadsafe(task.cancel)
            _log.warning("Gorev durduruluyor -- arac baslangic/bitis noktasina donup "
                         "inecek (en fazla %.0fs).", ABORT_RETURN_DEADLINE_S)

    install_signal_handlers(_request_mission_stop, log=_log)

    window_open = False
    window_name = None
    painted = 0
    t_fps = time.time()
    stopping = False
    try:
        while not holder.get("done"):
            item = MAIN_THREAD_PAINT.take()
            if item is not None:
                window_name, image = item
                if not window_open:
                    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
                    cv2.resizeWindow(window_name, image.shape[1], image.shape[0])
                    window_open = True
                cv2.imshow(window_name, image)
                painted += 1

            if window_open:
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27) and not stopping:
                    _log.info("Dashboard'dan cikis istendi (tus) -- gorev durduruluyor.")
                    _request_mission_stop()
                    # ADR-008 B2: bilerek `break` DEGIL. Arac hala havada ve
                    # simdi donus bacagini uculuyor; burada kirmak inisin
                    # tamami boyunca dashboard'u karartirdi -- operatorun ona
                    # en cok ihtiyac duydugu an. Dongu holder["done"] ile,
                    # yani gorev thread'i gercekten inisi bitirince cikar.
                    stopping = True
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    _log.info("Dashboard penceresi kapatildi -- gorev durduruluyor.")
                    _request_mission_stop()
                    # Boyanacak pencere kalmadi, bu yuzden BU kirar --
                    # asagidaki sinirli join yine de donus+inisin bitmesini
                    # bekler.
                    break

            now = time.time()
            if now - t_fps >= 5.0:
                _log.info("Dashboard boyama dongusu: %.1f FPS (ana thread)",
                          painted / (now - t_fps))
                painted, t_fps = 0, now

            if stop_state["requested"]:
                stopping = True

            time.sleep(1.0 / PAINT_HZ)
    except KeyboardInterrupt:
        _log.info("Ctrl-C -- gorev durduruluyor.")
        _request_mission_stop()
    finally:
        # Sinirli kapanma suresi (ADR-007 madde 10 + ADR-008 B2): iptal artik
        # ABORT_RETURN_DEADLINE_S ile sinirli GERCEK bir donus ucusu tetikliyor;
        # ondan kisa bir join, gorev thread'ini donusun ortasinda terk ederdi --
        # yani tam da kaldirilmak istenen "arac havada kaldi" hatasini geri
        # getirirdi. Yine de SONLU: fazlalik yalnizca teardown icin.
        shutdown_deadline_s = ABORT_RETURN_DEADLINE_S + TEARDOWN_MARGIN_S
        thread.join(timeout=shutdown_deadline_s)
        if thread.is_alive():
            _log.error("Gorev calisma zamani kapanmadan %.0fs icinde bitmedi; "
                       "yine de cikiliyor (daemon thread sonlandirilacak).", shutdown_deadline_s)
        if window_open:
            try:
                cv2.destroyAllWindows()
                cv2.waitKey(1)  # Cocoa pencereyi gercekten yiksin
            except Exception:  # noqa: BLE001
                pass

    if "exc" in mission_error:
        raise mission_error["exc"]
