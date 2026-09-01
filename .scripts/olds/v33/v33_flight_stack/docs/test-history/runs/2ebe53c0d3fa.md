---
kind: mission_run
machine_generated: true
generator: tools/run_record.py
run_id: 2ebe53c0d3fa
date: 2026-08-24
started: 2026-08-24T17:45:32Z
ended: 2026-08-24T17:50:24Z
duration_s: 291.6
exit_code: ~
terminal_phase: MISSION_COMPLETE
event_count: 4800
raw_artifacts:
  - "../logs/mission_2ebe53c0d3fa.jsonl"
  - "../logs/mission_positions_2ebe53c0d3fa.json"
  - "../logs/mission_20260824_204532.log"
---

# Koşu kaydı — `2ebe53c0d3fa`

> Bu dosya `tools/run_record.py` tarafından üretildi. Yalnızca olay
> kaydından **türetilebilen olguları** içerir: ne olduğunu söyler, ne
> anlama geldiğini **söylemez**. Kök neden, amaç, doğrulama ve sonraki
> adım insan yargısıdır ve phase özetine (`docs/test-history/PH-*.md`)
> aittir. Bu kayıt doğrulanmış bir özet **değildir** ve hiçbir ham veriyi
> silinebilir yapmaz.

## Faz zinciri

- `+   5.9s`  `MISSION_INIT` → `CONNECTING`
- `+   9.1s`  `CONNECTING` → `ARMING`
- `+   9.2s`  `ARMING` → `TAKEOFF`
- `+   9.2s`  `TAKEOFF` → `CLIMB_TO_ALTITUDE`  — (target=15.0m)
- `+  25.7s`  `CLIMB_TO_ALTITUDE` → `CHECKPOINT_SAVE`
- `+  25.7s`  `CHECKPOINT_SAVE` → `MISSION_ROUTE_CONFIRM`
- `+  25.8s`  `MISSION_ROUTE_CONFIRM` → `MISSION_START`
- `+  29.3s`  `MISSION_START` → `SEARCHING`
- `+  32.2s`  `SEARCHING` → `TARGET_TRACKING`  — (MAVI_ALTIGEN)
- `+  32.2s`  `TARGET_TRACKING` → `SWITCH_TO_OFFBOARD`
- `+  33.2s`  `SWITCH_TO_OFFBOARD` → `GOTO_TARGET_CENTERING`  — (MAVI_ALTIGEN)
- `+  61.4s`  `GOTO_TARGET_CENTERING` → `HOVER_CONFIRM`
- `+  63.5s`  `HOVER_CONFIRM` → `GPS_SAVE`
- `+  63.5s`  `GPS_SAVE` → `SEARCHING`  — (single_target_recorded_resuming_route)
- `+  69.0s`  `SEARCHING` → `TARGET_TRACKING`  — (KIRMIZI_UCGEN)
- `+  69.0s`  `TARGET_TRACKING` → `SWITCH_TO_OFFBOARD`
- `+  69.4s`  `SWITCH_TO_OFFBOARD` → `GOTO_TARGET_CENTERING`  — (KIRMIZI_UCGEN)
- `+ 101.2s`  `GOTO_TARGET_CENTERING` → `HOVER_CONFIRM`
- `+ 103.2s`  `HOVER_CONFIRM` → `GPS_SAVE`
- `+ 103.2s`  `GPS_SAVE` → `SEARCH_COMPLETE`
- `+ 240.2s`  `SEARCH_COMPLETE` → `GOREV2_COMPLETE`
- `+ 240.2s`  `GOREV2_COMPLETE` → `GOREV3_START`
- `+ 240.2s`  `GOREV3_START` → `GOREV3_RUNNING`  — (pickup)
- `+ 264.6s`  `GOREV3_RUNNING` → `GOREV3_RUNNING`  — (transport)
- `+ 269.1s`  `GOREV3_RUNNING` → `GOREV3_RUNNING`  — (redrop)
- `+ 276.5s`  `GOREV3_RUNNING` → `RETURN_TO_CHECKPOINT`  — (gorev3_finish)
- `+ 286.3s`  `RETURN_TO_CHECKPOINT` → `RETURN_TO_CHECKPOINT`  — (gorev3_complete)
- `+ 291.5s`  `RETURN_TO_CHECKPOINT` → `LANDING`  — (gorev3_complete)
- `+ 291.5s`  `LANDING` → `MISSION_COMPLETE`

## Health geçişleri

| +s | alt sistem | durum |
|---|---|---|
| `+6.0` | `MavsdkBackendBase` | **HEALTHY** |
| `+6.0` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+7.0` | `MavsdkBackendBase` | **DEGRADED** |
| `+8.0` | `MavsdkBackendBase` | **STALE** |
| `+9.0` | `MavsdkBackendBase` | **HEALTHY** |
| `+30.1` | `Gorev2Orchestrator.vision` | **DEGRADED** |
| `+31.1` | `Gorev2Orchestrator.vision` | **HEALTHY** |

## Merkezleme sonuçları

| +s | sonuç | şekil | irtifa (m) |
|---|---|---|---|
| `+50.2` | `CENTERING_TIMED_OUT` | MAVI_ALTIGEN | 15.0 |
| `+58.4` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 15.0 |
| `+86.6` | `CENTERING_TIMED_OUT` | KIRMIZI_UCGEN | 15.0 |
| `+98.1` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 15.0 |
| `+125.2` | `CENTERING_CONVERGED` | MAVI_ALTIGEN | 10.0 |
| `+148.0` | `CENTERING_TIMED_OUT` | MAVI_ALTIGEN | 5.0 |
| `+198.0` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 10.0 |
| `+209.1` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 5.0 |
| `+220.6` | `CENTERING_CONVERGED` | KIRMIZI_UCGEN | 0.45 |

## Payload olayları

- `+ 107.8s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 125.2s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 148.0s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 162.1s`  şekil=MAVI_ALTIGEN index=1 — MAVI_ALTIGEN
- `+ 178.4s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 198.0s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 209.1s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN
- `+ 228.9s`  şekil=KIRMIZI_UCGEN index=2 — KIRMIZI_UCGEN

## WARN ve üzeri olaylar

*Severity'ye göre süzülmüş tek bir liste. Bazı satırlar yukarıdaki*
*tablolarda da görünür (aynı olayın farklı görünümü, ek olay değil).*

- `+5.9s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=WAITING_MAVSDK_CONNECTION kind=BLOCKING_WAIT
- `+7.0s` **WARN** `HEALTH_STATE_CHANGED` (MavsdkBackendBase): MavsdkBackendBase -> DEGRADED
- `+8.0s` **WARN** `HEALTH_STATE_CHANGED` (MavsdkBackendBase): MavsdkBackendBase -> STALE
- `+9.2s` **WARN** `BLOCKING_STATE_ENTERED` (Gorev2Orchestrator): waiting_on=WAITING_ALTITUDE_REACHED kind=BLOCKING_WAIT
- `+25.7s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=WAITING_EXISTING_MISSION kind=BLOCKING_WAIT
- `+25.8s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=STARTING_UPLOADED_MISSION kind=BLOCKING_WAIT
- `+30.1s` **WARN** `HEALTH_STATE_CHANGED` (Gorev2Orchestrator.vision): Gorev2Orchestrator.vision -> DEGRADED
- `+33.2s` **WARN** `BLOCKING_STATE_ENTERED` (CenteringController): waiting_on=WAITING_CENTERING_CONVERGENCE kind=BLOCKING_WAIT
- `+50.2s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): MAVI_ALTIGEN
- `+50.2s` **WARN** `RETRY_IN_PLACE` (Gorev2Orchestrator): MAVI_ALTIGEN 1/3
- `+69.4s` **WARN** `BLOCKING_STATE_ENTERED` (CenteringController): waiting_on=WAITING_CENTERING_CONVERGENCE kind=BLOCKING_WAIT
- `+86.6s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): KIRMIZI_UCGEN
- `+86.6s` **WARN** `RETRY_IN_PLACE` (Gorev2Orchestrator): KIRMIZI_UCGEN 1/3
- `+148.0s` **WARN** `CENTERING_TIMED_OUT` (CenteringController): MAVI_ALTIGEN
- `+148.0s` **WARN** `PAYLOAD_APPROACH_STEP_TIMED_OUT` (PayloadReleaseService): MAVI_ALTIGEN
- `+151.3s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): MAVI_ALTIGEN
- `+159.7s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): MAVI_ALTIGEN
- `+164.1s` **WARN** `PAYLOAD_VERIFICATION_RESULT` (PayloadReleaseService): expected=KIRMIZI_DIKDORTGEN found=False
- `+223.4s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): KIRMIZI_UCGEN
- `+230.9s` **WARN** `PAYLOAD_VERIFICATION_RESULT` (PayloadReleaseService): expected=MAVI_DIKDORTGEN found=False
- `+256.4s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): KIRMIZI_DIKDORTGEN
- `+273.1s` **WARN** `LOW_ALT_OPEN_LOOP_DESCENT` (CenteringController): KIRMIZI_UCGEN
- `+286.3s` **WARN** `BLOCKING_STATE_ENTERED` (MasterMissionController): waiting_on=RETURNING_TO_START_FINISH kind=BLOCKING_WAIT

## Tespit edilen şekiller (kare sayısı)

- `MAVI_ALTIGEN`: 920 kare
- `KIRMIZI_UCGEN`: 864 kare
- `MAVI_DIKDORTGEN`: 340 kare
- `KIRMIZI_DIKDORTGEN`: 266 kare

## Olay sayımları

| kod | adet |
|---|---|
| `VISION_FRAME_PROCESSED` | 2468 |
| `CENTERING_STEP` | 1205 |
| `VEHICLE_TELEMETRY` | 512 |
| `WATCHDOG_UPDATED` | 291 |
| `LOW_ALT_OPEN_LOOP_STEP` | 100 |
| `MISSION_PHASE_CHANGED` | 29 |
| `TELEMETRY_STREAM_RATES` | 28 |
| `CENTERING_STARTED` | 12 |
| `TRACK_STATE_UPDATED` | 10 |
| `PAYLOAD_STATE` | 8 |
| `BLOCKING_STATE_ENTERED` | 7 |
| `HEALTH_STATE_CHANGED` | 7 |
| `BLOCKING_STATE_CLEARED` | 7 |
| `CENTERING_CONVERGED` | 6 |
| `GLOBAL_POSITION_NAV_STARTED` | 6 |
| `GLOBAL_POSITION_NAV_CONVERGED` | 6 |
| `LOW_ALT_OPEN_LOOP_DESCENT` | 5 |
| `LOW_ALT_OPEN_LOOP_DESCENT_DONE` | 5 |
| `GOREV3_PHASE_STARTED` | 4 |
| `CENTERING_TIMED_OUT` | 3 |
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
| `PAYLOAD_APPROACH_STEP_TIMED_OUT` | 1 |
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
