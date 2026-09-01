---
kind: mission_run
machine_generated: true
generator: tools/run_record.py
run_id: 3f1c0cdc1d2f
date: 2026-08-26
started: 2026-08-26T18:02:17Z
ended: 2026-08-26T18:06:51Z
duration_s: 274.0
exit_code: 0
terminal_phase: MISSION_FAILED
event_count: 4167
raw_artifacts:
  - "../logs/mission_3f1c0cdc1d2f.jsonl"
  - "../logs/mission_positions_3f1c0cdc1d2f.json"
  - "../logs/mission_20260826_210217.log"
---

# Koşu kaydı — `3f1c0cdc1d2f`

> Bu dosya `tools/run_record.py` tarafından üretildi. Yalnızca olay
> kaydından **türetilebilen olguları** içerir: ne olduğunu söyler, ne
> anlama geldiğini **söylemez**. Kök neden, amaç, doğrulama ve sonraki
> adım insan yargısıdır ve phase özetine (`docs/test-history/PH-*.md`)
> aittir. Bu kayıt doğrulanmış bir özet **değildir** ve hiçbir ham veriyi
> silinebilir yapmaz.

## Faz zinciri

- `+   5.8s`  `MISSION_INIT` → `CONNECTING`
- `+   7.3s`  `CONNECTING` → `ARMING`
- `+   7.4s`  `ARMING` → `TAKEOFF`
- `+   7.4s`  `TAKEOFF` → `CLIMB_TO_ALTITUDE`  — (target=15.0m)
- `+  27.2s`  `CLIMB_TO_ALTITUDE` → `CHECKPOINT_SAVE`
- `+  27.2s`  `CHECKPOINT_SAVE` → `MISSION_ROUTE_CONFIRM`
- `+  27.2s`  `MISSION_ROUTE_CONFIRM` → `MISSION_START`
- `+  31.3s`  `MISSION_START` → `SEARCHING`
- `+  34.1s`  `SEARCHING` → `TARGET_TRACKING`  — (MAVI_ALTIGEN)
- `+  34.1s`  `TARGET_TRACKING` → `SWITCH_TO_OFFBOARD`
- `+  34.4s`  `SWITCH_TO_OFFBOARD` → `GOTO_TARGET_CENTERING`  — (MAVI_ALTIGEN)
- `+  74.5s`  `GOTO_TARGET_CENTERING` → `HOVER_CONFIRM`
- `+  76.5s`  `HOVER_CONFIRM` → `GPS_SAVE`
- `+ 122.7s`  `GPS_SAVE` → `SEARCHING`  — (single_target_processed_resuming_route)
- `+ 128.0s`  `SEARCHING` → `TARGET_TRACKING`  — (KIRMIZI_UCGEN)
- `+ 128.0s`  `TARGET_TRACKING` → `SWITCH_TO_OFFBOARD`
- `+ 129.1s`  `SWITCH_TO_OFFBOARD` → `GOTO_TARGET_CENTERING`  — (KIRMIZI_UCGEN)
- `+ 162.4s`  `GOTO_TARGET_CENTERING` → `HOVER_CONFIRM`
- `+ 164.4s`  `HOVER_CONFIRM` → `GPS_SAVE`
- `+ 239.2s`  `GPS_SAVE` → `SEARCH_COMPLETE`
- `+ 239.3s`  `SEARCH_COMPLETE` → `GOREV2_COMPLETE`
- `+ 239.3s`  `GOREV2_COMPLETE` → `GOREV3_START`
- `+ 239.3s`  `GOREV3_START` → `GOREV3_RUNNING`  — (pickup)
- `+ 261.0s`  `GOREV3_RUNNING` → `MISSION_FAILED`  — (gorev3_pickup_failed)
- `+ 261.0s`  `MISSION_FAILED` → `RETURN_TO_CHECKPOINT`  — (gorev3_failed)
- `+ 273.9s`  `RETURN_TO_CHECKPOINT` → `LANDING`  — (gorev3_failed)
- `+ 274.0s`  `LANDING` → `MISSION_FAILED`  — (landed_after_prior_failure)

## Health geçişleri

| +s | alt sistem | durum |
|---|---|---|
| `+6.1` | `MavsdkBackendBase` | **HEALTHY** |
| `+6.1` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+20.2` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+21.2` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+181.1` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+182.1` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+210.2` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+211.2` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+254.6` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+255.6` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+270.7` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+271.7` | `Gorev2Orchestrator.vision` | **HEALTHY** |

## Merkezleme sonuçları

| +s | sonuç | şekil | irtifa (m) |
|---|---|---|---|
| `+59.3` | `CENTERING_TIMED_OUT` | MAVI_ALTIGEN | 15.0 |
| `+71.4` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 15.0 |
| `+86.6` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 10.0 |
| `+93.4` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 5.0 |
| `+148.9` | `CENTERING_TIMED_OUT` | KIRMIZI_UCGEN | 15.0 |
| `+159.3` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 15.0 |
| `+182.6` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 10.0 |
| `+193.3` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 5.0 |
| `+202.3` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 0.45 |
| `+261.0` | `CENTERING_CONVERGED` | KIRMIZI_DIKDORTGEN | 0.3 |

## Payload olayları

- `+  76.5s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+  86.6s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+  93.4s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 111.9s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 164.4s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 182.6s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 193.3s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 227.3s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN

## WARN ve üzeri olaylar

*Severity'ye göre süzülmüş tek bir liste. Bazı satırlar yukarıdaki*
*tablolarda da görünür (aynı olayın farklı görünümü, ek olay değil).*

- `+5.8s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=WAITING_MAVSDK_CONNECTION kind=BLOCKING_WAIT
- `+7.4s` **WARN** `BLOCKING_STATE_ENTERED` (Gorev2Orchestrator): waiting_on=WAITING_ALTITUDE_REACHED kind=BLOCKING_WAIT
- `+20.2s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+27.2s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=WAITING_EXISTING_MISSION kind=BLOCKING_WAIT
- `+27.2s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=STARTING_UPLOADED_MISSION kind=BLOCKING_WAIT
- `+34.4s` **WARN** `BLOCKING_STATE_ENTERED` (CenteringController): waiting_on=WAITING_CENTERING_CONVERGENCE kind=BLOCKING_WAIT
- `+59.3s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): MAVI_ALTIGEN
- `+59.3s` **WARN** `RETRY_IN_PLACE` (Gorev2Orchestrator): MAVI_ALTIGEN 1/3
- `+97.2s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): MAVI_ALTIGEN
- `+107.9s` **WARN** `MOUNT_TRANSLATE_DONE` (CenteringController): MAVI_ALTIGEN
- `+107.9s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): MAVI_ALTIGEN
- `+129.1s` **WARN** `BLOCKING_STATE_ENTERED` (CenteringController): waiting_on=WAITING_CENTERING_CONVERGENCE kind=BLOCKING_WAIT
- `+148.9s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): KIRMIZI_UCGEN
- `+148.9s` **WARN** `RETRY_IN_PLACE` (Gorev2Orchestrator): KIRMIZI_UCGEN 1/3
- `+181.1s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+204.8s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): KIRMIZI_UCGEN
- `+210.2s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+224.9s` **WARN** `PAYLOAD_APPROACH_STEP_TIMED_OUT` (PayloadReleaseService): KIRMIZI_UCGEN
- `+225.3s` **WARN** `PAYLOAD_RELEASE_ALTITUDE` (PayloadReleaseService): KIRMIZI_UCGEN
- `+229.3s` **WARN** `PAYLOAD_FINAL_POSE` (PayloadReleaseService): KIRMIZI_UCGEN
- `+229.3s` **WARN** `PAYLOAD_VERIFICATION_RESULT` (PayloadReleaseService): expected=MAVI_DIKDORTGEN found=False
- `+254.6s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+261.0s` **CRITICAL** `MISSION_PHASE_CHANGED` (MissionContext): GOREV3_RUNNING -> MISSION_FAILED (gorev3_pickup_failed)
- `+261.0s` **CRITICAL** `GOREV3_PHASE_FAILED` (Gorev3Orchestrator): pickup
- `+261.0s` **WARN** `BLOCKING_STATE_ENTERED` (MasterMissionController): waiting_on=RETURNING_TO_START_FINISH kind=BLOCKING_WAIT
- `+270.7s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+274.0s` **CRITICAL** `MISSION_PHASE_CHANGED` (MissionContext): LANDING -> MISSION_FAILED (landed_after_prior_failure)

## Tespit edilen şekiller (kare sayısı)

- `MAVI_ALTIGEN`: 709 kare
- `KIRMIZI_UCGEN`: 652 kare
- `MAVI_DIKDORTGEN`: 239 kare
- `KIRMIZI_DIKDORTGEN`: 199 kare

## Olay sayımları

| kod | adet |
|---|---|
| `VISION_FRAME_PROCESSED` | 2039 |
| `CENTERING_STEP` | 966 |
| `VEHICLE_TELEMETRY` | 489 |
| `WATCHDOG_UPDATED` | 273 |
| `LOW_ALT_OPEN_LOOP_STEP` | 189 |
| `MISSION_PHASE_CHANGED` | 27 |
| `TELEMETRY_STREAM_RATES` | 26 |
| `HEALTH_STATE_CHANGED` | 12 |
| `CENTERING_STARTED` | 11 |
| `TRACK_STATE_UPDATED` | 10 |
| `CENTERING_CONVERGED` | 8 |
| `PAYLOAD_STATE` | 8 |
| `BLOCKING_STATE_ENTERED` | 7 |
| `BLOCKING_STATE_CLEARED` | 7 |
| `LOW_ALT_OPEN_LOOP_DESCENT` | 3 |
| `LOW_ALT_OPEN_LOOP_DESCENT_DONE` | 3 |
| `PAYLOAD_STATE_SYNC` | 3 |
| `MISSION_STARTED` | 2 |
| `MISSION_STARTED_ONBOARD` | 2 |
| `TARGET_SELECTED` | 2 |
| `MISSION_AUTHORITY_RELEASED` | 2 |
| `OFFBOARD_SWITCH_CONFIRMED` | 2 |
| `OFFBOARD_AUTHORITY_ACQUIRED` | 2 |
| `CENTERING_TIMED_OUT` | 2 |
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
| `PAYLOAD_APPROACH_STEP_TIMED_OUT` | 1 |
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
