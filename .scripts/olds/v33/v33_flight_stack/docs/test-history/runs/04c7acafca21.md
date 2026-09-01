---
kind: mission_run
machine_generated: true
generator: tools/run_record.py
run_id: 04c7acafca21
date: 2026-08-24
started: 2026-08-24T17:38:26Z
ended: 2026-08-24T17:44:52Z
duration_s: 386.0
exit_code: ~
terminal_phase: MISSION_COMPLETE
event_count: 6479
raw_artifacts:
  - "../logs/mission_04c7acafca21.jsonl"
  - "../logs/mission_positions_04c7acafca21.json"
  - "../logs/mission_20260824_203826.log"
---

# Koşu kaydı — `04c7acafca21`

> Bu dosya `tools/run_record.py` tarafından üretildi. Yalnızca olay
> kaydından **türetilebilen olguları** içerir: ne olduğunu söyler, ne
> anlama geldiğini **söylemez**. Kök neden, amaç, doğrulama ve sonraki
> adım insan yargısıdır ve phase özetine (`docs/test-history/PH-*.md`)
> aittir. Bu kayıt doğrulanmış bir özet **değildir** ve hiçbir ham veriyi
> silinebilir yapmaz.

## Faz zinciri

- `+   6.0s`  `MISSION_INIT` → `CONNECTING`
- `+   9.1s`  `CONNECTING` → `ARMING`
- `+   9.1s`  `ARMING` → `TAKEOFF`
- `+   9.1s`  `TAKEOFF` → `CLIMB_TO_ALTITUDE`  — (target=15.0m)
- `+  24.7s`  `CLIMB_TO_ALTITUDE` → `CHECKPOINT_SAVE`
- `+  24.7s`  `CHECKPOINT_SAVE` → `MISSION_ROUTE_CONFIRM`
- `+  24.7s`  `MISSION_ROUTE_CONFIRM` → `MISSION_START`
- `+  28.3s`  `MISSION_START` → `SEARCHING`
- `+  31.1s`  `SEARCHING` → `TARGET_TRACKING`  — (MAVI_ALTIGEN)
- `+  31.1s`  `TARGET_TRACKING` → `SWITCH_TO_OFFBOARD`
- `+  32.1s`  `SWITCH_TO_OFFBOARD` → `GOTO_TARGET_CENTERING`  — (MAVI_ALTIGEN)
- `+  64.5s`  `GOTO_TARGET_CENTERING` → `HOVER_CONFIRM`
- `+  66.5s`  `HOVER_CONFIRM` → `GPS_SAVE`
- `+  66.5s`  `GPS_SAVE` → `SEARCHING`  — (single_target_recorded_resuming_route)
- `+  71.8s`  `SEARCHING` → `TARGET_TRACKING`  — (KIRMIZI_UCGEN)
- `+  71.8s`  `TARGET_TRACKING` → `SWITCH_TO_OFFBOARD`
- `+  72.2s`  `SWITCH_TO_OFFBOARD` → `GOTO_TARGET_CENTERING`  — (KIRMIZI_UCGEN)
- `+ 104.2s`  `GOTO_TARGET_CENTERING` → `HOVER_CONFIRM`
- `+ 106.3s`  `HOVER_CONFIRM` → `GPS_SAVE`
- `+ 106.3s`  `GPS_SAVE` → `SEARCH_COMPLETE`
- `+ 297.8s`  `SEARCH_COMPLETE` → `GOREV2_COMPLETE`
- `+ 297.8s`  `GOREV2_COMPLETE` → `GOREV3_START`
- `+ 297.8s`  `GOREV3_START` → `GOREV3_RUNNING`  — (pickup)
- `+ 344.3s`  `GOREV3_RUNNING` → `GOREV3_RUNNING`  — (transport)
- `+ 348.8s`  `GOREV3_RUNNING` → `GOREV3_RUNNING`  — (redrop)
- `+ 367.5s`  `GOREV3_RUNNING` → `RETURN_TO_CHECKPOINT`  — (gorev3_finish)
- `+ 382.3s`  `RETURN_TO_CHECKPOINT` → `RETURN_TO_CHECKPOINT`  — (gorev3_complete)
- `+ 385.8s`  `RETURN_TO_CHECKPOINT` → `LANDING`  — (gorev3_complete)
- `+ 385.9s`  `LANDING` → `MISSION_COMPLETE`

## Health geçişleri

| +s | alt sistem | durum |
|---|---|---|
| `+6.0` | `MavsdkBackendBase` | **HEALTHY** |
| `+6.0` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+7.0` | `MavsdkBackendBase` | **DEGRADED** |
| `+8.0` | `MavsdkBackendBase` | **STALE** |
| `+9.0` | `MavsdkBackendBase` | **HEALTHY** |
| `+37.1` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+38.1` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+53.2` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+54.2` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+81.2` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+82.2` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+152.6` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+153.6` | `Gorev2Orchestrator.vision` | **HEALTHY** |

## Merkezleme sonuçları

| +s | sonuç | şekil | irtifa (m) |
|---|---|---|---|
| `+49.2` | `CENTERING_TIMED_OUT` | MAVI_ALTIGEN | 15.0 |
| `+61.4` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 15.0 |
| `+89.5` | `CENTERING_TIMED_OUT` | KIRMIZI_UCGEN | 15.0 |
| `+101.1` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 15.0 |
| `+116.7` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 10.0 |
| `+126.4` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 5.0 |
| `+154.2` | `CENTERING_TIMED_OUT` | MAVI_ALTIGEN | 0.45 |
| `+215.8` | `CENTERING_TIMED_OUT` | KIRMIZI_UCGEN | 10.0 |
| `+239.6` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 5.0 |
| `+262.9` | `CENTERING_TIMED_OUT` | KIRMIZI_UCGEN | 0.45 |

## Payload olayları

- `+ 111.2s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 116.7s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 126.4s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 176.6s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 191.9s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 215.8s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 239.6s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 287.5s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN

## WARN ve üzeri olaylar

*Severity'ye göre süzülmüş tek bir liste. Bazı satırlar yukarıdaki*
*tablolarda da görünür (aynı olayın farklı görünümü, ek olay değil).*

- `+6.0s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=WAITING_MAVSDK_CONNECTION kind=BLOCKING_WAIT
- `+7.0s` **WARN** `HEALTH_STATE_CHANGED` (MavsdkBackendBase): MavsdkBackendBase -> DEGRADED
- `+8.0s` **WARN** `HEALTH_STATE_CHANGED` (MavsdkBackendBase): MavsdkBackendBase -> STALE
- `+9.1s` **WARN** `BLOCKING_STATE_ENTERED` (Gorev2Orchestrator): waiting_on=WAITING_ALTITUDE_REACHED kind=BLOCKING_WAIT
- `+24.7s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=WAITING_EXISTING_MISSION kind=BLOCKING_WAIT
- `+24.7s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=STARTING_UPLOADED_MISSION kind=BLOCKING_WAIT
- `+32.1s` **WARN** `BLOCKING_STATE_ENTERED` (CenteringController): waiting_on=WAITING_CENTERING_CONVERGENCE kind=BLOCKING_WAIT
- `+37.1s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+49.2s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): MAVI_ALTIGEN
- `+49.2s` **WARN** `RETRY_IN_PLACE` (Gorev2Orchestrator): MAVI_ALTIGEN 1/3
- `+53.2s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+72.2s` **WARN** `BLOCKING_STATE_ENTERED` (CenteringController): waiting_on=WAITING_CENTERING_CONVERGENCE kind=BLOCKING_WAIT
- `+81.2s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+89.5s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): KIRMIZI_UCGEN
- `+89.5s` **WARN** `RETRY_IN_PLACE` (Gorev2Orchestrator): KIRMIZI_UCGEN 1/3
- `+152.6s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+154.2s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): MAVI_ALTIGEN
- `+162.2s` **WARN** `MOUNT_TRANSLATE_DONE` (CenteringController): MAVI_ALTIGEN
- `+162.2s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): MAVI_ALTIGEN
- `+178.6s` **WARN** `PAYLOAD_VERIFICATION_RESULT` (PayloadReleaseService): expected=KIRMIZI_DIKDORTGEN found=False
- `+215.8s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): KIRMIZI_UCGEN
- `+215.8s` **WARN** `PAYLOAD_APPROACH_STEP_TIMED_OUT` (PayloadReleaseService): KIRMIZI_UCGEN
- `+262.9s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): KIRMIZI_UCGEN
- `+265.5s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): KIRMIZI_UCGEN
- `+285.5s` **WARN** `PAYLOAD_APPROACH_STEP_TIMED_OUT` (PayloadReleaseService): KIRMIZI_UCGEN
- `+285.9s` **WARN** `PAYLOAD_RELEASE_ALTITUDE` (PayloadReleaseService): KIRMIZI_UCGEN
- `+334.0s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): KIRMIZI_DIKDORTGEN
- `+355.5s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): KIRMIZI_UCGEN
- `+382.3s` **WARN** `BLOCKING_STATE_ENTERED` (MasterMissionController): waiting_on=RETURNING_TO_START_FINISH kind=BLOCKING_WAIT

## Tespit edilen şekiller (kare sayısı)

- `KIRMIZI_UCGEN`: 1297 kare
- `MAVI_ALTIGEN`: 799 kare
- `MAVI_DIKDORTGEN`: 486 kare
- `KIRMIZI_DIKDORTGEN`: 452 kare

## Olay sayımları

| kod | adet |
|---|---|
| `VISION_FRAME_PROCESSED` | 3193 |
| `CENTERING_STEP` | 1584 |
| `VEHICLE_TELEMETRY` | 683 |
| `LOW_ALT_OPEN_LOOP_STEP` | 395 |
| `WATCHDOG_UPDATED` | 385 |
| `TELEMETRY_STREAM_RATES` | 37 |
| `MISSION_PHASE_CHANGED` | 29 |
| `HEALTH_STATE_CHANGED` | 13 |
| `CENTERING_STARTED` | 12 |
| `TRACK_STATE_UPDATED` | 10 |
| `PAYLOAD_STATE` | 8 |
| `BLOCKING_STATE_ENTERED` | 7 |
| `BLOCKING_STATE_CLEARED` | 7 |
| `GLOBAL_POSITION_NAV_STARTED` | 6 |
| `GLOBAL_POSITION_NAV_CONVERGED` | 6 |
| `CENTERING_TIMED_OUT` | 5 |
| `CENTERING_CONVERGED` | 5 |
| `LOW_ALT_OPEN_LOOP_DESCENT` | 4 |
| `LOW_ALT_OPEN_LOOP_DESCENT_DONE` | 4 |
| `GOREV3_PHASE_STARTED` | 4 |
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
| `PAYLOAD_APPROACH_STEP_TIMED_OUT` | 2 |
| `WATCHDOG_ARMED` | 1 |
| `CONNECTED` | 1 |
| `ARMED` | 1 |
| `TAKEOFF_ISSUED` | 1 |
| `ALTITUDE_REACHED` | 1 |
| `CHECKPOINT_SAVED` | 1 |
| `MISSION_ROUTE_CONFIRMED` | 1 |
| `MISSION_PROGRESS` | 1 |
| `MISSION_CURRENT_ITEM_SET` | 1 |
| `MISSION_ROUTE_RESUMED` | 1 |
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
| `GOREV3_COMPLETE` | 1 |
| `RETURNING_TO_START_FINISH` | 1 |
| `RETURN_TO_START_FINISH_ARRIVED` | 1 |
| `MISSION_COMPLETE` | 1 |
| `WATCHDOG_DISARMED` | 1 |
