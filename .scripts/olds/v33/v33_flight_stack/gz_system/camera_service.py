"""
Ported from V30/V31 (.scripts/olds/v32/camera_service.py, byte-identical
back to v31_3rd_mission) -- the previous v32_flight_stack GzCameraSource
never actually subscribed to Gazebo at all; it just set a one-time
np.zeros() black frame in start() and never updated it again, which is why
the Mission Operations Center's camera panel showed solid black instead of
the real simulated feed.

Runs as a SEPARATE OS process, deliberately: gz-transport's protobuf
bindings can collide with other protobuf usage in the main mission process
(MAVSDK's gRPC client, EventStore's own serialization, etc.) -- isolating
Gazebo's Python bindings here and bridging frames out over ZeroMQ avoids
that entirely, and also survives a Gazebo restart without taking the
mission process down with it. camera_service_manager.py owns launching and
supervising this process; GzCameraSource (gz_camera_source.py) is the
ZMQ-consuming client side (via camera_client.CameraClient).
"""
import threading
import numpy as np
import cv2
import os
import time
import zmq
import argparse

# Ensure protobuf python implementation to avoid descriptor collisions with other libraries
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

import sys
import traceback

try:  # normal import when v33_flight_stack is on PYTHONPATH
    from gz_system.gz_env import apply_gz_env, describe_gz_env
except ImportError:  # spawned as a script from inside gz_system/
    from gz_env import apply_gz_env, describe_gz_env

DEFAULT_GZ_TOPIC = "/world/default/model/x500_mono_cam_down_0/link/camera_link/sensor/camera/image"
DEFAULT_ZMQ_ADDRESS = "tcp://127.0.0.1:5555"

# --- Kesif yoklamasi ---------------------------------------------------------
# KOK NEDEN (2026-08-25): resolve_camera_topic() TEK ATISLIK bir `gz topic -l`
# calistiriyordu. Kamera sensoru topic'i, gz sim ayaga kalktiktan bir sure
# SONRA advertise ediliyor; o ana kadar cagrilirsa liste bos/eksik doner,
# fonksiyon yapilandirilmis topic'e geri duser ve BIR DAHA ASLA denemez.
# Servis "Service is running." yazar, sonsuza kadar sifir kare uretir.
#
# OLCUM (bu makine, px4_sitl gz_x500_mono_cam_down, 3 kosu):
#   sim baslangici -> ilk topic'ler         : ~0 s
#   sim baslangici -> KAMERA topic'i yayinda: 6.3-9.4 s araligi (3/3 kosu)
# Yoklama cozunurlugu ~3 s oldugu icin ust sinir 9.4 s olarak okunmalidir.
#
# _TOPIC_POLL_INTERVAL_S: gz_hook_client.py ile AYNI deger, kasitli --
# ikisi de ayni seyi olcuyor (gz topic -l yoklama araligi).
_TOPIC_POLL_INTERVAL_S = 0.25

# Olculen en kotu durumun (~9.4 s) ~3 kati. NEDEN BU DEGER KALIBRASYON DEGIL
# (gz_hook_client.py'deki _TOPIC_POLL_LIMIT_S ile ayni gerekce): drone, kanca
# veya envelope hakkinda hicbir sey soylemiyor; yalnizca bir TANI beklemesini
# sinirliyor. Sure dolarsa akis IPTAL EDILMEZ -- eskisi gibi yapilandirilmis
# topic'e duser, uyarir, ve asagidaki kare-aclik dedektoru yeniden cozer.
# Yani yanlis secilmesi sessiz bir yanlis sonuc URETEMEZ.
_TOPIC_DISCOVERY_LIMIT_S = 30.0

# Abone olduktan sonra bu sure boyunca HIC kare gelmezse, abonelik yanlis
# topic'e yapilmis demektir (gz-transport var olmayan bir topic'e abone
# olmaya IZIN VERIR -- subscribe() True doner, bu yuzden watchdog'un
# RuntimeError dali hicbir zaman tetiklenmiyordu). Bu durumda RuntimeError
# firlatilir ve watchdog topic'i YENIDEN cozer.
# Taban: gz_hook_client.py::DISCOVERY_SETTLE_S = 2.5 s (olculmus gz-transport
# yerlesme bedeli). Buradaki deger onun ~6 kati; canli bir yayinda 30 Hz'de
# ~450 kare demek, yani saglikli bir akis bu esige asla yaklasmaz.
_FRAME_STARVATION_LIMIT_S = 15.0

try:
    from gz.transport13 import Node
    from gz.msgs10.image_pb2 import Image as ImageMsg
except ImportError as e:
    print(f"[CAMERA_SERVICE] FATAL: Gazebo Python bindings not importable: {e}")
    print("[CAMERA_SERVICE] Fix: ensure PYTHONPATH includes the system Gazebo Python "
          "bindings (/usr/lib/python3/dist-packages on Linux, or "
          "$HOMEBREW_PREFIX/lib/python<X.Y>/site-packages on macOS -- "
          "camera_service_manager.py sets this automatically; running camera_service.py "
          "directly without it will hit this exact error).")
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f"[CAMERA_SERVICE] FATAL: Unexpected error importing Gazebo bindings: {e}")
    traceback.print_exc()
    sys.exit(1)


def _list_topics_once(env, timeout_s: float):
    """Tek bir `gz topic -l` cagrisi. Hata/zaman asimi -> None (bilinmiyor).

    Bos liste ile 'sorgulayamadim' ayrimi KASITLI: bos liste 'sim henuz
    advertise etmedi' demektir ve yoklamaya devam etmek gerekir; None ise
    `gz` CLI'sinin kendisi calismiyor demektir.
    """
    import subprocess
    try:
        result = subprocess.run(["gz", "topic", "-l"], env=env,
                                capture_output=True, text=True, timeout=timeout_s)
    except Exception as e:  # noqa: BLE001
        print(f"[CAMERA_SERVICE] WARNING: 'gz topic -l' failed ({e}).")
        return None
    return [t.strip() for t in result.stdout.splitlines() if t.strip()]


def _match_camera_topic(preferred_topic: str, topics):
    """Yayindaki topic listesinden kamera topic'ini secer, yoksa None."""
    if preferred_topic in topics:
        return preferred_topic
    suffix = "/link/camera_link/sensor/camera/image"
    candidates = [t for t in topics if t.endswith(suffix)]
    if len(candidates) == 1:
        print(f"[CAMERA_SERVICE] Configured topic not live ({preferred_topic}). "
              f"Auto-discovered live camera topic instead: {candidates[0]}")
        return candidates[0]
    if len(candidates) > 1:
        print(f"[CAMERA_SERVICE] WARNING: multiple live camera topics found {candidates}; "
              f"using the first one: {candidates[0]}")
        return candidates[0]
    return None


def resolve_camera_topic(preferred_topic: str, timeout_s: float = 10.0,
                         discovery_limit_s: float = _TOPIC_DISCOVERY_LIMIT_S,
                         sleep=time.sleep, clock=time.monotonic) -> str:
    """
    Canli Gazebo mono-kamera image topic'ini `gz topic -l` ile kesfeder.

    Topic yolu model-ornegine ozgudur
    (.../model/<model_name>_0/link/camera_link/sensor/camera/image) ve
    <model_name> hangi world/model make hedefiyle PX4 SITL baslatildigina
    baglidir. Tek bir varyanti sabit yazmak, baskasi farkli bir varyantla
    baslattigi anda kameranin sessizce sifir kare uretmesi demektir --
    son-ek ile eslestirmek bunu dayanikli kilar.

    BEKLER (2026-08-25 duzeltmesi): kamera topic'i sim ayaga kalktiktan
    ~6-9 s SONRA advertise ediliyor. Eskiden burada TEK bir `gz topic -l`
    vardi; erken cagrildiginda geri duser ve bir daha denemezdi. Artik
    topic gorunene ya da discovery_limit_s dolana kadar yoklanir.

    Sure dolarsa yapilandirilmis topic dondurulur (eski davranis) --
    engellemez, cunku CameraService kare gelmedigini ayrica fark edip
    yeniden cozdurur.
    """
    env = os.environ.copy()
    env.setdefault("GZ_IP", "127.0.0.1")

    deadline = clock() + discovery_limit_s
    attempts = 0
    announced_wait = False
    while True:
        attempts += 1
        topics = _list_topics_once(env, timeout_s)
        if topics is None:
            return preferred_topic          # `gz` CLI yok/bozuk: yoklamanin anlami yok
        match = _match_camera_topic(preferred_topic, topics)
        if match is not None:
            if attempts > 1:
                print(f"[CAMERA_SERVICE] Camera topic became live after {attempts} "
                      f"discovery attempts.")
            return match
        if clock() >= deadline:
            break
        if not announced_wait:
            announced_wait = True
            print(f"[CAMERA_SERVICE] Camera topic not advertised yet "
                  f"({len(topics)} topics live); waiting up to "
                  f"{discovery_limit_s:.0f}s for it...")
        sleep(_TOPIC_POLL_INTERVAL_S)

    print(f"[CAMERA_SERVICE] WARNING: no live camera topic found via 'gz topic -l' "
          f"within {discovery_limit_s:.0f}s ({attempts} attempts). "
          f"Falling back to configured topic (will likely produce zero frames): "
          f"{preferred_topic}")
    return preferred_topic


class CameraStarvationError(RuntimeError):
    """Abonelik kuruldu ama kare AKMIYOR.

    gz-transport, var OLMAYAN bir topic'e abone olmaya izin verir:
    subscribe() True doner ve servis "Service is running." yazar. Bu yuzden
    watchdog'un RuntimeError dali eski kodda ASLA tetiklenmiyordu -- arizanin
    sessiz kalmasinin ikinci sebebi buydu. RuntimeError'dan turuyor ki
    mevcut watchdog `except RuntimeError` dali onu dogal olarak yakalasin.
    """


class CameraService:
    """Subscribes to a Gazebo camera topic and republishes frames over ZeroMQ."""

    def __init__(self, topic: str, zmq_addr: str):
        self.topic = topic
        self.zmq_addr = zmq_addr

        self.node = Node()
        self.latest_frame = None
        self.frame_lock = threading.Lock()

        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.setsockopt(zmq.SNDHWM, 2)  # drop old frames if not consumed fast enough

        self.frame_count = 0
        self.last_fps_time = time.time()
        self.running = False

    def _cb(self, msg: "ImageMsg"):
        try:
            if not msg.data or msg.width == 0 or msg.height == 0:
                return

            W, H = msg.width, msg.height
            step = msg.step if getattr(msg, "step", 0) else W * 3
            rowb = W * 3

            buf = np.frombuffer(msg.data, dtype=np.uint8)
            if buf.size < H * step:
                print(f"[CAMERA_SERVICE] ERROR: Incomplete buffer received. Expected {H*step}, got {buf.size}")
                return

            img_step = buf.reshape((H, step))
            rgb = img_step[:, :rowb].reshape((H, W, 3))
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

            with self.frame_lock:
                self.latest_frame = bgr
        except Exception as e:
            print(f"[CAMERA_SERVICE] ERROR in frame callback: {e}")
            traceback.print_exc()

    def start(self):
        print(f"[CAMERA_SERVICE] Binding ZMQ publisher to {self.zmq_addr}...")
        try:
            self.socket.bind(self.zmq_addr)
        except Exception as e:
            print(f"[CAMERA_SERVICE] FATAL ERROR binding ZMQ: {e}")
            traceback.print_exc()
            raise

        print(f"[CAMERA_SERVICE] Subscribing to Gazebo topic: {self.topic}...")
        try:
            sub_res = self.node.subscribe(ImageMsg, self.topic, self._cb)
        except Exception as e:
            print(f"[CAMERA_SERVICE] Exception during subscribe(): {e}")
            traceback.print_exc()
            raise

        if not sub_res:
            print(f"[CAMERA_SERVICE] FATAL ERROR: Subscribe failed for topic {self.topic}.")
            print("[CAMERA_SERVICE] Please check if Gazebo is running and topic exists ('gz topic -l').")
            raise RuntimeError("Gazebo subscription failed.")

        self.running = True
        print("[CAMERA_SERVICE] Service is running.")

        # Abonelik kuruldu != kare akiyor. Son kare (ya da hic kare gelmediyse
        # abonelik ani) uzerinden _FRAME_STARVATION_LIMIT_S gecerse topic
        # yanlis demektir; CameraStarvationError watchdog'a topic'i YENIDEN
        # cozdurur.
        last_activity = time.monotonic()
        ever_received = False

        try:
            while self.running:
                frame_to_send = None
                with self.frame_lock:
                    if self.latest_frame is not None:
                        frame_to_send = self.latest_frame.copy()
                        self.latest_frame = None  # consume

                if frame_to_send is not None:
                    _, buffer = cv2.imencode('.jpg', frame_to_send, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                    self.socket.send(buffer.tobytes())

                    self.frame_count += 1
                    now = time.time()
                    if now - self.last_fps_time >= 1.0:
                        fps = self.frame_count / (now - self.last_fps_time)
                        print(f"[CAMERA_SERVICE] Publishing at {fps:.1f} FPS | Shape: {frame_to_send.shape}")
                        self.frame_count = 0
                        self.last_fps_time = now

                    last_activity = time.monotonic()
                    ever_received = True
                elif time.monotonic() - last_activity > _FRAME_STARVATION_LIMIT_S:
                    raise CameraStarvationError(
                        f"no frames on '{self.topic}' for "
                        f"{_FRAME_STARVATION_LIMIT_S:.0f}s "
                        f"({'stream stopped' if ever_received else 'never started'}) "
                        f"-- topic is probably wrong; re-resolving")

                time.sleep(0.01)  # small sleep to prevent CPU spin
        except CameraStarvationError:
            raise                      # watchdog yeniden cozsun: YUTMA
        except KeyboardInterrupt:
            print("\n[CAMERA_SERVICE] Keyboard interrupt received.")
        except Exception as e:
            print(f"[CAMERA_SERVICE] Unexpected error in publisher loop: {e}")
            traceback.print_exc()
        finally:
            self.stop()

    def stop(self):
        print("[CAMERA_SERVICE] Stopping service...")
        self.running = False
        self.socket.close()
        self.context.term()
        print("[CAMERA_SERVICE] Shutdown complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Standalone Gazebo Camera Service")
    parser.add_argument("--topic", type=str, default=DEFAULT_GZ_TOPIC, help="Gazebo image topic")
    parser.add_argument("--zmq-addr", type=str, default=DEFAULT_ZMQ_ADDRESS, help="ZMQ Publish Address")
    parser.add_argument("--no-watchdog", action="store_true", help="Disable auto-reconnect watchdog loop")
    args = parser.parse_args()

    # Partition/IP drift is invisible until frames silently stop arriving
    # (gz-transport just never discovers the publisher), so state the
    # EFFECTIVE values up front. apply_gz_env() only fills in defaults, so an
    # explicit value from the manager or the shell still wins.
    apply_gz_env()
    print(f"[CAMERA_SERVICE] gz-transport env: {describe_gz_env()}")

    if args.no_watchdog:
        try:
            CameraService(resolve_camera_topic(args.topic), args.zmq_addr).start()
        except Exception:
            traceback.print_exc()
            sys.exit(1)
    else:
        # Auto-reconnect loop wrapper for Gazebo restarts.
        #
        # DUZELTME (2026-08-25) -- IKI AYRI HATA duzeltildi:
        #
        # (a) resolve_camera_topic() donguIN DISINDA, tek kez cagriliyordu.
        #     Yanlis/erken cozulmus bir topic'i yeniden denemek imkansizdi;
        #     watchdog ayni olu topic'e sonsuza kadar geri donuyordu.
        #
        # (b) Ayni `service` NESNESI yeniden kullaniliyordu. Oysa start()'in
        #     finally blogu stop() cagirip ZMQ socket'ini close(), context'ini
        #     term() ediyor -- yani ikinci start() cagrisi kapali bir socket
        #     uzerinde calisacakti. Watchdog pratikte tek kullanimlikti.
        #
        # Ikisi de her turda TAZE cozum + TAZE nesne ile kapaniyor.
        while True:
            try:
                CameraService(resolve_camera_topic(args.topic), args.zmq_addr).start()
            except RuntimeError as e:
                print(f"[CAMERA_SERVICE] Retrying Gazebo connection in 5 seconds... {e}")
                time.sleep(5.0)
            except KeyboardInterrupt:
                break
            except Exception:
                traceback.print_exc()
                sys.exit(1)
