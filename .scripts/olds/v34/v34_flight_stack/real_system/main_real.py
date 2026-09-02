import asyncio
import yaml
import logging
import os
import uuid

from real_system.real_flight_backend import RealFlightBackend
from real_system.real_camera_source import RealCameraSource
from real_system.real_payload_actuator import RealPayloadActuator

from core.detection.detection_feed import DetectionFeed
from core.detection.vision_runtime import FeedDetector, VisionRuntime
from core.detection.hsv_contour_detector import HSVContourDetector
from core.detection.target_validator import TargetValidator
from core.detection.target_selector import TargetSelector
from core.mission.debounce import DebounceTracker
from core.position_log.position_store import PositionStore
from core.mission.interlock import PayloadInterlock
from core.navigation.centering_controller import CenteringController
from core.navigation.motion_fsm import MotionProfile
from core.mission.payload_release import PayloadReleaseService
from core.mission.gorev2_fsm import PayloadMissionSequencer
from core.navigation.checkpoint import MissionCheckpoint
from core.mission.gorev2_orchestrator import Gorev2Orchestrator
from core.mission.gorev3_pickup import Gorev3PickupPhase
from core.mission.gorev3_transport import Gorev3TransportPhase
from core.mission.gorev3_redrop import Gorev3RedropPhase
from core.mission.gorev3_finish import Gorev3FinishPhase
from core.mission.gorev3_orchestrator import Gorev3Orchestrator
from core.mission.master_fsm import MasterMissionController
from core.mission.rectangle_alignment_strategy import RectangleAlignmentStrategy
from core.telemetry.ops_center import build_ops_center
from core.telemetry.mission_logger import configure_all_loggers
import sys

from core.runtime.shutdown import install_signal_handlers
from core.runtime.main_thread_gui import run_with_main_thread_gui
from core.config.parameters import ABORT_RETURN_DEADLINE_S

logger = logging.getLogger(__name__)


async def _run_with_shutdown(config: dict, mission_id: str) -> None:
    """ADR-010 R4 (denetim B4, 2026-09-02): SIGINT/SIGTERM'i kontrollu bir
    donus-ve-inise cevirir.

    NEDEN BIR SARMALAYICI, NEDEN _run()'IN ICINDE DEGIL: signal.signal()
    yalnizca ANA THREAD'de calisir. main_gz.py _run()'i bir WORKER thread'de
    kosuyor (ADR-006, macOS Cocoa), yani isleyiciyi _run() icine koymak orada
    her calismada ValueError'a duserdi. Burada, asyncio.run()'in ana thread'de
    calistigi gercek-ucus entrypoint'inde kuruluyor -- ayni ADR-010 R4
    korumasi, ortama uygun yerde.

    Iptal SOZLESMESI main_gz ile ayni: gorev task'i iptal edilir,
    MasterMissionController.run() CancelledError'i yakalar ve araci
    baslangic/bitis checkpoint'ine donup indirir (ABORT_RETURN_DEADLINE_S ile
    sinirli). Once bu yoktu: arka planda baslatilan bir gercek ucusta
    `kill -INT` sessizce yutuluyor ve arac HAVADA kaliyordu."""
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()

    def _request_stop():
        if task is not None and not task.done():
            logger.warning("Gorev durduruluyor -- arac baslangic/bitis noktasina donup "
                           "inecek (en fazla %.0fs).", ABORT_RETURN_DEADLINE_S)
            loop.call_soon_threadsafe(task.cancel)

    install_signal_handlers(_request_stop, log=logger)
    await _run(config, mission_id)


async def _run(config: dict, mission_id: str) -> None:
    # ADR-004 §13: constructed and started BEFORE anything mission-related --
    # the dashboard opens the instant RUN MISSION executes, unconditionally,
    # no operator action.
    ops_center = build_ops_center(mission_id=mission_id, log_dir=config.get("log_dir", "logs"))
    ops_center.start()
    publisher = ops_center.bus
    context = ops_center.context
    camera = None

    try:
        flight = RealFlightBackend(config["flight_backend"]["connection_string"], publisher=publisher)
        camera = RealCameraSource(config["camera"]["device_index_or_pipeline"])
        # BUG FIX: camera.start() was never called anywhere in this codebase
        # (pre-existing, not introduced by ADR-004) -- RealCameraSource only
        # ever opens cv2.VideoCapture inside start(), so every get_frame()
        # call raised "Kamera baslatilmamis." forever. Previously this only
        # surfaced once _search_and_engage_loop() began; now that vision
        # runs from mission start (_frame_grab_loop/_detection_loop), it
        # would surface immediately and continuously instead.
        await camera.start()
        actuator = RealPayloadActuator()

        # BUG FIX (operator-reported): see gz_system/main_gz.py for the full
        # explanation -- YoloDetector("yolov8n.pt") never actually detected
        # anything (unresolvable path + wrong classes even if it did), so
        # Mission mode ran with vision permanently blind. HSVContourDetector
        # is the one detector proven to work; swap back to
        # YoloDetector(<real trained model path>) once a real YOLO26 model
        # exists. Its HSV thresholds (parameters.py) were tuned for the
        # earlier v29 camera/lighting setup -- retune against the real
        # camera before competition use if colors look off on the dashboard.
        detector = HSVContourDetector()
        validator = TargetValidator()
        selector = TargetSelector()
        debounce = DebounceTracker(publisher=publisher)
        # BUG FIX (operator revision, 2026-08-13, "Mission Lifecycle" --
        # INVALID STATE 7): see gz_system/main_gz.py for the full
        # explanation -- mission-ID-scoped path prevents a previous
        # mission's target records from leaking into a new one.
        position_store_path = os.path.join(config.get("log_dir", "logs"), f"mission_positions_{mission_id}.json")
        position_store = PositionStore(storage_path=position_store_path, publisher=publisher)
        interlock = PayloadInterlock(publisher=publisher)
        checkpoint = MissionCheckpoint(publisher=publisher)

        # ADR-008 B1 / ADR-010 P3 (denetim B1, 2026-09-02): tek besleme,
        # composition root'ta kurulur; TEK uretici VisionRuntime, geri kalan
        # herkes tuketici. `detector` YALNIZCA VisionRuntime'a verilir;
        # IDetector arayuzunu isteyen baska bir bilesen FeedDetector alir.
        #
        # BU BLOK NEDEN EKLENDI: bu entrypoint VisionRuntime'i hic kurmuyordu.
        # ADR-010 P3 vision donguleri Gorev2Orchestrator'dan cikarip
        # VisionRuntime'a tasidiginda (orchestrator artik saf TUKETICI),
        # main_gz.py guncellendi ama burasi guncellenmedi. Sonuc: uretimde
        # DetectionFeed.publish() yalnizca vision_runtime.py:206'dan
        # cagriliyor ve o dosya burada hic ornek edilmedigi icin besleme HIC
        # DOLMUYORDU -- arama hicbir hedefi dogrulayamaz, merkezleme surekli
        # "hedef kayboldu" gorur, dashboard kamera paneli bos kalirdi.
        # Eski _detection_loop/_frame_grab_loop yoluna DONULMEDI; mevcut
        # VisionRuntime mimarisi dogru sekilde baglandi.
        detection_feed = DetectionFeed()
        vision = VisionRuntime(camera, detector, detection_feed,
                               frame_channel=ops_center.frame_channel, publisher=publisher)
        feed_detector = FeedDetector(detection_feed)

        centering = CenteringController(flight, detection_feed, camera, publisher=publisher)
        centering.kp_horizontal = config["control_gains"]["kp_horizontal"]
        centering.kp_vertical = config["control_gains"]["kp_vertical"]
        centering.kp_altitude = config["control_gains"]["kp_altitude"]
        centering.tolerance_x = config["control_gains"]["centering_tolerance_x"]
        centering.tolerance_y = config["control_gains"]["centering_tolerance_y"]
        # Climb-then-Cruise esikleri -- GERCEK UCUS profili.
        # control_gains ile AYNI desen: YAML blogu yoksa ya da bir anahtar
        # eksikse o alan parameters.py varsayilaninda kalir.
        centering.motion_profile = MotionProfile.from_config(config.get("motion_profile"))

        release_service = PayloadReleaseService(actuator, detection_feed, camera, centering, flight,
                                                publisher=publisher)
        sequencer = PayloadMissionSequencer(flight, centering, interlock, position_store, release_service,
                                             publisher=publisher)

        gorev2 = Gorev2Orchestrator(
            flight=flight, camera=camera, detector=detector, actuator=actuator,
            interlock=interlock, position_store=position_store, debounce=debounce,
            validator=validator, selector=selector, centering=centering, sequencer=sequencer,
            checkpoint=checkpoint, release_service=release_service,
            context=context, publisher=publisher, frame_channel=ops_center.frame_channel,
            detection_feed=detection_feed,
        )

        # ADR-010 P3: Gorev 3 Gorev 2 ile AYNI beslemeyi tuketir. Buraya
        # ham `detector` verilirse HSVContourDetector'in sekil-basina streak
        # durumuna IKINCI bir detect() cagirani girer -- ADR-008 B1'in tam da
        # onlemek icin var oldugu durum. VisionRuntime eklendigi icin bu artik
        # teorik degil: iki gercek uretici olurdu. publisher da geciliyor,
        # aksi halde bu fazin olaylari telemetriye/dashboard'a hic dusmez.
        pickup_phase = Gorev3PickupPhase(flight, camera, feed_detector, actuator, position_store,
                                          RectangleAlignmentStrategy(), centering, publisher=publisher)
        transport_phase = Gorev3TransportPhase(flight, position_store, centering)
        redrop_phase = Gorev3RedropPhase(flight, actuator, position_store, centering)
        finish_phase = Gorev3FinishPhase(flight, checkpoint, centering)
        gorev3 = Gorev3Orchestrator(interlock, pickup_phase, transport_phase, redrop_phase, finish_phase,
                                     context=context, publisher=publisher)

        master = MasterMissionController(gorev2, gorev3, context=context, publisher=publisher)
        # ADR-008 B2 (A2 row 6): makes the mandatory 10-minute budget act.
        ops_center.mission_timeout_hook = master.request_abort
        # ADR-010 P3: vision TUM gorev boyunca yasar -- master FSM'den once
        # baslar, o dondukten sonra durur. Boylece kalkistan disarm'a kadar
        # her faz (Gorev 2, Gorev 3, donus, inis) ayni tek-sahipli beslemeyi
        # tuketir ve goruntu hic durmaz.
        vision.start()
        try:
            await master.run()
        finally:
            await vision.stop()
    finally:
        # ADR-004 §13 / §1: always torn down, even on failure -- the
        # dashboard must never linger past the mission it was observing.
        # camera.stop() mirrors camera.start() above -- symmetric lifecycle,
        # guarded for the case construction itself failed before `camera`
        # was ever assigned. For RealCameraSource this also releases the
        # real cv2.VideoCapture device -- skipping it would leak the camera
        # handle across runs.
        if camera is not None:
            try:
                await camera.stop()
            except Exception as e:  # noqa: BLE001 -- shutdown must not raise over a cleanup failure
                logger.warning(f"Kamera durdurulurken hata (yoksayiliyor): {e}")
        await ops_center.stop()


def main():
    # BUG FIX (runtime investigation, 2026-08-13): see
    # configure_all_loggers()'s own docstring -- without this, virtually
    # every diagnostic log in this project was silently going nowhere.
    configure_all_loggers()
    config_path = os.path.join(os.path.dirname(__file__), "config", "real_system.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    mission_id = uuid.uuid4().hex[:12]

    # ADR-006 (denetim B3, 2026-09-02): macOS'ta dashboard cv2.imshow YERINE
    # MAIN_THREAD_PAINT koprusune yayin yapar (dashboard.py:287). Kopruyu ana
    # thread'de bosaltan bir pompa olmadan kareler yazilir, kimse okumaz ve
    # HICBIR PENCERE ACILMAZ -- gercek ucusta operatorun tek ekrani odur.
    # Bu yol daha once yalnizca main_gz.py'de vardi.
    #
    # Pompa sinyal isleyicilerini de KENDISI kurar, bu yuzden bu dalda
    # _run_with_shutdown'a gerek yok (iki kez kurmak zararsiz ama gereksiz).
    # Linux/Windows'ta dashboard kendi thread'inde boyar, pompaya gerek yok --
    # o yol degismedi.
    if sys.platform == "darwin":
        run_with_main_thread_gui(lambda: _run(config, mission_id), log=logger)
    else:
        asyncio.run(_run_with_shutdown(config, mission_id))

if __name__ == "__main__":
    main()
