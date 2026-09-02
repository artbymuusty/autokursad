import asyncio
import yaml
import logging
import os
import sys
import uuid


from core.runtime.main_thread_gui import run_with_main_thread_gui
from gz_system.gz_env import apply_gz_env, describe_gz_env
from gz_system.gz_flight_backend import GzFlightBackend
from gz_system.gz_camera_source import GzCameraSource
from gz_system.gz_payload_actuator import GzPayloadActuator
from gz_system.gz_pose_monitor import GzPoseMonitor

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

# NOT __name__: this module is executed as a script (run_mission_v34_gz.sh runs
# "python -u gz_system/main_gz.py"), so __name__ is "__main__", which is outside
# every namespace configure_all_loggers() sets up ("core", "gz_system",
# "mavsdk_common", ...). Every log line this entrypoint emitted was therefore
# silently dropped. Naming the logger explicitly puts it back under "gz_system".
logger = logging.getLogger("gz_system.main_gz")


async def _run(config: dict, mission_id: str) -> None:
    # ADR-004 §13: constructed and started BEFORE anything mission-related --
    # the dashboard opens the instant RUN MISSION executes, unconditionally,
    # no operator action.
    # legacy_dashboard_default="0": SIM akisinda in-process MissionOpsDashboard
    # artik kurulmaz -- izleme, run_mission_v34_gz.sh'in otomatik baslattigi
    # ayri process'teki tools/mission_dashboard_unified.py'ye devredildi.
    # main_real.py/main_dual.py bu argumani VERMEZ, yani orada varsayilan
    # ACIK kalir (gercek ucusta operatorun tek ekrani odur).
    # KURSAD40_LOG_DIR: gorev loglarini baska bir dizine yonlendirir. Demo
    # kosumlari gercek test loglariyla karismasin diye var; unified dashboard
    # AYNI degiskeni zaten okuyor (tools/mission_dashboard_unified.py:1183),
    # yani tek env ile ikisi ayni dizine bakar. Verilmezse davranis degismez.
    log_dir = os.environ.get("KURSAD40_LOG_DIR", config.get("log_dir", "logs"))
    ops_center = build_ops_center(mission_id=mission_id, log_dir=log_dir,
                                  legacy_dashboard_default="0")
    ops_center.start()
    publisher = ops_center.bus
    context = ops_center.context
    camera = None

    try:
        flight = GzFlightBackend(config["flight_backend"]["connection_string"], publisher=publisher)
        camera = GzCameraSource(config["camera"]["ros2_topic"], config["camera"]["zmq_address"])
        # BUG FIX: camera.start() was never called anywhere in this
        # codebase (pre-existing, not introduced by ADR-004) -- GzCameraSource
        # only ever populates _last_frame inside start(), so every
        # get_frame() call raised "Baglanti yok." forever. Previously this
        # only surfaced once _search_and_engage_loop() began (after
        # connect/arm/takeoff/climb/upload all succeeded); now that vision
        # runs from mission start (_frame_grab_loop/_detection_loop), it
        # surfaced immediately and continuously instead.
        await camera.start()
        # F2: started here, before takeoff, so gz-transport discovery (~2 s)
        # is paid during setup and not while a payload is hanging under the
        # vehicle waiting to be confirmed released.
        pose_monitor = GzPoseMonitor()
        await pose_monitor.start()
        actuator = GzPayloadActuator(config["actuator"]["gazebo_service_name"],
                                     pose_monitor=pose_monitor)

        # BUG FIX (operator-reported): YoloDetector("yolov8n.pt") never
        # actually detected anything -- the path doesn't resolve from this
        # entrypoint's cwd, and even loaded, yolov8n.pt is a stock
        # COCO-pretrained model sharing no class names with
        # MAVI_ALTIGEN/KIRMIZI_UCGEN (see yolo_detector.py's own footgun
        # warning). detect() therefore always returned [], so
        # TargetValidator never reached track-ready and the Mission->Offboard
        # handover never had anything to trigger on -- Mission mode just ran
        # to completion untouched. HSVContourDetector is the one detector in
        # this codebase actually proven to find MAVI_ALTIGEN/KIRMIZI_UCGEN
        # (ported from the working v29/flat-v32 pipeline); swap back to
        # YoloDetector(<real trained model path>) once a real YOLO26 model
        # exists.
        detector = HSVContourDetector()
        validator = TargetValidator()
        selector = TargetSelector()
        debounce = DebounceTracker(publisher=publisher)
        # BUG FIX (operator revision, 2026-08-13, "Mission Lifecycle" --
        # INVALID STATE 7): PositionStore(publisher=publisher) used to
        # default to a FIXED "mission_positions.json" path and LOADS
        # existing data from it on construction -- a previous mission's
        # target records would silently satisfy both_required_targets_found()
        # for a brand-new mission before it ever searched anything.
        # Mission-ID-scoped path, same convention as EventStore's own
        # per-mission log file, guarantees a clean slate every run.
        position_store_path = os.path.join(log_dir, f"mission_positions_{mission_id}.json")
        position_store = PositionStore(storage_path=position_store_path, publisher=publisher)
        interlock = PayloadInterlock(publisher=publisher)
        checkpoint = MissionCheckpoint(publisher=publisher)

        # ADR-008 B1 / ADR-010 P3: one feed, constructed at the composition
        # root and shared by its single producer (VisionRuntime) and every
        # consumer. `detector` is handed ONLY to VisionRuntime -- anything
        # else that needs a detection takes the feed, or a FeedDetector when
        # it must satisfy the IDetector interface.
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
        # Climb-then-Cruise esikleri -- SITL profili.
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

        # ADR-010 P3: Görev 3 consumes the SAME feed as Görev 2. It used to
        # be handed the real detector and call detect() itself -- a second
        # caller into HSVContourDetector's streak state, and the reason its
        # own centering saw 0 committed detections in V1'''.
        pickup_phase = Gorev3PickupPhase(flight, camera, feed_detector, actuator, position_store,
                                          RectangleAlignmentStrategy(), centering, publisher=publisher)
        transport_phase = Gorev3TransportPhase(flight, position_store, centering)
        redrop_phase = Gorev3RedropPhase(flight, actuator, position_store, centering)
        finish_phase = Gorev3FinishPhase(flight, checkpoint, centering)
        gorev3 = Gorev3Orchestrator(interlock, pickup_phase, transport_phase, redrop_phase, finish_phase,
                                     context=context, publisher=publisher)

        master = MasterMissionController(gorev2, gorev3, context=context, publisher=publisher)
        # ADR-008 B2 (A2 row 6): arms the mandatory 10-minute budget to
        # actually DO something. Wired here rather than in build_ops_center()
        # because the ops center is deliberately started before the mission
        # runtime exists (ADR-004 §13).
        ops_center.mission_timeout_hook = master.request_abort
        # ADR-010 P3: vision spans the WHOLE mission -- started before the
        # master FSM and stopped only after it returns, so frames and
        # overlay keep rendering from takeoff to disarm no matter which
        # phase is running. Previously this lived inside Gorev2Orchestrator
        # and died at GOREV2_COMPLETE.
        vision.start()
        try:
            await master.run()
        finally:
            await vision.stop()
            await pose_monitor.stop()
    finally:
        # ADR-004 §13 / §1: always torn down, even on failure -- the
        # dashboard must never linger past the mission it was observing.
        # camera.stop() mirrors camera.start() above -- symmetric lifecycle,
        # guarded for the case construction itself failed before `camera`
        # was ever assigned.
        if camera is not None:
            try:
                await camera.stop()
            except Exception as e:  # noqa: BLE001 -- shutdown must not raise over a cleanup failure
                logger.warning(f"Kamera durdurulurken hata (yoksayiliyor): {e}")
        await ops_center.stop()


def _run_with_main_thread_gui(config: dict, mission_id: str) -> None:
    """macOS entrypoint (ADR-006): gorev worker thread'de, GUI ana thread'de.

    GOVDESI core/runtime/main_thread_gui.py'ye TASINDI (2026-09-02). Bu pompa
    bir donem YALNIZCA burada vardi; main_real.py ve main_dual.py'de olmadigi
    icin macOS'ta GERCEK UCUS dashboard'u hic acilmiyordu (denetim B3). Once
    ortak modul yazilip o iki entrypoint baglandi, sonra -- iki kopyanin
    zamanla ayrismasini onlemek icin -- burasi da ayni moduldeki
    implementasyona devredildi. Davranis birebir ayni: ayni pompa, ayni
    sinyal isleyicileri, ayni sinirli join.

    Ince sarmalayici korundu ki main() degismesin ve platform dalinin
    okunurlugu bozulmasin.

    NOT (bu delegasyonla kapanMAYAN bilinen bosluk): asagidaki main()'in
    Linux/Windows dali `asyncio.run(_run(...))` diyor ve HICBIR sinyal
    isleyicisi kurmuyor -- yani o platformda `kill -INT` denetim B4'un
    tarif ettigi sekilde yutulabilir. main_real/main_dual'in Linux dali
    _run_with_shutdown() kullaniyor ve bu boslugu tasimiyor. Kapsam disi
    birakildi, kayit icin yazildi."""
    run_with_main_thread_gui(lambda: _run(config, mission_id), log=logger)


def main():
    # BUG FIX (runtime investigation, 2026-08-13): must run before any
    # core.*/gz_system.* module logs anything -- see configure_all_loggers()'s
    # own docstring for the full explanation of what was silently invisible
    # without this.
    configure_all_loggers()

    # gz-transport partition/IP must match the simulator's, or every Gazebo
    # subscription silently yields zero frames (macOS: the default
    # "<hostname>:<username>" partition drifts whenever the DHCP hostname
    # changes). Applied here so the mission entrypoint does not depend on a
    # shell having sourced gz_env.sh, and logged so drift is immediately
    # visible instead of showing up as a dead camera panel.
    apply_gz_env()
    logger.info("gz-transport env: %s", describe_gz_env())

    config_path = os.path.join(os.path.dirname(__file__), "config", "gz_system.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    mission_id = uuid.uuid4().hex[:12]

    if sys.platform == "darwin":
        _run_with_main_thread_gui(config, mission_id)
    else:
        # Linux/Windows behaviour is deliberately untouched: the mission owns
        # the main thread and MissionOpsDashboard paints on its own thread.
        asyncio.run(_run(config, mission_id))

if __name__ == "__main__":
    main()
