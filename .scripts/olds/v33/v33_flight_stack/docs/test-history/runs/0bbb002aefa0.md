---
kind: mission_run
machine_generated: true
generator: tools/run_record.py
run_id: 0bbb002aefa0
date: 2026-08-20
started: 2026-08-20T17:40:20Z
ended: 2026-08-20T17:47:49Z
duration_s: 449.3
exit_code: ~
terminal_phase: MISSION_FAILED
event_count: 6198
raw_artifacts:
  - "../logs/mission_0bbb002aefa0.jsonl"
  - "../logs/mission_positions_0bbb002aefa0.json"
  - "../logs/mission_20260820_204020.log"
---

# Koşu kaydı — `0bbb002aefa0`

> Bu dosya `tools/run_record.py` tarafından üretildi. Yalnızca olay
> kaydından **türetilebilen olguları** içerir: ne olduğunu söyler, ne
> anlama geldiğini **söylemez**. Kök neden, amaç, doğrulama ve sonraki
> adım insan yargısıdır ve phase özetine (`docs/test-history/PH-*.md`)
> aittir. Bu kayıt doğrulanmış bir özet **değildir** ve hiçbir ham veriyi
> silinebilir yapmaz.

## Faz zinciri

- `+   1.1s`  `MISSION_INIT` → `CONNECTING`
- `+   3.1s`  `CONNECTING` → `ARMING`
- `+   3.2s`  `ARMING` → `TAKEOFF`
- `+   3.2s`  `TAKEOFF` → `CLIMB_TO_ALTITUDE`  — (target=15.0m)
- `+  21.3s`  `CLIMB_TO_ALTITUDE` → `CHECKPOINT_SAVE`
- `+  21.3s`  `CHECKPOINT_SAVE` → `MISSION_ROUTE_CONFIRM`
- `+  21.3s`  `MISSION_ROUTE_CONFIRM` → `MISSION_START`
- `+  25.4s`  `MISSION_START` → `SEARCHING`
- `+  27.9s`  `SEARCHING` → `TARGET_TRACKING`  — (MAVI_ALTIGEN)
- `+  27.9s`  `TARGET_TRACKING` → `SWITCH_TO_OFFBOARD`
- `+  28.3s`  `SWITCH_TO_OFFBOARD` → `GOTO_TARGET_CENTERING`  — (MAVI_ALTIGEN)
- `+  59.0s`  `GOTO_TARGET_CENTERING` → `HOVER_CONFIRM`
- `+  61.1s`  `HOVER_CONFIRM` → `GPS_SAVE`
- `+  61.1s`  `GPS_SAVE` → `SEARCHING`  — (single_target_recorded_resuming_route)
- `+  66.3s`  `SEARCHING` → `TARGET_TRACKING`  — (KIRMIZI_UCGEN)
- `+  66.3s`  `TARGET_TRACKING` → `SWITCH_TO_OFFBOARD`
- `+  69.4s`  `SWITCH_TO_OFFBOARD` → `SEARCHING`  — (offboard_switch_failed)
- `+  70.9s`  `SEARCHING` → `TARGET_TRACKING`  — (KIRMIZI_UCGEN)
- `+  70.9s`  `TARGET_TRACKING` → `SWITCH_TO_OFFBOARD`
- `+  73.7s`  `SWITCH_TO_OFFBOARD` → `GOTO_TARGET_CENTERING`  — (KIRMIZI_UCGEN)
- `+  99.0s`  `GOTO_TARGET_CENTERING` → `HOVER_CONFIRM`
- `+ 101.0s`  `HOVER_CONFIRM` → `GPS_SAVE`
- `+ 101.0s`  `GPS_SAVE` → `SEARCH_COMPLETE`
- `+ 317.3s`  `SEARCH_COMPLETE` → `GOREV2_COMPLETE`
- `+ 317.3s`  `GOREV2_COMPLETE` → `GOREV3_START`
- `+ 317.3s`  `GOREV3_START` → `GOREV3_RUNNING`  — (pickup)
- `+ 386.9s`  `GOREV3_RUNNING` → `MISSION_FAILED`  — (gorev3_pickup_failed)
- `+ 386.9s`  `MISSION_FAILED` → `RETURN_TO_CHECKPOINT`  — (gorev3_failed)
- `+ 449.1s`  `RETURN_TO_CHECKPOINT` → `LANDING`  — (gorev3_failed)
- `+ 449.1s`  `LANDING` → `MISSION_FAILED`  — (landed_after_prior_failure)

## Health geçişleri

| +s | alt sistem | durum |
|---|---|---|
| `+2.0` | `MavsdkBackendBase` | **HEALTHY** |
| `+4.0` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+93.4` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+94.4` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+335.2` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+336.2` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+339.2` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+340.2` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+361.3` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+362.3` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+379.4` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+380.4` | `Gorev2Orchestrator.vision` | **HEALTHY** |

## Merkezleme sonuçları

| +s | sonuç | şekil | irtifa (m) |
|---|---|---|---|
| `+46.7` | `CENTERING_TIMED_OUT` | MAVI_ALTIGEN | 15.0 |
| `+55.9` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 15.0 |
| `+95.9` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 15.0 |
| `+167.5` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 10.0 |
| `+190.4` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 5.0 |
| `+283.1` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 10.0 |
| `+291.5` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 5.0 |
| `+301.4` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 0.45 |

## Payload olayları

- `+ 161.2s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 167.5s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 190.4s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 206.5s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 277.5s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 283.1s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 291.5s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 305.9s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN

## WARN ve üzeri olaylar

*Severity'ye göre süzülmüş tek bir liste. Bazı satırlar yukarıdaki*
*tablolarda da görünür (aynı olayın farklı görünümü, ek olay değil).*

- `+1.1s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=WAITING_MAVSDK_CONNECTION kind=BLOCKING_WAIT
- `+3.2s` **WARN** `BLOCKING_STATE_ENTERED` (Gorev2Orchestrator): waiting_on=WAITING_ALTITUDE_REACHED kind=BLOCKING_WAIT
- `+21.3s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=WAITING_EXISTING_MISSION kind=BLOCKING_WAIT
- `+21.3s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=STARTING_UPLOADED_MISSION kind=BLOCKING_WAIT
- `+28.3s` **WARN** `BLOCKING_STATE_ENTERED` (CenteringController): waiting_on=WAITING_CENTERING_CONVERGENCE kind=BLOCKING_WAIT
- `+46.7s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): MAVI_ALTIGEN
- `+46.7s` **WARN** `RETRY_IN_PLACE` (Gorev2Orchestrator): MAVI_ALTIGEN 1/3
- `+69.4s` **CRITICAL** `OFFBOARD_SWITCH_FAILED` (CenteringController): PX4 did not report OFFBOARD before timeout
- `+73.7s` **WARN** `BLOCKING_STATE_ENTERED` (CenteringController): waiting_on=WAITING_CENTERING_CONVERGENCE kind=BLOCKING_WAIT
- `+93.4s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+161.2s` **WARN** `GLOBAL_POSITION_NAV_TIMED_OUT` (CenteringController): 
- `+196.6s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): MAVI_ALTIGEN
- `+202.8s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): MAVI_ALTIGEN
- `+277.5s` **WARN** `GLOBAL_POSITION_NAV_TIMED_OUT` (CenteringController): 
- `+303.8s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): KIRMIZI_UCGEN
- `+304.2s` **WARN** `PAYLOAD_RELEASE_ALTITUDE` (PayloadReleaseService): KIRMIZI_UCGEN
- `+307.9s` **WARN** `PAYLOAD_VERIFICATION_RESULT` (PayloadReleaseService): expected=MAVI_DIKDORTGEN found=False
- `+335.2s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+339.2s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+361.3s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+377.4s` **WARN** `GLOBAL_POSITION_NAV_TIMED_OUT` (CenteringController): 
- `+379.4s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+386.9s` **CRITICAL** `MISSION_PHASE_CHANGED` (MissionContext): GOREV3_RUNNING -> MISSION_FAILED (gorev3_pickup_failed)
- `+386.9s` **CRITICAL** `GOREV3_PHASE_FAILED` (Gorev3Orchestrator): pickup
- `+386.9s` **WARN** `BLOCKING_STATE_ENTERED` (MasterMissionController): waiting_on=RETURNING_TO_START_FINISH kind=BLOCKING_WAIT
- `+447.0s` **WARN** `GLOBAL_POSITION_NAV_TIMED_OUT` (CenteringController): 
- `+449.1s` **WARN** `RETURN_TO_START_FINISH_TIMED_OUT` (MasterMissionController): dist=0.1 m
- `+449.1s` **CRITICAL** `MISSION_PHASE_CHANGED` (MissionContext): LANDING -> MISSION_FAILED (landed_after_prior_failure)

## Tespit edilen şekiller (kare sayısı)

- `MAVI_ALTIGEN`: 1803 kare
- `KIRMIZI_UCGEN`: 1101 kare
- `MAVI_DIKDORTGEN`: 549 kare
- `KIRMIZI_DIKDORTGEN`: 25 kare

## Olay sayımları

| kod | adet |
|---|---|
| `VISION_FRAME_PROCESSED` | 3777 |
| `CENTERING_STEP` | 888 |
| `VEHICLE_TELEMETRY` | 804 |
| `WATCHDOG_UPDATED` | 448 |
| `LOW_ALT_OPEN_LOOP_STEP` | 46 |
| `TELEMETRY_STREAM_RATES` | 44 |
| `MISSION_PHASE_CHANGED` | 30 |
| `HEALTH_STATE_CHANGED` | 12 |
| `TRACK_STATE_UPDATED` | 11 |
| `CENTERING_STARTED` | 9 |
| `PAYLOAD_STATE` | 8 |
| `BLOCKING_STATE_ENTERED` | 7 |
| `BLOCKING_STATE_CLEARED` | 7 |
| `CENTERING_CONVERGED` | 7 |
| `GLOBAL_POSITION_NAV_STARTED` | 4 |
| `GLOBAL_POSITION_NAV_TIMED_OUT` | 4 |
| `MISSION_STARTED_ONBOARD` | 3 |
| `TARGET_SELECTED` | 3 |
| `MISSION_AUTHORITY_RELEASED` | 3 |
| `LOW_ALT_OPEN_LOOP_DESCENT` | 3 |
| `LOW_ALT_OPEN_LOOP_DESCENT_DONE` | 3 |
| `MISSION_STARTED` | 2 |
| `OFFBOARD_SWITCH_CONFIRMED` | 2 |
| `OFFBOARD_AUTHORITY_ACQUIRED` | 2 |
| `POST_LOCK_DRIFT` | 2 |
| `HOVER_STARTED` | 2 |
| `HOVER_CONFIRMED` | 2 |
| `GPS_SAVE_CONFIRMED` | 2 |
| `TARGET_CONFIRMED` | 2 |
| `MISSION_CURRENT_ITEM_SET` | 2 |
| `MISSION_ROUTE_RESUMED` | 2 |
| `PAYLOAD_RELEASE_REQUESTED` | 2 |
| `AIM_OFFSET_APPLIED` | 2 |
| `MOUNT_TRANSLATE_DONE` | 2 |
| `NUDGE_FORWARD_STARTED` | 2 |
| `NUDGE_FORWARD_DONE` | 2 |
| `PAYLOAD_RELEASE_OFFSET` | 2 |
| `PAYLOAD_RELEASE_ALTITUDE` | 2 |
| `MOUNT_VECTOR_MEASURED` | 2 |
| `PAYLOAD_RELEASE_CONFIRMED` | 2 |
| `PAYLOAD_RELEASED` | 2 |
| `PAYLOAD_FINAL_POSE` | 2 |
| `PAYLOAD_VERIFICATION_RESULT` | 2 |
| `CLIMB_STARTED` | 2 |
| `CLIMB_DONE` | 2 |
| `GOREV_V3_SUCCESS` | 2 |
| `WATCHDOG_ARMED` | 1 |
| `CONNECTED` | 1 |
| `ARMED` | 1 |
| `TAKEOFF_ISSUED` | 1 |
| `ALTITUDE_REACHED` | 1 |
| `CHECKPOINT_SAVED` | 1 |
| `MISSION_ROUTE_CONFIRMED` | 1 |
| `MISSION_PROGRESS` | 1 |
| `CENTERING_TIMED_OUT` | 1 |
| `RETRY_IN_PLACE` | 1 |
| `OFFBOARD_SWITCH_FAILED` | 1 |
| `SEARCH_COMPLETE` | 1 |
| `SEARCH_WAYPOINTS_CANCELLED` | 1 |
| `PAYLOAD_MISSION_1_STARTED` | 1 |
| `PAYLOAD_1_RELEASED` | 1 |
| `PAYLOAD_MISSION_1_COMPLETE` | 1 |
| `PAYLOAD_MISSION_2_STARTED` | 1 |
| `PAYLOAD_2_RELEASED` | 1 |
| `PAYLOAD_MISSION_2_COMPLETE` | 1 |
| `PAYLOAD_STATE_SYNC` | 1 |
| `GOREV2_COMPLETE` | 1 |
| `GOREV3_HOOK_INVOKED` | 1 |
| `GOREV3_PHASE_STARTED` | 1 |
| `GOREV3_PHASE_FAILED` | 1 |
| `RETURNING_TO_START_FINISH` | 1 |
| `RETURN_TO_START_FINISH_TIMED_OUT` | 1 |
| `WATCHDOG_DISARMED` | 1 |
