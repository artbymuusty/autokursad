---
kind: mission_run
machine_generated: true
generator: tools/run_record.py
run_id: fa00e5c5bfc5
date: 2026-08-26
started: 2026-08-26T18:17:06Z
ended: 2026-08-26T18:21:48Z
duration_s: 282.5
exit_code: 0
terminal_phase: MISSION_FAILED
event_count: 4599
raw_artifacts:
  - "../logs/mission_fa00e5c5bfc5.jsonl"
  - "../logs/mission_positions_fa00e5c5bfc5.json"
  - "../logs/mission_20260826_211706.log"
---

# Koşu kaydı — `fa00e5c5bfc5`

> Bu dosya `tools/run_record.py` tarafından üretildi. Yalnızca olay
> kaydından **türetilebilen olguları** içerir: ne olduğunu söyler, ne
> anlama geldiğini **söylemez**. Kök neden, amaç, doğrulama ve sonraki
> adım insan yargısıdır ve phase özetine (`docs/test-history/PH-*.md`)
> aittir. Bu kayıt doğrulanmış bir özet **değildir** ve hiçbir ham veriyi
> silinebilir yapmaz.

## Faz zinciri

- `+   5.8s`  `MISSION_INIT` → `CONNECTING`
- `+   7.6s`  `CONNECTING` → `ARMING`
- `+   7.6s`  `ARMING` → `TAKEOFF`
- `+   7.7s`  `TAKEOFF` → `CLIMB_TO_ALTITUDE`  — (target=15.0m)
- `+  26.8s`  `CLIMB_TO_ALTITUDE` → `CHECKPOINT_SAVE`
- `+  26.8s`  `CHECKPOINT_SAVE` → `MISSION_ROUTE_CONFIRM`
- `+  26.8s`  `MISSION_ROUTE_CONFIRM` → `MISSION_START`
- `+  30.3s`  `MISSION_START` → `SEARCHING`
- `+  33.2s`  `SEARCHING` → `TARGET_TRACKING`  — (MAVI_ALTIGEN)
- `+  33.2s`  `TARGET_TRACKING` → `SWITCH_TO_OFFBOARD`
- `+  34.2s`  `SWITCH_TO_OFFBOARD` → `GOTO_TARGET_CENTERING`  — (MAVI_ALTIGEN)
- `+  66.4s`  `GOTO_TARGET_CENTERING` → `HOVER_CONFIRM`
- `+  68.5s`  `HOVER_CONFIRM` → `GPS_SAVE`
- `+ 115.1s`  `GPS_SAVE` → `SEARCHING`  — (single_target_processed_resuming_route)
- `+ 120.4s`  `SEARCHING` → `TARGET_TRACKING`  — (KIRMIZI_UCGEN)
- `+ 120.4s`  `TARGET_TRACKING` → `SWITCH_TO_OFFBOARD`
- `+ 120.8s`  `SWITCH_TO_OFFBOARD` → `GOTO_TARGET_CENTERING`  — (KIRMIZI_UCGEN)
- `+ 154.4s`  `GOTO_TARGET_CENTERING` → `HOVER_CONFIRM`
- `+ 156.5s`  `HOVER_CONFIRM` → `GPS_SAVE`
- `+ 237.9s`  `GPS_SAVE` → `SEARCH_COMPLETE`
- `+ 238.0s`  `SEARCH_COMPLETE` → `GOREV2_COMPLETE`
- `+ 238.0s`  `GOREV2_COMPLETE` → `GOREV3_START`
- `+ 238.0s`  `GOREV3_START` → `GOREV3_RUNNING`  — (pickup)
- `+ 272.7s`  `GOREV3_RUNNING` → `MISSION_FAILED`  — (gorev3_pickup_failed)
- `+ 272.7s`  `MISSION_FAILED` → `RETURN_TO_CHECKPOINT`  — (gorev3_failed)
- `+ 282.4s`  `RETURN_TO_CHECKPOINT` → `LANDING`  — (gorev3_failed)
- `+ 282.4s`  `LANDING` → `MISSION_FAILED`  — (landed_after_prior_failure)

## Health geçişleri

| +s | alt sistem | durum |
|---|---|---|
| `+6.0` | `MavsdkBackendBase` | **HEALTHY** |
| `+6.0` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+131.5` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+132.5` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+168.6` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+169.6` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+227.4` | `Gorev2Orchestrator.vision` | **STALE** |
| `+228.4` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+230.5` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+231.5` | `Gorev2Orchestrator.vision` | **HEALTHY** |

## Merkezleme sonuçları

| +s | sonuç | şekil | irtifa (m) |
|---|---|---|---|
| `+51.7` | `CENTERING_TIMED_OUT` | MAVI_ALTIGEN | 15.0 |
| `+63.4` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 15.0 |
| `+80.2` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 10.0 |
| `+89.8` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 5.0 |
| `+138.5` | `CENTERING_TIMED_OUT` | KIRMIZI_UCGEN | 15.0 |
| `+151.4` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 15.0 |
| `+163.9` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 10.0 |
| `+170.8` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 5.0 |
| `+195.1` | `CENTERING_TIMED_OUT` | KIRMIZI_UCGEN | 0.45 |
| `+272.7` | `CENTERING_CONVERGED` | KIRMIZI_DIKDORTGEN | 0.3 |

## Payload olayları

- `+  68.5s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+  80.2s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+  89.8s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 104.0s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 156.5s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 163.9s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 170.8s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 220.7s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN

## WARN ve üzeri olaylar

*Severity'ye göre süzülmüş tek bir liste. Bazı satırlar yukarıdaki*
*tablolarda da görünür (aynı olayın farklı görünümü, ek olay değil).*

- `+5.8s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=WAITING_MAVSDK_CONNECTION kind=BLOCKING_WAIT
- `+7.7s` **WARN** `BLOCKING_STATE_ENTERED` (Gorev2Orchestrator): waiting_on=WAITING_ALTITUDE_REACHED kind=BLOCKING_WAIT
- `+26.8s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=WAITING_EXISTING_MISSION kind=BLOCKING_WAIT
- `+26.8s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=STARTING_UPLOADED_MISSION kind=BLOCKING_WAIT
- `+34.2s` **WARN** `BLOCKING_STATE_ENTERED` (CenteringController): waiting_on=WAITING_CENTERING_CONVERGENCE kind=BLOCKING_WAIT
- `+51.7s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): MAVI_ALTIGEN
- `+51.7s` **WARN** `RETRY_IN_PLACE` (Gorev2Orchestrator): MAVI_ALTIGEN 1/3
- `+93.8s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): MAVI_ALTIGEN
- `+100.8s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): MAVI_ALTIGEN
- `+120.8s` **WARN** `BLOCKING_STATE_ENTERED` (CenteringController): waiting_on=WAITING_CENTERING_CONVERGENCE kind=BLOCKING_WAIT
- `+131.5s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+138.5s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): KIRMIZI_UCGEN
- `+138.5s` **WARN** `RETRY_IN_PLACE` (Gorev2Orchestrator): KIRMIZI_UCGEN 1/3
- `+168.6s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+195.1s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): KIRMIZI_UCGEN
- `+203.1s` **WARN** `MOUNT_TRANSLATE_DONE` (CenteringController): KIRMIZI_UCGEN
- `+203.1s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): KIRMIZI_UCGEN
- `+222.7s` **WARN** `PAYLOAD_FINAL_POSE` (PayloadReleaseService): KIRMIZI_UCGEN
- `+222.7s` **WARN** `PAYLOAD_VERIFICATION_RESULT` (PayloadReleaseService): expected=MAVI_DIKDORTGEN found=False
- `+227.4s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> STALE
- `+230.5s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+272.7s` **CRITICAL** `MISSION_PHASE_CHANGED` (MissionContext): GOREV3_RUNNING -> MISSION_FAILED (gorev3_pickup_failed)
- `+272.7s` **CRITICAL** `GOREV3_PHASE_FAILED` (Gorev3Orchestrator): pickup
- `+272.7s` **WARN** `BLOCKING_STATE_ENTERED` (MasterMissionController): waiting_on=RETURNING_TO_START_FINISH kind=BLOCKING_WAIT
- `+282.4s` **CRITICAL** `MISSION_PHASE_CHANGED` (MissionContext): LANDING -> MISSION_FAILED (landed_after_prior_failure)

## Tespit edilen şekiller (kare sayısı)

- `MAVI_ALTIGEN`: 749 kare
- `KIRMIZI_UCGEN`: 602 kare
- `MAVI_DIKDORTGEN`: 351 kare
- `KIRMIZI_DIKDORTGEN`: 296 kare

## Olay sayımları

| kod | adet |
|---|---|
| `VISION_FRAME_PROCESSED` | 2280 |
| `CENTERING_STEP` | 1154 |
| `VEHICLE_TELEMETRY` | 497 |
| `WATCHDOG_UPDATED` | 281 |
| `LOW_ALT_OPEN_LOOP_STEP` | 178 |
| `MISSION_PHASE_CHANGED` | 27 |
| `TELEMETRY_STREAM_RATES` | 27 |
| `CENTERING_STARTED` | 11 |
| `HEALTH_STATE_CHANGED` | 10 |
| `TRACK_STATE_UPDATED` | 10 |
| `PAYLOAD_STATE` | 8 |
| `BLOCKING_STATE_ENTERED` | 7 |
| `BLOCKING_STATE_CLEARED` | 7 |
| `CENTERING_CONVERGED` | 7 |
| `CENTERING_TIMED_OUT` | 3 |
| `LOW_ALT_OPEN_LOOP_DESCENT` | 3 |
| `LOW_ALT_OPEN_LOOP_DESCENT_DONE` | 3 |
| `PAYLOAD_STATE_SYNC` | 3 |
| `MISSION_STARTED` | 2 |
| `MISSION_STARTED_ONBOARD` | 2 |
| `TARGET_SELECTED` | 2 |
| `MISSION_AUTHORITY_RELEASED` | 2 |
| `OFFBOARD_SWITCH_CONFIRMED` | 2 |
| `OFFBOARD_AUTHORITY_ACQUIRED` | 2 |
| `RETRY_IN_PLACE` | 2 |
| `POST_LOCK_DRIFT` | 2 |
| `HOVER_STARTED` | 2 |
| `HOVER_CONFIRMED` | 2 |
| `GPS_SAVE_CONFIRMED` | 2 |
| `TARGET_CONFIRMED` | 2 |
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
| `GLOBAL_POSITION_NAV_STARTED` | 2 |
| `GLOBAL_POSITION_NAV_CONVERGED` | 2 |
| `WATCHDOG_ARMED` | 1 |
| `CONNECTED` | 1 |
| `ARMED` | 1 |
| `TAKEOFF_ISSUED` | 1 |
| `ALTITUDE_REACHED` | 1 |
| `CHECKPOINT_SAVED` | 1 |
| `MISSION_ROUTE_CONFIRMED` | 1 |
| `MISSION_PROGRESS` | 1 |
| `PAYLOAD_MISSION_1_STARTED` | 1 |
| `PAYLOAD_1_RELEASED` | 1 |
| `PAYLOAD_MISSION_1_COMPLETE` | 1 |
| `MISSION_CURRENT_ITEM_SET` | 1 |
| `MISSION_ROUTE_RESUMED` | 1 |
| `PAYLOAD_MISSION_2_STARTED` | 1 |
| `PAYLOAD_2_RELEASED` | 1 |
| `PAYLOAD_MISSION_2_COMPLETE` | 1 |
| `SEARCH_COMPLETE` | 1 |
| `SEARCH_WAYPOINTS_CANCELLED` | 1 |
| `GOREV2_COMPLETE` | 1 |
| `GOREV3_HOOK_INVOKED` | 1 |
| `GOREV3_PHASE_STARTED` | 1 |
| `GOREV3_PHASE_FAILED` | 1 |
| `RETURNING_TO_START_FINISH` | 1 |
| `RETURN_TO_START_FINISH_ARRIVED` | 1 |
| `WATCHDOG_DISARMED` | 1 |
