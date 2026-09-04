"""
Bu dosyadaki TODO değerler bilerek boş bırakılmıştır; ekip fiziksel test sonrası dolduracaktır
"""

# --- Görev 2 (Görev 2 Rapor Bölüm 4, 5, 6, 9, 14) ---
YOLO_CONFIDENCE_THRESHOLD: float = 0.70          # Bölüm 5.2
CAMERA_PROCESS_FREQ_HZ_MIN: int = 10             # Bölüm 5.2
CAMERA_PROCESS_FREQ_HZ_MAX: int = 30             # Bölüm 5.2
MISSION_ALTITUDE_M: float = 15.0                 # Bölüm 4.2, 6, 9 [TASARIM KARARI]
HOVER_DURATION_S: float = 2.0                    # Bölüm 9
DEBOUNCE_DURATION_S: float = 10.0                # Bölüm 14
GOREV2_MAX_FLIGHT_DURATION_S: int = 600          # Şartname Bölüm 5.6 (10 dakika, ZORUNLU)

# --- Görev 3 (Görev 3 Rapor Bölüm 4) — TASARIM KARARI, fiziksel testle güncellenecek ---
# 3.0 -> 1.5 (2026-08-21): yuk 0.30x0.225'ten 0.14x0.05'e kuculunce
# 3.0 m'de kameraya 25.2 x 9.0 px = 227 px2 dusuyor ve
# HSV_MIN_AREA_RECT_BASE=400 esiginin ALTINDA kaliyor -- Gorev 3
# Faz 1 dikdortgeni hic goremezdi. 1.5 m'de 50.4 x 18.0 px =
# 907 px2, esikten 2.3x uzak.
GOREV3_TRANSIT_ALTITUDE_M: float = 1.5
#: Gorev 3 gecis bacaklarinin SEYIR irtifasi (Gorev D, 2026-09-03).
#: GOREV3_TRANSIT_ALTITUDE_M ile KARISTIRILMAMALI: o, aracin CALISMA/alma
#: irtifasi (1.5 m) ve gorev3_transport/gorev3_redrop/gorev2_fsm tarafindan
#: tirmanis hedefi olarak da kullaniliyor -- degistirmek alma geometrisini
#: kaydirirdi. Bu sabit YALNIZCA yatay transitin yapildigi ara irtifadir.
#:
#: NEDEN 1.5 DEGIL (olculdu, PX4 ULog, 2. payload -> grapple bacagi):
#:   50.8 m yol, max |v_xy| 11.92 m/s, pitch max 42.09 derece, irtifa 0.9-1.7 m
#: Sebep: goto_global_position_and_wait MUTLAK POZISYON setpoint'i gonderir,
#: hizi PX4 secer ve tavan MPC_XY_VEL_MAX = 12.0 (ULog parametresi; olculen
#: 11.92 ile birebir). MPC_TILTMAX_AIR = 45 derece; olculen 42.09.
#: GOREV3_TRANSIT_SPEED_M_S = 2.0 tanimli ama UYGULANMIYOR
#: (gorev3_transport.py:33 bunu kendisi belgeliyor).
#:
#: 3.0 m, yatay hareketi yer etkisi bolgesinden cikarir ve varis overshoot'unun
#: (15 m'de 0.56 m olculdu) hedefi kacirmasini onler; alcalma hedefin uzerinde
#: DIKEY olarak yapilir.
GOREV3_CRUISE_ALTITUDE_M: float = 3.0

# Gorev 2'nin SON (ikinci) yuk birakmasindan sonraki geri tirmanis irtifasi.
# 2026-08-26 olcumu: uc gercek gorevde payload 2, 0.435 / 0.473 / 0.477 m'de
# birakildi, ardindan release_and_verify() hard-code'lu MISSION_ALTITUDE_M
# (15.0 m) hedefine tirmandi -- tepe 14.69 / 14.71 / 14.75 m, sure 8.9 / 9.0 /
# 9.1 s -- ve tirmanis biter bitmez (~0.11 s sonra) Gorev 3'un ILK komutu olan
# GOREV3_TRANSIT_ALTITUDE_M = 1.5 m'ye geri alcaldi. Yani ~13.2 m tirmanis +
# ~13.2 m alcalma ve ~9 s, TAMAMEN bosa gidiyordu: payload 2'den sonra o
# irtifayi TUKETEN hicbir sey yok (Gorev 2 biter, master_fsm dogrudan Gorev
# 3'e devreder, bkz. gorev3_pickup.py:238-239).
#
# 1.5 m'de emniyet payi (vinc Gorev 2 boyunca TOPLANMIS -- set_winch(EXTEND)
# yalnizca Gorev 3'un activate_pickup_mechanism'inda cagrilir):
#   halat 0.183 m; toplu haldeki kanca ucu base_link'in 0.198 m altinda;
#   birakilan yukun guverte ustu z = 0.070 m
#   -> base_link 1.5 m iken kanca ucu 1.302 m, yani yukun 1.23 m ustunde.
#   -> vinc tamamen disarida takili kalsa bile (0.35 m) 0.88 m bosluk kalir.
#
# ILK birakma bilerek MISSION_ALTITUDE_M'de kaliyor: oradaki tirmanis bosa
# gitmiyor, rota devami (route resume) ve IKINCI hedefin aranmasi tarafindan
# tuketiliyor -- arama Bolum 4.2/6/9'a gore MISSION_ALTITUDE_M'de yapilir.
# Bu yuzden degisiklik yalnizca TERMINAL (son) birakmaya uygulanir.
GOREV2_FINAL_RELEASE_CLIMB_ALTITUDE_M: float = GOREV3_TRANSIT_ALTITUDE_M

GOREV3_DESCENT_ALTITUDE_M: float = 0.30
# Operatör revizyonu (2026-08-13): "1. Yüke dik, 30 cm geride pozisyonlansın"
# / "60 cm ileri giderek yükü aldığımız ortam" -- eski 0.15/0.30 değerleri
# (hiçbir zaman fiziksel testle doğrulanmamış TASARIM KARARI placeholder'lardı)
# operatörün gerçek ölçümleriyle değiştirildi.
GOREV3_RETREAT_DISTANCE_M: float = 0.30
# Birakilan yukun 'yere indi' sayilma esigi. Yuk 0.07 m yuksek,
# yerde dururken merkezi 0.035 m'de; 0.12 m bunun rahatca ustunde
# ama kancada asiliyken (olculdu: 0.226 m) cok altinda.
GOREV3_REDROP_REST_HEIGHT_M: float = 0.12
GOREV3_ADVANCE_DISTANCE_M: float = 0.60
GOREV3_PICKUP_VERIFY_CLIMB_STEPS_M: list[float] = [1.0, 2.0, 3.0]
GOREV3_DROP_CLIMB_STEPS_M: list[float] = [1.0, 2.0]
# GOREV3_ALIGNMENT_ANGLE_DEG (fixed 90.0 placeholder) removed: superseded by
# RectangleAlignmentStrategy.compute_alignment_yaw(), which derives the real
# perpendicular heading from the detected rectangle's own orientation
# instead of assuming a fixed angle (operator revision, 2026-08-13).
# PHASE 12 Q2 (ADR-010): 30 -> 80 attempts, i.e. a 3.0 s -> 8.0 s
# acquisition window at OFFBOARD_SETPOINT_INTERVAL_S.
#
# Applied as instructed. It was NOT expected to fix Görev 3, and the
# measurement said why: at the time, Tools/simulation/gz/worlds/default.sdf
# included exactly two ground models, `blue_hexagon` and `red_triangle`.
# There was no red rectangle in the simulated world at all, so
# KIRMIZI_DIKDORTGEN -- the target this window waits for -- could not
# legitimately be detected no matter how long the vehicle looked, and
# widening the window only bought more chances to catch a FALSE positive.
# See ADR-010 Phase 12 Q2.
#
# SUPERSEDED (2026-08-30, single-competition-area migration). That premise
# no longer holds: default.sdf now includes FOUR ground models --
# blue_hexagon, red_triangle, red_square and blue_square -- all four placed
# by generate_competition_area.py inside the one 30 x 100 m area.
#
# A red square DOES classify as KIRMIZI_DIKDORTGEN. Proof, not assumption:
# hsv_contour_detector.py:129 is the only shape test on the rectangle path,
# `if len(approx) != 4 or not cv2.isContourConvex(approx): continue`. There
# is no aspect-ratio, squareness or maximum-area gate anywhere in
# _detect_rectangle, and :316-317 stamps every 4-gon found on the red mask
# with that exact label. red_square's material is byte-identical to
# red_triangle's (ambient/diffuse 1 0 0), so it lands in the same place in
# the red mask.
#
# TWO QUALIFIERS, both measured:
#  1. ALTITUDE BAND. The 1 m square is only detectable between ~0.57 m and
#     27.0 m. Below ~0.57 m it fills the frame and _touches_border (:154)
#     discards it -- which rules it out at GOREV3_DESCENT_ALTITUDE_M (0.30)
#     and at the ~0.45 m release altitude. The Görev 3 hook altitudes
#     (1.2 m, 0.90 m) are inside the band.
#  2. This makes Görev 3 TESTABLE. It does not make it WORKING. Nothing
#     here has been flown end to end yet; do not read this note as a claim
#     that the phase passes.
GOREV3_PICKUP_ALIGN_MAX_ATTEMPTS: int = 80
GOREV3_PICKUP_VISIBILITY_CONFIRM_FRAMES: int = 3

# TODO[PARAMETRE]: Normal görev seyir hızı (Görev 2/3) hala ekip tarafından
# fiziksel testle belirlenecek -- None birakilmasi bilinçlidir (bkz.
# gorev3_transport.py'nin RuntimeError guard'ı), rastgele bir değer
# UYDURULMAYACAK.
NORMAL_MISSION_SPEED_M_S: float | None = None   # TODO: ekip tarafından doldurulacak
# Operatör revizyonu (2026-08-13): "3 m irtifada, 2 m/s seyir hızı ile ikinci
# yük bırakma konumuna ilerleyecektir" -- ekip tarafından ACIKCA verilen
# gerçek bir değer, NORMAL_MISSION_SPEED_M_S/3 formülünün yerine geçer.
GOREV3_TRANSIT_SPEED_M_S: float | None = 2.0

# Doğrulama renk eşleşmeleri (Görev 2 Rapor Bölüm 13)
VERIFICATION_MARKER: dict[str, str] = {
    "MAVI_ALTIGEN": "KIRMIZI_DIKDORTGEN",
    "KIRMIZI_UCGEN": "MAVI_DIKDORTGEN",
}

# --- Mission Operations Center (ADR-004 / ADR-005) ---
# Health heartbeat cadences: expected interval between events from a given
# subsystem before HealthMonitor marks it DEGRADED/STALE/DOWN. A subsystem
# going silent longer than interval*grace_multiplier is DOWN (ADR-004 §10).
VISION_HEARTBEAT_INTERVAL_S: float = 1.0 / CAMERA_PROCESS_FREQ_HZ_MIN  # worst-case tick at min spec Hz
FLIGHT_TELEMETRY_HEARTBEAT_INTERVAL_S: float = 1.0
HEALTH_GRACE_MULTIPLIER: float = 3.0

# --- ADR-008 B0: MAVSDK telemetry stream cadence ---
# PX4's default position rate is 1 Hz. MavsdkBackendBase used to open a
# fresh `async for ... in telemetry.position()` per get_global_position()
# call and take its first pushed value, so every call cost ~1s -- which
# throttled CenteringController.go_to_and_center() from its designed
# OFFBOARD_SETPOINT_INTERVAL_S (10 Hz) down to ~1 Hz, i.e. 2x PAST PX4's
# ~500ms Offboard timeout, and 10x too slow for HSVContourDetector's
# N-consecutive-frame streak to ever hold. Requested at connect() for
# position / position_velocity_ned / attitude_euler; flight_mode has no
# set_rate_* (PX4 pushes it on change).
TELEMETRY_STREAM_RATE_HZ: float = 10.0
# Bounded wait for the first position fix after connect() -- every getter
# now serves from cache, and a cache miss would otherwise let the
# CHECKPOINT_SAVE read record a (0,0,0) placeholder as the start/finish
# checkpoint.
TELEMETRY_FIRST_SAMPLE_TIMEOUT_S: float = 10.0
# The flight-backend heartbeat is published from the position watcher now,
# not from whoever calls get_global_position(). Throttled so a 10 Hz stream
# does not multiply the JSONL event log tenfold, while staying well inside
# FLIGHT_TELEMETRY_HEARTBEAT_INTERVAL_S (health would only go DEGRADED past
# 1.0s and DOWN past 3.0s).
TELEMETRY_HEARTBEAT_PUBLISH_INTERVAL_S: float = 0.5
# How often the ACHIEVED rate of each stream is measured and published --
# a set_rate_* PX4 accepted but silently did not honour must not look
# identical to one it did.
TELEMETRY_STREAM_RATE_REPORT_INTERVAL_S: float = 10.0
# --- ADR-009 D1: freshness guard on the cached getters ---
# The B0 cache turned a blocking read into a non-blocking one, but nothing
# checked HOW OLD the cached sample was -- so when the MAVSDK channel wedged
# on 2026-08-16 at 23:10:49, get_global_position()/get_velocity_ned() served
# the same frozen sample for 66.8s and goto_global_position_and_wait() flew
# its full 60s timeout computing distance and speed from data that had
# stopped changing. Before B0 a wedged channel blocked or raised; it must
# not silently lie now. 10x the 10Hz stream period: long enough to ride out
# ordinary scheduling jitter, short enough that a dead link is caught inside
# one navigation timeout rather than after it.
TELEMETRY_STALE_AFTER_S: float = 1.0
# flight_mode has no set_rate_* and is pushed on CHANGE, so a long quiet
# period is normal rather than a fault -- it needs its own, looser bound.
TELEMETRY_STALE_AFTER_FLIGHT_MODE_S: float = 3.0

# Watchdog thresholds (ADR-004 §18). MISSION_TIMEOUT_S reuses the existing,
# previously-unenforced GOREV2_MAX_FLIGHT_DURATION_S -- this is what makes
# it finally fire instead of sitting dead in config.
CONNECTION_ESTABLISH_TIMEOUT_S: float = 15.0
MISSION_UPLOAD_ACK_TIMEOUT_S: float = 5.0
# DEPRECATED (ADR-008 B1). This was reported to the dashboard as
# WAITING_CENTERING_CONVERGENCE's timeout, and its comment claimed it
# "matches CenteringController's own 30x0.1s budget" -- stale by two
# revisions: the real budget has been max_attempts x
# OFFBOARD_SETPOINT_INTERVAL_S (150 or 200 attempts) since the precision
# revision. On the 2026-08-16 run the banner therefore advertised a 5s
# timeout while sitting there for 77s and 82s. Nothing ever enforced it
# (set_blocking is display-only), so the number was pure fiction. The
# orchestrator now asks CenteringController.budget_s() for the real one;
# this constant is retained only so no import breaks.
CENTERING_CONVERGENCE_TIMEOUT_S: float = 5.0
# BUG FIX (operator revision, 2026-08-13, "mission_gz supervisor model"):
# starting Mission mode is exclusively the operator's action in
# QGroundControl, same as the route upload itself -- this system only
# waits and observes. Generous timeout since it is a genuine human-paced
# step (arm/takeoff already happened; the operator presses Start Mission
# whenever they're ready), not a network/telemetry round-trip.
OPERATOR_MISSION_START_TIMEOUT_S: float = 300.0  # SUPERSEDED by ADR-007, retained for reference

# ADR-007 (supersedes the 2026-08-13 operator-start rule): the system now
# starts the uploaded mission itself after its own takeoff. Settle time
# between reaching MISSION_ALTITUDE_M and issuing the start, so the vehicle
# is stable in HOLD before Mission mode engages.
MISSION_START_HOLD_S: float = 3.0
# Bounded confirmation that PX4 actually entered Mission mode after the
# start command -- replaces the old 300s human-paced wait.
MISSION_MODE_CONFIRM_TIMEOUT_S: float = 10.0
# ADR-009 PX4-STABILITY (2026-08-17). Minimum wall-clock spacing between two
# Mission resumes. Evidence from three PX4 SITL sessions, all with the same
# code path (stop_offboard -> start_mission), counted from the navigator's
# own "Executing Mission" log lines:
#
#   session            resumes  min gap   outcome
#   V1'  10_17_23.ulg     4     14.39s    survived, clean landing + disarm
#   V2'  10_28_08.ulg     4      5.04s    4th resume SILENTLY ignored -> HOLD -> PX4 stopped
#   V2   20_06_33.ulg   450      0.11s    wedged; pause_mission() timed out; PX4 died
#
# 15.0s because 14.39s is the smallest spacing actually observed to survive
# -- this is the evidence, not a tuned value. It costs search time, so it is
# a floor to revisit once the confirm/retry below has some flight history.
# ADR-010 R2: 15.0 -> 6.0. The 15s figure was chosen when EVERY failed
# pursuit resumed the route; R1's retry-in-place makes resumes rare (only
# after a target is abandoned at the cap, or a genuine offboard failure),
# and every resume is now confirmed with a retry rather than fired blind.
# 6.0 sits above the 5.04s spacing that PX4 silently ignored on
# 2026-08-17, with the confirm/retry carrying the actual safety.
MISSION_RESUME_MIN_INTERVAL_S: float = 6.0

# --- ROUTE REJOIN (2026-08-29, operator-requested, DEFAULT OFF) -----------
# _resume_mission_route() has always just told PX4 "continue from mission
# item <index>" (set_current_mission_item + start_mission). PX4 then flies
# a straight line from wherever the vehicle actually IS (offset after a
# pursuit's lateral/vertical manoeuvring) to that item -- NOT back to the
# search route's own line. Operator-observed: after centering on an
# off-route target, the vehicle can resume the search noticeably off the
# original transect instead of re-joining it.
#
# ENABLE_ROUTE_REJOIN=True makes _resume_mission_route() correct the ONE
# axis the uploaded QGroundControl route holds fixed (detected from the
# route's own raw mission-item coordinates, never assumed) back to its
# value from just before the pursuit started, using the existing
# goto_global_position_and_wait() primitive -- the OTHER axis (direction of
# travel) is left at the vehicle's current position, so this is a lateral
# correction, not a return to a specific prior point. The route itself
# (QGroundControl's job, never generated here) is untouched either way.
#
# DEFAULT FALSE: unmeasured impact on ADR-009's resume timing (a documented
# history of PX4 wedging when resume spacing/confirmation was got wrong).
# Flip only after SITL measurement shows the added offboard time does not
# violate MISSION_RESUME_MIN_INTERVAL_S's margin.
# REVERTED to the documented default (2026-09-02). The TEMP flip above was
# the SITL measurement round of 2026-08-29 and its own comment said
# "reverting after"; it was never reverted. Left on, it also broke 9 tests
# in three files (test_mission_route_resume, test_adr009_stale_health_
# backoff_speed, test_adr010_retry_in_place_and_resume): those construct the
# orchestrator with Gorev2Orchestrator.__new__() to bypass __init__, so the
# _rejoin_route_axis() call this flag enables read a self._route_axis that
# the bypassed __init__ never set -- AttributeError, not a flight bug.
# ACILDI (F2-a madde 4, 2026-09-04). Onkosullar tamamlandi:
#   madde 1 -- test fixture'lari _route_axis'i kuruyor (AttributeError gitti)
#   madde 2 -- rejoin yalnizca Offboard'a GERCEKTEN girildiyse calisiyor
#              (F1 basarisizlik yolunda 15 s bosa bekleme riski kesildi)
#   madde 3 -- kod yolunun ilk 12 testi yazildi (once SIFIR kapsam vardi)
# Asagidaki 'DEFAULT FALSE' gerekcesi TARIHSEL olarak birakildi; ADR-009
# resume zamanlamasina etkisi bu acilisla ILK KEZ olculuyor.
ENABLE_ROUTE_REJOIN: bool = True
# Convergence tolerance for the rejoin manoeuvre is GPS_POSITION_CONVERGENCE_
# TOLERANCE_M -- goto_global_position_and_wait() is reused UNCHANGED (it is
# not parameterised for tolerance), so this is that same "close enough" as
# every other GPS-goto in this codebase, not a new precision requirement.
#
# Upper bound on how long the rejoin manoeuvre may run before giving up and
# falling through to the normal resume (best-effort, never a hard gate).
ROUTE_REJOIN_TIMEOUT_S: float = 15.0
# ADR-010 R2: PX4 refused OFFBOARD 4 times in V1'' when a pursuit's
# pause_mission() landed ~1s after a resume's start_mission(). Give the
# autopilot this long to settle in MISSION before asking it to leave again.
OFFBOARD_AFTER_RESUME_SETTLE_S: float = 2.0

# Ops Center runtime cadence
WATCHDOG_CHECK_INTERVAL_S: float = 1.0
DASHBOARD_REFRESH_HZ: float = 10.0

# QGroundControl connection visibility (operator-requested: "let's see in
# the mission board whether QGC is connected or not"). MAVSDK exposes no
# API for "which other GCS clients are connected to this vehicle" -- this
# is a genuine platform limitation, not something we can query directly.
# QGC_UDP_PORT is its conventional default listen port; QgcMonitor treats
# "something locally bound to this port" as a heuristic proxy for "QGC (or
# an equivalent GCS) is running" -- honest best-effort, not a definitive
# MAVLink-level confirmation that QGC is actively receiving telemetry.
QGC_UDP_PORT: int = 14550
QGC_CHECK_INTERVAL_S: float = 2.0

# --- Centering closed-loop control (Görev 2 Rapor Bölüm 8-9) ---
# BUG FIX (operator-reported): go_to_and_center() previously computed pixel
# error and then just checked it against a threshold -- it never called
# set_velocity_body() at all, so nothing ever actually drove the vehicle
# toward the target regardless of Offboard being active. This is the
# minimum viable, physically bounded proportional controller; kp_horizontal/
# kp_vertical (config-injected per real_system.yaml/gz_system.yaml) and
# MAX_CENTERING_SPEED_M_S are placeholders the team will retune after
# physical flight testing, same as every other TODO gain in this file --
# but centering now actually commands the vehicle, which it did not before.
# ADR-009 S1 (operator, 2026-08-16, measured from the V1 baseline): 2.0 -> 3.0.
# V1 showed |ey| decaying with tau ~= 17-23s against a 15s budget, so every
# first-lock pursuit timed out and targets were only captured after 5-6
# cumulative pursuits walked the error down.
MAX_CENTERING_SPEED_M_S: float = 3.0
# ADR-009 S1: floor on the commanded lateral speed while OUTSIDE tolerance.
# V1 pursuit 6 stalled at |ey|=0.0146 (~7px, 0.20m ground) where the control
# law asks for 0.0146 * 0.3 * 2.0 = 0.009 m/s -- 9 mm/s, below what PX4
# tracks against drift, so the error stopped shrinking entirely while the
# budget drained. Inside tolerance the command is still exactly 0, so this
# adds no limit-cycle of its own: it only removes the dead zone between
# "outside tolerance" and "commanding something PX4 can act on".
CENTERING_MIN_CMD_SPEED_M_S: float = 0.15
# ADR-009 S2 (operator, 2026-08-17). S1's floor was a single speed for every
# altitude, but the centering tolerance is ANGULAR (normalized pixels), so
# its ground-equivalent shrinks with altitude. Measured on V1':
#
#   alt      ground tolerance band      one 0.1s step at the 0.15 m/s floor
#   15.00m   0.1778 m                   0.015 m   (0.1x  -- fine)
#    0.45m   0.0053 m                   0.015 m   (2.8x  -- overshoots)
#    0.30m   0.0036 m                   0.015 m   (4.2x  -- guaranteed limit cycle)
#
# Both 0.30m payload steps in V1' failed to converge and one diverged
# (|ey| 0.0042 -> 0.1396). The floor is now capped so a single iteration can
# never cross more than this fraction of the tolerance band:
#
#   floor(alt) = min(CENTERING_MIN_CMD_SPEED_M_S,
#                    CENTERING_FLOOR_TOL_FRACTION * ground_tol(alt)
#                    / OFFBOARD_SETPOINT_INTERVAL_S)
#
# 0.5 keeps at least two iterations inside the band on approach, which is
# what prevents the bang-bang crossing; at mission altitude the absolute
# 0.15 m/s cap still binds, so high-altitude behaviour is untouched.
CENTERING_FLOOR_TOL_FRACTION: float = 0.5
# Operator request (2026-08-17): convergence is a single-frame test, so
# measure how far the target slides in the frame over this window right
# after a lock. Telemetry only -- it gates nothing.
POST_LOCK_DRIFT_WINDOW_S: float = 3.0
# PX4 auto-exits Offboard if it doesn't receive a new setpoint within ~500ms
# (hard PX4 safety behavior, not configurable away) -- this must stay well
# under that, not just "fast enough to look responsive".
OFFBOARD_SETPOINT_INTERVAL_S: float = 0.1
OFFBOARD_MODE_CONFIRM_TIMEOUT_S: float = 3.0

# --- Centering precision + staged payload approach (operator revision,
# 2026-08-13) ---
# go_to_and_center() already computed error_x_norm/error_y_norm but
# converged on a raw-pixel threshold instead -- these replace that with the
# operator's actual precision requirement. Config-injected per
# real_system.yaml/gz_system.yaml, same pattern as kp_horizontal/kp_vertical.
CENTERING_TOLERANCE_X_NORM: float = 0.01
CENTERING_TOLERANCE_Y_NORM: float = 0.01
# BUG FIX (operator-reported, 2026-08-13): go_to_and_center()'ın lateral-only
# (irtifa değişmeyen) çağrıları -- yani İLK kilitlenme geçişi -- eskiden
# sabit 30 deneme (3 saniye) kullanıyordu; bu, eski 20px toleransı için
# ayarlanmıştı. ±0.01 normalize tolerans ~6-9 kat daha sıkı, ve 3 saniye
# gerçek kamera/kontrol gürültüsüyle bu hassasiyete ulaşmak için yetersiz --
# operatörün bildirdiği "kilitleniyor ama sonrasını tamamlayamıyor"
# belirtisine katkıda bulunan ikinci neden buydu (birincisi:
# _resume_mission_route eksikliği, bkz. gorev2_orchestrator.py).
CENTERING_LATERAL_TIMEOUT_S: float = 15.0
# ADR-008 B1: the "any real altitude change" attempt budget, lifted out of
# go_to_and_center()'s body where it was a bare `200` literal. Unchanged in
# value -- it is now also readable by CenteringController.budget_s(), which
# is what the dashboard's WAITING_CENTERING_CONVERGENCE timeout reports.
CENTERING_ALTITUDE_CHANGE_ATTEMPTS: int = 200
# ADR-009 D3: a real centering failure must never become a pause/resume
# storm. Proven necessary by the 2026-08-16 23:06 forced-failure run: every
# failed pursuit immediately re-engaged the same still-track-ready target,
# producing 585 pursuits and 601 Mission resumes in 3.5 minutes (~3 PX4
# pause/resume cycles per second) until PX4 stopped responding and
# pause_mission() timed out. After this many failed attempts on one shape,
# the orchestrator logs "target seen but not centered" and carries on
# searching instead of retrying forever.
# --- GOREV F (2) 2026-09-04: Offboard-gecis hatasi icin AYRI sinir ---
# NEDEN AYRI: _centering_attempts/CENTERING_MAX_ATTEMPTS_PER_TARGET
# MERKEZLEME basarisizligi icin kurulmus (hedefi goruyorum ama ustune
# oturamiyorum). Offboard gecis hatasi BASKA BIR SINIF: hedefin
# gorunurluguyle ilgisi yok, muhtemelen gecici bir otopilot durumu. Ikisini
# ayni sayacta toplamak, bir otopilot aksakligi yuzunden GORUNUR bir hedefi
# kalici terk etmeye yol acardi.
#
# DEGER 3, olculen doz-yanittan: kosum basina Offboard hata dagilimi
# 0 hata -> 77 kosum, 1 -> 32, >=2 -> 15; ve rota erken bitme orani
# 0 hata %2, 1 hata %4, >=2 hata %60. 1 hata cok yaygin ve neredeyse zararsiz;
# zarar >=2'de patliyor. 3'te kesmek tek bir gecici aksakliga tolerans
# birakirken butce tuketen kuyrugu keser.
# --- K6 (2026-09-04): pause_mission() ile offboard.start() ARASINA BEKLEME ---
# KOK NEDEN (docs/gorevF1-offboard-start-kok-neden.md): MAVSDK v3.17.2'de
# CommandIdentification, DO_SET_MODE (176) icin komut PARAMETRELERINI
# ICERMIYOR (maybe_param1/2 yalnizca REQUEST_MESSAGE ve SET_MESSAGE_INTERVAL
# icin doldurulur). Dolayisiyla:
#     mission.pause_mission() -> DO_SET_MODE 176, main=4 (AUTO/LOITER)
#     offboard.start()        -> DO_SET_MODE 176, main=6 (OFFBOARD)
# ikisinin kimligi BIREBIR AYNI {0,0,176,1,1}. pause'un ACK'i hala yoldayken
# start() kendi is kalemini kuyruga koyarsa, gelen ACK offboard kalemine
# ATFEDILIP onu Success ile coziyor -- offboard komutu HIC GONDERILMEDEN.
# start() hatasiz doner, PX4 hicbir sey almaz, arac HOLD'da kalir.
#
# DEGER OLCULDU (tools/offboard_gap_sweep.py, 175 deneme, tek SITL oturumu):
#     0 ms -> 5/25 basarisiz (%20.0)      [kulliyat ortalamasi %24.4]
#    20 ms -> 0/25          40 ms -> 0/25         100 ms -> 0/25
#    30 ms -> 0/25          50 ms -> 0/25         200 ms -> 0/25
# Diz noktasi 0-20 ms arasinda, yani cakisma penceresi TAM BIR ROUND-TRIP
# kadar (olculen start() round-trip'i 11-14 ms, en yuksek 25.4 ms).
# >=20 ms olan alti bekleme birlesik: 0/150 -> %95 ust sinir ~%2.0.
#
# NEDEN 20 DEGIL DE 50: 20 ms TARANAN EN DUSUK degerdi, altinda olculmus pay
# yok. 50 ms round-trip'in ~4 kati ve gozlenen en yuksek start() suresinin
# (25.4 ms) 2 kati. Maliyet gorev basina 2-4 takip x 50 ms = 0.1-0.2 s,
# 600 s'lik butcede olculemez. 100-200 ms'nin EK FAYDASI OLCULMEDI.
#
# BU BIR ONLEMDIR, sinirlayici degil: F1 guard'i (OFFBOARD_FAILURE_MAX_PER_TARGET)
# ucuncu savunma katmani olarak KALIR -- 0/150'in ust siniri %2, sifir degil.
OFFBOARD_PAUSE_SETTLE_S: float = 0.05

OFFBOARD_FAILURE_MAX_PER_TARGET: int = 3
CENTERING_MAX_ATTEMPTS_PER_TARGET: int = 3
# Minimum spacing between two centering attempts on the SAME shape, so even
# below the cap the route gets uninterrupted flying time between pursuits.
# ADR-010 R1: 10.0 -> 5.0. This is no longer a "fly the route and come
# back" gap -- it is a HOLD IN PLACE over the target between attempts, so
# it only needs to be long enough for the vehicle to settle after the
# previous attempt's last velocity command, not long enough to re-acquire.
CENTERING_RETRY_COOLDOWN_S: float = 5.0
# ADR-009 D3: lets a validation run shorten the centering budget without
# touching config or any gain -- the faithful replacement for the
# instant-fail hook, which distorted pacing so badly it wedged PX4.
CENTERING_LATERAL_TIMEOUT_ENV: str = "KURSAD_CENTERING_LATERAL_TIMEOUT_S"

# --- ADR-008 B1: shared detection feed ---
# A single detection loop (Gorev2Orchestrator._detection_loop) is the only
# caller of detector.detect(); centering and payload verification consume
# its latest result instead of running their own detect() calls. A consumer
# must still be able to tell "the loop just told me there is no target"
# from "the loop has gone quiet", so any sample older than this counts as
# no sample at all. Also bounds how long a stale box may stay drawn on the
# dashboard overlay: on 2026-08-16 the frozen KIRMIZI_UCGEN box was redrawn
# on live frames for 82s while nothing was detecting, which is exactly why
# the run looked like vision was alive.
DETECTION_STALE_AFTER_S: float = 0.5

# --- Deferred payload-mission GPS navigation (operator revision, 2026-08-13:
# Mission = search-only, Payload Mission 1/2 run AFTER search completes,
# from wherever the vehicle happens to be -- see
# core/navigation/geo.py + CenteringController.goto_global_position_and_wait) ---
GPS_POSITION_CONVERGENCE_TOLERANCE_M: float = 2.0
# BUG FIX (regression investigation, 2026-08-13): goto_global_position_and_wait()
# used to declare convergence on position alone, with no check that the
# vehicle had actually slowed down -- proven via live instrumentation to
# fire while the vehicle was moving at ~11 m/s, mid-flight through the
# target's 2m radius, causing it to coast ~10-25m past before anything
# else corrected it. The prior (pre-Mission-Lifecycle-revision) codebase's
# proven working equivalent (.scripts/olds/v34/mission.py::_state_return_home,
# used only as a behavioral reference, not copied) always gated arrival on
# 3D velocity magnitude alongside position, not position alone. Its own
# value (0.05 m/s) was tuned for a strict final-landing approach; this
# tolerance only needs to be "slowed enough for the following staged-descent
# centering to have a fair chance", so it's scaled to this codebase's own
# existing tolerances (GPS_POSITION_CONVERGENCE_TOLERANCE_M=2.0,
# ALTITUDE_CONVERGENCE_TOLERANCE_M=0.3) rather than copied verbatim.
GPS_POSITION_VELOCITY_TOLERANCE_M_S: float = 0.3
GLOBAL_POSITION_NAV_TIMEOUT_S: float = 60.0

# --- ADR-008 B2: return to the start/finish checkpoint on every terminal path ---
# Before this, exactly ONE of the eight terminal paths flew back to the
# recorded checkpoint (Görev 3 completing successfully); every failure,
# timeout, watchdog and Ctrl-C path either landed wherever the vehicle
# happened to be or -- for Ctrl-C and the mission-timeout watchdog -- did
# not land at all. Proven on 2026-08-16: search ended incomplete and the
# vehicle landed 39.8m+ north of its checkpoint.
RETURN_TO_START_FINISH_HOLD_S: float = 2.0
# Hard ceiling on the return leg when the mission is being ABORTED
# (Ctrl-C / dashboard close / MISSION_TIMEOUT). Must stay under
# main_gz.py's mission-thread join timeout, or the process would abandon
# the thread mid-return.
ABORT_RETURN_DEADLINE_S: float = 45.0
# ADR-009 D1: how long the return-to-start path waits for a stale vehicle
# link to recover before giving up and landing in place. Short enough that
# it cannot eat the abort deadline, long enough to ride out a hiccup.
TELEMETRY_RECOVERY_WAIT_S: float = 5.0

# Separate from kp_vertical (which controls the image-Y/forward-body-axis,
# not altitude) -- altitude convergence is a distinct physical axis and
# needs its own gain/tolerance.
KP_ALTITUDE: float = 0.5
ALTITUDE_CONVERGENCE_TOLERANCE_M: float = 0.3
# Payload approach sequence (operator spec): from mission altitude, step
# down through these altitudes, re-centering at each one, before the final
# forward nudge and servo release. Shared by both payload drops (Mavi
# Altıgen / Kırmızı Üçgen) and by Görev 3's redrop -- same staged-descent
# primitive, just called with different target shapes/positions.
# OPERATÖR REVİZYONU (2026-08-17): son bırakma irtifası 0.30 m -> 0.45 m.
# Yük artık düzleme 45 cm'den bırakılır. Ara adımlar (10 m, 5 m) ve
# PAYLOAD_FINAL_FORWARD_M (10 cm ileri kayma) değişmedi.
#
# Yan fayda (ADR-009 S1 ölçümü): merkezleme toleransı AÇISAL (normalize
# piksel), yani yere karşılığı irtifayla ölçeklenir -- 0.30 m'de tolerans
# bandı yalnızca 3.6 mm iken CENTERING_MIN_CMD_SPEED_M_S tabanı tek
# iterasyonda 15 mm yol aldırıyordu (4.2x band). V1' koşusunda her iki
# 0.30 m adımı da bu yüzden yakınsayamadı. 0.45 m'de band 5.3 mm'ye
# çıkar, oran 4.2x -> 2.8x'e düşer: iyileşir ama 1x'in ALTINA inmez, yani
# taban sorununu çözmez (bkz. rapor -- tabanın irtifaya bağlı olması
# gerekiyor).
PAYLOAD_APPROACH_ALTITUDES_M: list[float] = [10.0, 5.0, 0.45]
PAYLOAD_FINAL_FORWARD_M: float = 0.10

# --- ADR-010 P1: low-altitude vision limit + hybrid (open-loop) descent ---
# MEASURED, not assumed -- from the V1''' run (mission_81cfefe66ad7), per
# centering call, the altitude of the LAST committed detection before a
# sustained loss:
#
#   KIRMIZI_UCGEN  0.45m step : tracked down to 0.47 m (151 seen / 49 lost)
#   MAVI_ALTIGEN   0.45m step : lost at 1.63 m, first miss 1.47 m
#                               (29 seen / 171 lost) -> stalled, released 1.587 m
#
# The limit is shape-dependent because the loss is GEOMETRIC, not a
# threshold that could be tuned: _detect_hexagon approximates the contour
# with a SINGLE eps and requires exactly 6 convex vertices, so as soon as
# the hexagon clips the frame edge its contour stops being a hexagon and no
# eps sweep can recover it. The triangle survives lower (smaller footprint,
# and it is tried over 6 eps values). Detector gates are explicitly out of
# scope, so the fix is to stop REQUIRING vision below this altitude.
#
# 2.0 m sits just above the highest observed loss (1.63 m) with margin. It
# is a GATE, not a mode switch: above it, losing the target still means
# hold (something is wrong and open-loop would be unsafe); below it, losing
# the target is expected and the descent continues on the frozen estimate.
LOW_ALT_VISION_LIMIT_M: float = 2.0

# SEKLE BAGLI ESIK (2026-08-24). Yukaridaki 2.0 m ALTIGEN ve UCGEN icin
# olculdu: onlar arena hedefleri (5.00 m ve 1.00 m genisliginde) ve alcakta
# kadrajin kenarini kirptiklari an konturlari artik 6-gen/3-gen olmuyor.
# Gorev 3'un aradigi KIRMIZI_DIKDORTGEN ise BIRAKILAN YUK: 0.14 x 0.05 m.
# 1.2 m'de kadraj 2.84 x 2.13 m, yuk yalnizca 63 x 22 piksel -- kenara
# degmesi icin merkezden 1 m'den fazla kaymasi gerekir. Yani 2.0 m'lik
# esigi haklı cikaran geometrik gerekce bu sekil icin gecerli DEGIL.
#
# Bunu gormeden once hizalama merkezlemesi tek iterasyonda acik cevrime
# dusuyordu (olculdu, 02:33:47 kosusu):
#     [CENTERING] KIRMIZI_DIKDORTGEN 1/200 dx=+21px dy=+144px
#     [LOW_ALT_OPEN_LOOP_DESCENT] goruntu 1.59m'de kayboldu
# yani kapali cevrim hizalama 1.2 m'de hic calismiyordu.
#
# Altigen/ucgen icin olculmus 2.0 m DEGISMEDI; yalnizca kucuk yuk
# dikdortgenleri kendi esigini aliyor.
LOW_ALT_VISION_LIMIT_BY_SHAPE: dict = {
    "KIRMIZI_DIKDORTGEN": 0.5,
    "MAVI_DIKDORTGEN": 0.5,
}


def low_alt_vision_limit(shape_type: str) -> float:
    """Sekle gore gorus gati esigi; tanimsizsa genel LOW_ALT_VISION_LIMIT_M."""
    return LOW_ALT_VISION_LIMIT_BY_SHAPE.get(shape_type, LOW_ALT_VISION_LIMIT_M)
# Below LOW_ALT_VISION_LIMIT_M the controller centres on the BOUNDING-BOX
# centre instead of the contour-moment centre. Measured divergence between
# the two grows with apparent size -- 3.51 px mean at 15 m to 77.99 px
# (max 163.5) at 0.45 m, where the shape spans 814 px of a 1280 px frame.
# The moment centre is the one that destabilises, because a clipped blob's
# moments are computed over the VISIBLE part only.
LOW_ALT_BBOX_CENTER: bool = True
# Release-altitude acceptance band (operator spec: 0.45 +/- 0.05 m).
PAYLOAD_RELEASE_ALTITUDE_TOLERANCE_M: float = 0.05
# Open-loop descent gives up if it cannot reach the release altitude in
# this long -- it must never become an unbounded descent.
LOW_ALT_OPEN_LOOP_TIMEOUT_S: float = 20.0
# Minimum commanded descent rate while the open-loop descent is outside the
# release band. Pure proportional control asymptotes: with kp_altitude=0.5
# and a 0.05 m band, alt_error=0.10 m asks for 0.05 m/s and the last stretch
# crawls past the timeout. Same reasoning as the ADR-009 S1 lateral floor,
# scoped to this method only -- the staged-approach descent is unchanged.
LOW_ALT_OPEN_LOOP_MIN_DESCENT_M_S: float = 0.12
# W4.3: how long after the servo to sample the released payload's pose.
# 2 s is enough for a body released at 0.45 m to fall and settle, and short
# enough that the mission is still parked over the target when it is read.
PAYLOAD_FINAL_POSE_DELAY_S: float = 2.0
# W4.4: how long the camera overlay keeps showing the RELEASED tag.
RELEASED_OVERLAY_DURATION_S: float = 3.0

# --- F2 (2026-08-17): confirmed release ---
# The first ADR-011 flight released payload 2 and climbed away while it was
# STILL ATTACHED (measured: 2 s after the servo it was at z=0.523, exactly
# base_link minus the 0.18 m mount offset). It separated somewhere during the
# climb-out and landed 4.9 m past the triangle, and every operator channel
# reported a clean RELEASED. A release is therefore no longer believed until
# the body is SEEN to leave the vehicle.
#
# The burst exists because gz-transport is a slow joiner: each `gz topic -p`
# is a fresh short-lived process that advertises and publishes in the same
# breath, so the DetachableJoint plugin can still be connecting when the one
# and only message goes out. Five sends over 0.25 s cost nothing and close
# that window. This is a transport workaround, not a physics change.
PAYLOAD_DETACH_BURST_COUNT: int = 5
PAYLOAD_DETACH_BURST_INTERVAL_S: float = 0.05
# Separation is judged on VEHICLE-RELATIVE drop, so a climbing drone can
# never be mistaken for a falling payload. 0.05 m is ~7x the pose noise of a
# hovering vehicle and is reached ~0.1 s into free fall.
PAYLOAD_DETACH_SEPARATION_M: float = 0.05
# Measured from the SERVO COMMAND, not from the start of polling, so it has
# to cover the transport as well as the physics: a fresh `gz topic -p`
# process costs 0.91 s +-0.005 (n=5, measured 2026-08-17) between launch and
# delivery, and free fall then needs ~0.1 s to clear the separation
# threshold. 2.0 s leaves roughly 1 s of headroom over that.
PAYLOAD_DETACH_CONFIRM_TIMEOUT_S: float = 2.0
PAYLOAD_DETACH_POLL_INTERVAL_S: float = 0.05
# If the payload is still attached after publish + republish, the vehicle
# HOLDS at release altitude rather than climbing away. Unbounded holding
# would trade one silent failure for another (a drone hovering until the
# battery quits), so the hold has a backstop after which the mission
# continues -- loudly, with the failure recorded, never silently.
PAYLOAD_DETACH_HOLD_MAX_S: float = 60.0

# --- F3 (2026-08-17): "settled ON TARGET", not merely "above ground" ---
# The old check was z > -0.05, which only distinguished "fell through the
# world" from "did not". It passed a payload lying 4.9 m off the triangle.
# Expected rest height is world geometry: the target's collision top sits at
# z=0.006 (include pose 0.003 + collision pose -0.047 + half of 0.1), and the
# prism is 0.05 thick, so a body lying FLAT on the shape rests at 0.031.
PAYLOAD_EXPECTED_REST_Z_M: float = 0.031
# 0.03 m catches a payload standing on edge (which rests at 0.156, half its
# 0.30 m long side above the surface) as well as one that never landed.
PAYLOAD_ON_TARGET_Z_TOLERANCE_M: float = 0.03
# YEDEK DEGER (E3 takibi, 2026-09-03). Artik BIRINCIL esik degil: gz arka
# ucu her sekil icin yaricapi SDF geometrisinden turetiyor
# (gz_payload_actuator.read_on_target_radius_m), cunku tek bir sayi iki
# hedef sekle birden uyamiyor -- olculdu:
#     blue_hexagon  ic teget 0.866 m -> esik 0.716 m (yuk yaricapi 0.15 dusuldu)
#     red_triangle  ic teget 0.289 m -> esik 0.139 m
# 0.5 m boylece UCGEN icin fazla gevsekti (0.5 m'de yuk ucgenin disinda kalir)
# ve ALTIGEN icin gereksiz dardi. Bu deger yalnizca geometriyi veremeyen bir
# arka uc icin kalir -- gercek donanimda SDF yoktur, orada davranis degismez.
# Buyutulmemesi bilincli: 2026-09-03 olcumunde isabet dagilimi iki kutupluydu
# (yakinsayan bacaklar <=0.885 m, suresi dolanlar >=2.121 m); esigi buyutmek
# yalnizca 2-5 m'lik iskalari "basarili" yazdirir, hicbir seyi duzeltmez.
PAYLOAD_ON_TARGET_RADIUS_M: float = 0.5

# --- A2 (2026-08-17): payload-centred aim ---
# Where each payload hangs in the BODY frame, as (forward_m, right_m). The
# mission centres the CAMERA on the target, so a payload mounted to one side
# lands to that side: measured across two nominal flights, all four drops
# came to rest 33.7-37.3 cm from the target centre, clustered around the
# 0.28 m mount offset rather than scattered. That error was always present;
# it only became visible once ADR-011 stopped the payload falling through
# the world, and it now dominates every other term in the release offset.
#
# The fix is to aim the PAYLOAD rather than the camera: on the final
# approach step the target is driven to the payload's position in frame
# instead of to the frame centre. This is a change to the setpoint TARGET
# only -- the P-law, the gains and the tolerances are untouched.
#
# FRAME, and it is not the one the SDF is written in. SDF/Gazebo body axes
# are FLU (X forward, Y **LEFT**); PX4 -- and set_velocity_body, and this
# constant -- are FRD (X forward, Y **RIGHT**). The world SDF mounts
# payload_red at y = -0.28 and payload_blue at y = +0.28, which is red on
# the RIGHT and blue on the LEFT, so the signs here are the SDF's negated.
#
# Taking the SDF's y straight across cost a flight: A2 first flew with red
# at right = -0.28, which steered the vehicle the wrong way and doubled the
# error instead of cancelling it -- 0.243 m became 0.850 m, almost exactly
# the predicted 0.243 + 2 x 0.28. Both signs are now confirmed twice over,
# by static geometry and by where four payloads actually came to rest:
# red landed at world X +0.243 / +0.240 and blue at -0.270 / -0.337, and
# world X is PX4 body-right at the mission's heading of ~0.
# How close the vehicle must get to the translated hold point before the
# release is allowed. The goal is a sub-10 cm final offset, so the hold
# itself has to be tighter than that; 5 cm leaves room for the fall.
PAYLOAD_AIM_HOLD_TOLERANCE_M: float = 0.05

# --- T1 (2026-08-17): MOUNT_TRANSLATE is its own phase ---
# Folding the translation into the descent let it eat the descent budget:
# the 0.28 m move is asymptotic with no lateral floor, so the vehicle kept
# sinking while it crawled and the loop exited on its 20 s timeout at
# whatever altitude it had reached -- measured, releases at 0.385 m and
# 0.159 m, both out of band. The translation now holds altitude, runs on its
# own budget, and cannot touch the descent.
# --- E4e (2026-09-03): IRAKSAMA KORUMASI ---
# Olculdu (7 pencere, 15 ardisik-artis serisi; MOUNT_TRANSLATE_TICK.residual_m
# ve ayni niceligi tasiyan LOW_ALT_OPEN_LOOP_STEP.hold_error_m):
#   seri uzunlugu dagilimi: 1x8, 2x2, 3x3, 9x1, 12x1
#   YAKINSAYAN pencerelerde gorulen en uzun seri: 1  (>=5 olan: 0/3)
#   IRAKSAYAN pencerede: 12 ve 9
# 3 ile 9 arasinda HIC seri yok; 5 bu bosluga dusuyor ve 4-8 arasi her deger
# bu veride ayni siniflandirmayi yapar. Saglikli en kotunun 5 kati, yakalanmasi
# gereken en kisa kotu serinin (9) 4 tick oncesinde ateslenir. 10 Hz'de 0.5 s.
# ORNEKLEM KUCUK (7 pencere, yalnizca 3'u yakinsayan) -- bu yuzden parametre.
MOUNT_TRANSLATE_DIVERGE_TICKS: int = 5
# Milimetrik gurultunun sayaci tetiklememesi icin olu bant.
MOUNT_TRANSLATE_DIVERGE_EPS_M: float = 0.001

# E4e Guard 2 IKINCIL kapisi. BIRINCIL kapi yakinsamadir; bu yalnizca kaba
# hareketi yakalar ve KESTIRIM ARIZASINA KORDUR: run4'te birakma aninda EKF
# 0.05 m/s bildiriyordu, gercek 3.00 m/s idi. Deger, saglikli birakmalarin en
# kotusunun (0.206 m/s) 2.4 kati -- yanlis tetiklemez.
PAYLOAD_RELEASE_MAX_GROUND_SPEED_M_S: float = 0.5

# Guard tetiklenince tirmanilacak irtifa. LOW_ALT_VISION_LIMIT_M = 2.0'in
# UZERINDE olmasi sart: tirmanmanin amaci gorusu geri kazanmak ve kestirimin
# en kotu oldugu guverte bolgesinden cikmak. PAYLOAD_APPROACH_ALTITUDES_M'in
# ortadaki adimiyla ayni deger secildi (yeni bir rejim icat etmemek icin).
PAYLOAD_RELEASE_RETRY_ALTITUDE_M: float = 5.0

MOUNT_TRANSLATE_BUDGET_S: float = 8.0
MOUNT_TRANSLATE_TOLERANCE_M: float = 0.05

# --- T2 (2026-08-17): the camera is not at the body origin ---
# x500_mono_cam_down/model.sdf mounts mono_cam at <pose>0.35 0 .05</pose>,
# i.e. 0.35 m FORWARD of base_link. _freeze_target_estimate back-projects
# the pixel offset -- which is measured from the CAMERA -- and added it to
# the VEHICLE's GPS, so every frozen estimate landed 0.35 m aft of the real
# target. Predicted landing error 0.35 - 0.10 (the final nudge) = 0.25 m
# south; measured across four flights: 0.252, 0.264, 0.290, 0.305 m south.
# (forward_m, right_m) in the PX4 body frame, same convention as the mount.
# 2026-08-21: kamera yuklerin bir ucuna alindi (model.sdf mono_cam
# pose x=+0.085); eski 0.35 govde ucundaydi.
CAMERA_LEVER_ARM_BODY_M: tuple = (0.085, 0.0)

PAYLOAD_MOUNT_OFFSET_BODY_M: dict = {
    # 2026-08-21: yukler artik yandan degil DRONE'UN ALTINDA, aralarinda
    # 2 cm boslukla (dunya SDF: y = -+0.035). Sistematik dusme hatasi
    # 0.28 m'den 0.035 m'ye iniyor.
    "MAVI_ALTIGEN": (0.0, 0.035),    # red payload, mounted RIGHT
    "KIRMIZI_UCGEN": (0.0, -0.035),  # blue payload, mounted LEFT
}

# --- ADR-010 P4: setpoint-stage smoothing (NOT a control-law change) ---
# MEASURED baseline, V1''' (n=1647 CENTERING_STEP setpoints @10 Hz):
#   |dv| per 0.1s tick: mean 0.035, p95 0.150 m/s  -- steady state is smooth
#   BUT 9 ticks changed by >0.5 m/s, up to 2.50 m/s IN ONE TICK (25 m/s2),
#   clustered at 9.99 / 5.24 / 5.00 m -- i.e. the first tick of each new
#   descent step, where the command jumps from the previous call's terminal
#   zero straight to max.
#   Actual (ULog vehicle_local_position, offboard windows only):
#   horiz accel mean 0.63, p95 5.08, p99 7.85, max 9.65 m/s2.
#
# So the problem is the STEP CHANGE at call/Offboard entry, not the gains.
# Both limits below are applied to the final setpoint only; the P-law and
# every gain/tolerance/floor above are untouched.
#
# Max change in commanded velocity per OFFBOARD_SETPOINT_INTERVAL_S tick.
# TIGHTENED 0.30 -> 0.15 m/s per 0.1s tick (3.0 -> 1.5 m/s2 commanded):
# gorev3_pickup hook-seating runs (2026-08-29) repeatedly failed the tilt
# gate (hook_seating.SEAT_MAX_TILT_RAD, 15 deg) while the vehicle was still
# making rate-limited-but-real lateral corrections during approach -- the
# rope-hung hook has no damping of its own, so even a "smooth" 3.0 m/s2
# commanded step is enough to set it swinging past the seating tolerance.
# Halving the rate limit does not touch the P-law, any gain, tolerance or
# floor (see the ADR-010 note above) -- only how fast the already-computed
# command is allowed to change tick-to-tick. Still comfortably above the
# floor Phase 12 needed (worst-case single-tick jump now ramps over ~1.6s
# instead of ~0.8s; convergence tau cost is expected to grow, not eliminated
# by this change alone -- re-measure before tightening further).
SETPOINT_MAX_DELTA_V_M_S: float = 0.15
# PHASE 12 Q1: the distance-scaled speed cap that used to live here
# (SETPOINT_SPEED_PER_DISTANCE / SETPOINT_MIN_VMAX_M_S) is REMOVED. It
# compounded with proportional control in exactly the regime where the
# convergence tail is longest -- at d = 0.3 m it clamped the command to
# 0.3 m/s on top of a P-law already shrinking it -- and cost tau 9.1 ->
# 13.2 s (+44.9%) on the pursuits common to V1''' and V1'''', against a
# +20% budget. The rate limit alone had already delivered the whole
# smoothness gain (accelerating ticks > 0.5 m/s: 7 -> 0). See ADR-010.
#
# How many consecutive frames the target may be missing before the
# controller commands a hard zero. Below this it decelerates under the
# normal rate limit instead. V1'''' hard-braked from ~1.3 m/s to zero four
# times, each on a SINGLE-frame dropout, then had to re-accelerate from
# standstill when the target reappeared the next frame. 10 frames = 1.0 s at
# OFFBOARD_SETPOINT_INTERVAL_S, and 10 ticks x 0.15 m/s of decel authority
# reaches zero from 1.5 m/s anyway -- so the count is a backstop, not the
# primary mechanism.
#
# DOUBLED 5 -> 10 alongside SETPOINT_MAX_DELTA_V_M_S's 0.30 -> 0.15 halving
# (2026-08-29), to hold decel authority constant (5*0.30 == 10*0.15 == 1.5
# m/s): halving the rate limit without widening this window would have left
# a real hard-zero at frame 5 while the vehicle was still well above zero,
# i.e. exactly the sharp stop this whole mechanism exists to avoid.
TARGET_LOSS_GRACE_FRAMES: int = 10

# --- HSVContourDetector interim fallback (core/detection/hsv_contour_detector.py) ---
# Classical HSV-threshold + contour-shape tuning, ported unchanged from the
# proven-working v29 monolith (.scripts/v29.py / .scripts/olds/v34/vision_backends.py
# HSVContourDetectorBackend, marked there "LEGACY, TO BE DEPRECATED" but never
# actually replaced by a working ML detector). This is a real, functioning
# non-ML IDetector for MAVI_ALTIGEN/KIRMIZI_UCGEN only (no verification-marker
# rectangle detection) -- usable today as an interim/testing detector while
# yolo_detector.py waits for a real trained YOLO26 model (see its own
# footgun-guard warning for why the stock yolov8n.pt is not a substitute).
HSV_RED_LO_1: tuple[int, int, int] = (0, 40, 40)
HSV_RED_HI_1: tuple[int, int, int] = (15, 255, 255)
HSV_RED_LO_2: tuple[int, int, int] = (165, 40, 40)
HSV_RED_HI_2: tuple[int, int, int] = (180, 255, 255)
HSV_BLUE_LO: tuple[int, int, int] = (90, 80, 40)
HSV_BLUE_HI: tuple[int, int, int] = (140, 255, 255)
HSV_MIN_AREA_TRI_BASE: float = 390
HSV_MIN_AREA_HEX_BASE: float = 800
HSV_EPS_TRI_MIN: float = 0.03
HSV_EPS_TRI_MAX: float = 0.09
HSV_EPS_HEX: float = 0.026
HSV_COLOR_FRAC_TRI_BASE: float = 0.35
HSV_COLOR_FRAC_HEX: float = 0.45
HSV_STREAK_FRAMES: int = 3
HSV_STREAK_DIST_PX: float = 60

# --- HSVContourDetector rectangle detection (Görev 3, operatör revizyonu
# 2026-08-13) -- KIRMIZI_DIKDORTGEN / MAVI_DIKDORTGEN. Unlike the triangle/
# hexagon constants above (ported, proven values from v29), no prior
# working rectangle detector exists anywhere in this codebase's history --
# these are new, untuned defaults (same order of magnitude as the ported
# triangle/hexagon constants) and will need real-camera calibration before
# competition use, same caveat as every HSV_* constant in this file.
HSV_MIN_AREA_RECT_BASE: float = 400
HSV_EPS_RECT_MIN: float = 0.02
HSV_EPS_RECT_MAX: float = 0.06
HSV_COLOR_FRAC_RECT: float = 0.40

# D2c follow-up (2026-08-21): how much of a committed triangle/hexagon a
# rectangle must cover before it is treated as that same contour re-read
# through the rectangle gate, rather than a separate object lying on top of
# it. The duplicate case is ONE contour passing two gates, so the two bboxes
# ARE the same bbox -- median 512 px2 in both sets over the 1741-frame
# 2026-08-17 sample (tests/test_d2c_one_contour_one_class.py). A payload
# resting on a target is a genuinely different, far smaller object:
# blue_hexagon spans 5.00 m against the payload cylinder's 0.30 m, ~280x in
# area. Anything in the wide gap between those two regimes works; 0.50 sits
# in the middle with ~2x margin on the duplicate side and ~140x on the
# payload side.
HSV_RECT_DUPLICATE_AREA_RATIO: float = 0.50

# --- MOTION FSM: Climb-then-Cruise (2026-09-02) ------------------------------
# Dikey ve yatay hareketi ZAMANDA ayiran hareket makinesinin esikleri.
# Tamami gz_system.yaml / real_system.yaml icindeki `motion_profile` blogundan
# EZILEBILIR -- control_gains ile ayni desen (main_gz.py, main_real.py,
# main_dual.py). Buradaki degerler yalnizca varsayilandir.
#
# SITL ile HW'nin AYRI profil tasimasi kasitlidir: gercek telemetri linkinde
# gecikme, gercek IMU/GPS'te gurultu var. Simulasyonda dogrulanmis dar bir
# esik gercek ucusta state'in HIC gecmemesine yol acabilir (bkz.
# docs/flight-control-analysis.md 2.4).

#: Makine kapatilirsa cagiranlar eski goto_global_position_and_wait()
#: davranisina duser. Geri donus yolu bir kod degisikligi gerektirmesin diye var.
MOTION_FSM_ENABLED: bool = True

#: CLIMB/DESCEND yakinsama bandi. ALTITUDE_CONVERGENCE_TOLERANCE_M ile ayni
#: deger, ama AYRI bir sabit: o tolerans go_to_and_center ve climb_to_altitude
#: tarafindan paylasiliyor ve ADR-010'da olculmus; hareket makinesi icin
#: ayarlanmasi gerekirse onlari birlikte suruklememeli.
MOTION_ALT_TOL_M: float = 0.30

#: CLIMB/DESCEND cikis guard'inin IKINCI yarisi. climb_to_altitude()'un
#: mevcut guard'i yalnizca |alt_error| bakiyordu; band icine HIZLA girip
#: asmak "yakinsadi" sayiliyordu. Ayni sinif hata goto_global_position_and_
#: wait()'te 2026-08-13'te olculmustu (arac hedefin 2 m yaricapindan ~11 m/s
#: ile geciyordu) ve orada hiz kosulu eklenerek cozulmustu; ayni cozum burada.
MOTION_VZ_SETTLE_M_S: float = 0.20

#: HOLD'un ALT siniri. 0.30 -> 2.0 (operator karari 2026-09-02, Blok 6).
#:
#: TALEP "sabit ~2 s hold yeterli" idi; UYGULAMA "EN AZ 2 s VE STABIL". Guard
#: KALDIRILMADI, saf sleep'e cevrilmedi: cikis hala min sure DOLDU **VE**
#: roll/pitch turevi esik altinda MOTION_ATTITUDE_STABLE_SAMPLES ardisik
#: ornek kaldi kosuluna bagli. Yani 2 s bir TABAN, bir hedef degil --
#: 2 s sonunda arac hala sallaniyorsa makine beklemeye devam eder.
#:
#: Neden 2 s'lik bir taban anlamli: eski 0.30 s, attitude guard'inin ilk
#: orneklerini almaya bile zor yetiyordu (10 Hz'de 3 ornek = 0.3 s), yani
#: pratikte cikisi neredeyse hep guard degil sayac belirliyordu. 2 s'de guard
#: gercekten olcum yapabiliyor.
MOTION_HOLD_MIN_S: float = 2.0
#: HOLD'un UST siniri. Attitude hic durulmazsa (ruzgar, salinim) makine
#: sonsuza kadar beklemez -- gorev butcesi 600 s ve HOLD onu yiyemez.
#: Asildiginda WARN ile CRUISE'a gecilir, gorev dusurulmez.
#:
#: 3.0 -> 4.0 (2026-09-02): taban 2 s'ye ciktigi icin eski tavan guard'a
#: yalnizca 1 s hareket alani birakiyordu. Tavan tabana bu kadar yakin
#: oldugunda guard fiilen devre disi kalir (her sallanan aracta hemen
#: tavana carpar). 4.0, tabandan sonra 2 s'lik gercek bir durulma penceresi
#: birakir.
MOTION_HOLD_MAX_S: float = 4.0

#: Attitude stabilite guard'i: roll ve pitch'in SAYISAL TUREVI bu esigin
#: altinda MOTION_ATTITUDE_STABLE_SAMPLES ardisik ornek boyunca kalmali.
#:
#: NEDEN VARYANS DEGIL RATE: tasarim notu "attitude rate varyansi" diyordu.
#: 10 Hz'de 3 ornekli bir pencerenin varyansi gurultu baskin ve yorumlanmasi
#: zor bir sayidir; maksimum |rate| hem daha siki bir sinir hem de dogrudan
#: fiziksel bir buyukluk (deg/s). Esik asildiginda ne kadar asildigi loglanir.
MOTION_ATTITUDE_RATE_LIMIT_DEG_S: float = 15.0
MOTION_ATTITUDE_STABLE_SAMPLES: int = 3

#: CRUISE varis yaricapi. GPS_POSITION_CONVERGENCE_TOLERANCE_M ile ayni deger;
#: ayri sabit olmasinin gerekcesi MOTION_ALT_TOL_M ile ayni.
MOTION_ARRIVAL_RADIUS_M: float = 2.0
#: CRUISE cikis guard'inin IKINCI yarisi -- yaricap TEK BASINA yetmez.
#: goto_global_position_and_wait()'te tam bu eksiklik 2026-08-13'te olculmustu:
#: konum kosulu arac hedefin 2 m yaricapindan ~11 m/s ile GECERKEN atesleniyor
#: ve arac 10-25 m otesine suzuluyordu. Deger GPS_POSITION_VELOCITY_TOLERANCE_M_S
#: ile ayni; profil zaten hedefte sifira inecek sekilde frenledigi icin bu
#: kosul normalde profille birlikte saglanir, tek basina bir gecikme yaratmaz.
MOTION_ARRIVAL_SPEED_M_S: float = 0.30

#: Trapez profilin seyir tavani ve ivme rampasi (velocity_profile.py).
#: MOTION_ACCEL_M_S2 varsayilani SETPOINT_MAX_DELTA_V_M_S / OFFBOARD_SETPOINT_
#: INTERVAL_S = 0.15/0.1 = 1.5 m/s2 ile AYNI secildi: profil, ardindan gelen
#: SetpointLimiter'in zaten uygulayacagi ivme tavaniyla catismasin, onu
#: ONCEDEN bilerek uygulasin. Buradan buyuk bir deger vermek profili degil
#: yalnizca limiter'i calistirir.
MOTION_CRUISE_SPEED_M_S: float = 3.0
MOTION_ACCEL_M_S2: float = 1.5
#: Dikey bacaklarin tavani. MAX_CENTERING_SPEED_M_S'ten dusuk tutuldu: dikey
#: asim irtifa bandindan tasar ve VZ_SETTLE guard'ini geciktirir.
MOTION_VERTICAL_SPEED_M_S: float = 1.5

#: Tek bir bacagin (bes state'in tamami) ust siniri. GLOBAL_POSITION_NAV_
#: TIMEOUT_S ile ayni: bu makine onun yerine geciyor, butcesini buyutmuyor.
MOTION_LEG_TIMEOUT_S: float = 60.0
#: Tek bir dikey state'in ust siniri (climb_to_altitude'un kendi 20 s'i ile ayni).
MOTION_VERTICAL_TIMEOUT_S: float = 20.0
#: ARRIVAL_HOLD suresi -- varista yatay artik hizin inise/merkezlemeye
#: tasinmamasi icin. master_fsm.py'nin donus bacaginda zaten uygulanan
#: RETURN_TO_START_FINISH_HOLD_S ile ayni gerekce.
MOTION_ARRIVAL_HOLD_S: float = 1.0

# --- Payload birakma penceresi pozisyon kilidi (Gorev C, 2026-09-03) --------
#: Servo cagrisi boyunca konumu tutan arka plan gorevinin UST siniri.
#:
#: NEDEN VAR (olculdu, 4 birakma, PX4 ULog): birakma dizisi
#: (irtifa okuma -> mount vektoru -> servo -> ayrilma onayi) 1.13-1.31 s
#: suruyor ve o pencerede AKTIF POZISYON KILIDI YOK. nudge_forward bitiste
#: sifir HIZ gonderiyor, ama sifir hiz konumu geri GETIRMEZ -- yalnizca
#: sonumler. Pencereye artik hizla girilirse o hiz boyunca alinan yol kalici
#: oluyor: giris hizi 0.09-0.14 m/s olan uc birakmada sapma 0.05-0.16 m,
#: 0.52 m/s ile girilen dorduncude 2.225 m (43 kat).
#:
#: Ayrilmanin KENDISI tetikleyici degil: dordunun de kutlesi, mekanizmasi ve
#: irtifasi ayni; nav_state dort pencerede de sabit 14 (OFFBOARD) kaldi.
#:
#: Bu bir TAVAN: aktuator dondugu anda gorev iptal ediliyor, yani normalde
#: ~1.2 s kullanilir. Genis birakildi ki yavas bir ayrilma onayi (F2 yolu)
#: kilidi erken dusurmesin.
PAYLOAD_RELEASE_HOLD_MAX_S: float = 8.0
