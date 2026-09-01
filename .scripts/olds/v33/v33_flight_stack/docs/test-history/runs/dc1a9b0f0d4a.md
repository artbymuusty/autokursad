---
kind: mission_run
machine_generated: true
generator: tools/run_record.py
run_id: dc1a9b0f0d4a
date: 2026-08-26
started: 2026-08-26T20:32:16Z
ended: 2026-08-26T20:54:19Z
duration_s: 1323.0
exit_code: 0
terminal_phase: MISSION_FAILED
event_count: 4713
raw_artifacts:
  - "../logs/mission_dc1a9b0f0d4a.jsonl"
  - "../logs/mission_positions_dc1a9b0f0d4a.json"
  - "../logs/mission_20260826_233216.log"
---

# Koşu kaydı — `dc1a9b0f0d4a`

> Bu dosya `tools/run_record.py` tarafından üretildi. Yalnızca olay
> kaydından **türetilebilen olguları** içerir: ne olduğunu söyler, ne
> anlama geldiğini **söylemez**. Kök neden, amaç, doğrulama ve sonraki
> adım insan yargısıdır ve phase özetine (`docs/test-history/PH-*.md`)
> aittir. Bu kayıt doğrulanmış bir özet **değildir** ve hiçbir ham veriyi
> silinebilir yapmaz.

## Faz zinciri

- `+   6.1s`  `MISSION_INIT` → `CONNECTING`
- `+   7.9s`  `CONNECTING` → `ARMING`
- `+   7.9s`  `ARMING` → `TAKEOFF`
- `+   7.9s`  `TAKEOFF` → `CLIMB_TO_ALTITUDE`  — (target=15.0m)
- `+  24.5s`  `CLIMB_TO_ALTITUDE` → `CHECKPOINT_SAVE`
- `+  24.5s`  `CHECKPOINT_SAVE` → `MISSION_ROUTE_CONFIRM`
- `+  24.5s`  `MISSION_ROUTE_CONFIRM` → `MISSION_START`
- `+  28.1s`  `MISSION_START` → `SEARCHING`
- `+  31.1s`  `SEARCHING` → `TARGET_TRACKING`  — (MAVI_ALTIGEN)
- `+  31.1s`  `TARGET_TRACKING` → `SWITCH_TO_OFFBOARD`
- `+  32.0s`  `SWITCH_TO_OFFBOARD` → `GOTO_TARGET_CENTERING`  — (MAVI_ALTIGEN)
- `+  60.0s`  `GOTO_TARGET_CENTERING` → `HOVER_CONFIRM`
- `+  62.0s`  `HOVER_CONFIRM` → `GPS_SAVE`
- `+ 130.4s`  `GPS_SAVE` → `SEARCHING`  — (single_target_processed_resuming_route)
- `+ 136.5s`  `SEARCHING` → `TARGET_TRACKING`  — (KIRMIZI_UCGEN)
- `+ 136.5s`  `TARGET_TRACKING` → `SWITCH_TO_OFFBOARD`
- `+ 137.5s`  `SWITCH_TO_OFFBOARD` → `GOTO_TARGET_CENTERING`  — (KIRMIZI_UCGEN)
- `+ 184.0s`  `GOTO_TARGET_CENTERING` → `HOVER_CONFIRM`
- `+ 186.0s`  `HOVER_CONFIRM` → `GPS_SAVE`
- `+ 290.7s`  `GPS_SAVE` → `SEARCH_COMPLETE`
- `+ 290.9s`  `SEARCH_COMPLETE` → `GOREV2_COMPLETE`
- `+ 290.9s`  `GOREV2_COMPLETE` → `GOREV3_START`
- `+ 290.9s`  `GOREV3_START` → `GOREV3_RUNNING`  — (pickup)
- `+1322.7s`  `GOREV3_RUNNING` → `MISSION_TIMEOUT`  — (MISSION_TIMEOUT: exceeded 600s budget)
- `+1322.7s`  `MISSION_TIMEOUT` → `MISSION_TIMEOUT`  — (MISSION_TIMEOUT: exceeded 600s budget)
- `+1322.8s`  `MISSION_TIMEOUT` → `LANDING`  — (abort_recancelled)
- `+1322.9s`  `LANDING` → `MISSION_FAILED`  — (land_failed: <AioRpcError of RPC that terminated with: status = StatusCode.UNAVAILABLE details = "failed to connect to all addresses; last error: UNKNOWN: ipv4:127.0.0.1:50051: Failed to conne…

## Health geçişleri

| +s | alt sistem | durum |
|---|---|---|
| `+7.0` | `MavsdkBackendBase` | **HEALTHY** |
| `+7.0` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+51.2` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+53.2` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+1322.7` | `MavsdkBackendBase` | **DOWN** |
| `+1322.7` | `Gorev2Orchestrator.vision` | **DOWN** |

## Merkezleme sonuçları

| +s | sonuç | şekil | irtifa (m) |
|---|---|---|---|
| `+50.4` | `CENTERING_TIMED_OUT` | MAVI_ALTIGEN | 15.0 |
| `+56.9` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 15.0 |
| `+75.1` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 10.0 |
| `+82.7` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 5.0 |
| `+162.8` | `CENTERING_TIMED_OUT` | KIRMIZI_UCGEN | 15.0 |
| `+181.0` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 15.0 |
| `+212.8` | `CENTERING_TIMED_OUT` | KIRMIZI_UCGEN | 10.0 |
| `+231.4` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 5.0 |
| `+257.6` | `CENTERING_TIMED_OUT` | KIRMIZI_UCGEN | 0.45 |

## Payload olayları

- `+  62.0s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+  75.1s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+  82.7s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 108.4s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 186.0s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 212.8s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 231.4s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 268.6s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN

## WARN ve üzeri olaylar

*Severity'ye göre süzülmüş tek bir liste. Bazı satırlar yukarıdaki*
*tablolarda da görünür (aynı olayın farklı görünümü, ek olay değil).*

- `+6.1s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=WAITING_MAVSDK_CONNECTION kind=BLOCKING_WAIT
- `+7.9s` **WARN** `BLOCKING_STATE_ENTERED` (Gorev2Orchestrator): waiting_on=WAITING_ALTITUDE_REACHED kind=BLOCKING_WAIT
- `+24.5s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=WAITING_EXISTING_MISSION kind=BLOCKING_WAIT
- `+24.5s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=STARTING_UPLOADED_MISSION kind=BLOCKING_WAIT
- `+32.0s` **WARN** `BLOCKING_STATE_ENTERED` (CenteringController): waiting_on=WAITING_CENTERING_CONVERGENCE kind=BLOCKING_WAIT
- `+50.4s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): MAVI_ALTIGEN
- `+50.4s` **WARN** `RETRY_IN_PLACE` (Gorev2Orchestrator): MAVI_ALTIGEN 1/3
- `+51.2s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+87.0s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): MAVI_ALTIGEN
- `+94.5s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): MAVI_ALTIGEN
- `+110.4s` **WARN** `PAYLOAD_VERIFICATION_RESULT` (PayloadReleaseService): expected=KIRMIZI_DIKDORTGEN found=False
- `+130.4s` **WARN** `CLIMB_TIMED_OUT` (CenteringController): 
- `+137.5s` **WARN** `BLOCKING_STATE_ENTERED` (CenteringController): waiting_on=WAITING_CENTERING_CONVERGENCE kind=BLOCKING_WAIT
- `+162.8s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): KIRMIZI_UCGEN
- `+162.8s` **WARN** `RETRY_IN_PLACE` (Gorev2Orchestrator): KIRMIZI_UCGEN 1/3
- `+212.8s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): KIRMIZI_UCGEN
- `+212.8s` **WARN** `PAYLOAD_APPROACH_STEP_TIMED_OUT` (PayloadReleaseService): KIRMIZI_UCGEN
- `+257.6s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): KIRMIZI_UCGEN
- `+265.7s` **WARN** `MOUNT_TRANSLATE_DONE` (CenteringController): KIRMIZI_UCGEN
- `+265.7s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): KIRMIZI_UCGEN
- `+270.6s` **WARN** `PAYLOAD_VERIFICATION_RESULT` (PayloadReleaseService): expected=MAVI_DIKDORTGEN found=False
- `+290.7s` **WARN** `CLIMB_TIMED_OUT` (CenteringController): 
- `+1322.7s` **CRITICAL** `HEALTH_STATE_CHANGED` (MavsdkBackendBase): MavsdkBackendBase -> DOWN
- `+1322.7s` **CRITICAL** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DOWN
- `+1322.7s` **CRITICAL** `WATCHDOG_FIRED` (MasterMissionController): MISSION_TIMEOUT exceeded 600s
- `+1322.7s` **CRITICAL** `MISSION_PHASE_CHANGED` (WatchdogEngine): GOREV3_RUNNING -> MISSION_TIMEOUT (MISSION_TIMEOUT: exceeded 600s budget)
- `+1322.7s` **CRITICAL** `MISSION_ABORT_REQUESTED` (MasterMissionController): MISSION_TIMEOUT: exceeded 600s budget
- `+1322.7s` **CRITICAL** `MISSION_PHASE_CHANGED` (MissionContext): MISSION_TIMEOUT -> MISSION_TIMEOUT (MISSION_TIMEOUT: exceeded 600s budget)
- `+1322.7s` **CRITICAL** `TELEMETRY_STALE` (MavsdkBackendBase): position stale
- `+1322.7s` **CRITICAL** `TELEMETRY_STALE` (MasterMissionController): position: last sample 1019.7s old (limit 1.0s) -- vehicle link is not delivering telemetry
- `+1322.9s` **CRITICAL** `MISSION_PHASE_CHANGED` (MissionContext): LANDING -> MISSION_FAILED (land_failed: <AioRpcError of RPC that terminated with: status = StatusCode.UNAVAILABLE details = "failed to connect to all addresses; last error: UNKNOWN: ipv4:127.0.0.1:50051: Failed to conne…
- `+1322.9s` **CRITICAL** `MISSION_FAILED` (MasterMissionController): land_failed: <AioRpcError of RPC that terminated with: status = StatusCode.UNAVAILABLE details = "failed to connect to all addresses; last error: UNKNOWN: ipv4:127.0.0.1:50051: Failed to connect to remote host: Connecti…

## Tespit edilen şekiller (kare sayısı)

- `KIRMIZI_UCGEN`: 958 kare
- `MAVI_ALTIGEN`: 706 kare
- `MAVI_DIKDORTGEN`: 173 kare
- `KIRMIZI_DIKDORTGEN`: 74 kare

## Olay sayımları

| kod | adet |
|---|---|
| `VISION_FRAME_PROCESSED` | 2302 |
| `CENTERING_STEP` | 1230 |
| `VEHICLE_TELEMETRY` | 537 |
| `WATCHDOG_UPDATED` | 301 |
| `LOW_ALT_OPEN_LOOP_STEP` | 139 |
| `TELEMETRY_STREAM_RATES` | 29 |
| `MISSION_PHASE_CHANGED` | 27 |
| `TRACK_STATE_UPDATED` | 10 |
| `CENTERING_STARTED` | 10 |
| `PAYLOAD_STATE` | 8 |
| `BLOCKING_STATE_ENTERED` | 6 |
| `HEALTH_STATE_CHANGED` | 6 |
| `BLOCKING_STATE_CLEARED` | 6 |
| `CENTERING_CONVERGED` | 5 |
| `CENTERING_TIMED_OUT` | 4 |
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
| `CLIMB_TIMED_OUT` | 2 |
| `GOREV_V3_SUCCESS` | 2 |
| `TELEMETRY_STALE` | 2 |
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
| `GLOBAL_POSITION_NAV_STARTED` | 1 |
| `GLOBAL_POSITION_NAV_CONVERGED` | 1 |
| `WATCHDOG_FIRED` | 1 |
| `MISSION_ABORT_REQUESTED` | 1 |
| `MISSION_FAILED` | 1 |
| `WATCHDOG_DISARMED` | 1 |
