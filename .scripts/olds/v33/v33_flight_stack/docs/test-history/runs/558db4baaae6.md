---
kind: mission_run
machine_generated: true
generator: tools/run_record.py
run_id: 558db4baaae6
date: 2026-08-24
started: 2026-08-24T20:56:40Z
ended: 2026-08-24T20:57:00Z
duration_s: 20.7
exit_code: ~
terminal_phase: MISSION_FAILED
event_count: 181
raw_artifacts:
  - "../logs/mission_558db4baaae6.jsonl"
  - "../logs/mission_20260824_235640.log"
---

# Koşu kaydı — `558db4baaae6`

> Bu dosya `tools/run_record.py` tarafından üretildi. Yalnızca olay
> kaydından **türetilebilen olguları** içerir: ne olduğunu söyler, ne
> anlama geldiğini **söylemez**. Kök neden, amaç, doğrulama ve sonraki
> adım insan yargısıdır ve phase özetine (`docs/test-history/PH-*.md`)
> aittir. Bu kayıt doğrulanmış bir özet **değildir** ve hiçbir ham veriyi
> silinebilir yapmaz.

## Faz zinciri

- `+   5.7s`  `MISSION_INIT` → `CONNECTING`
- `+  20.7s`  `CONNECTING` → `MISSION_FAILED`  — (WAITING_MAVSDK_CONNECTION timed out after 15s)
- `+  20.7s`  `MISSION_FAILED` → `LANDING`  — (gorev2_exception: WAITING_MAVSDK_CONNECTION timed out after 15s)
- `+  20.7s`  `LANDING` → `MISSION_FAILED`  — (land_failed: Action plugin has not been initialized! Did you run `System.connect()`?)

## Health geçişleri

| +s | alt sistem | durum |
|---|---|---|
| `+6.0` | `MavsdkBackendBase` | **HEALTHY** |
| `+6.0` | `Gorev2Orchestrator.vision` | **HEALTHY** |
| `+7.0` | `MavsdkBackendBase` | **DEGRADED** |
| `+8.0` | `MavsdkBackendBase` | **STALE** |
| `+9.0` | `MavsdkBackendBase` | **DOWN** |

## WARN ve üzeri olaylar

*Severity'ye göre süzülmüş tek bir liste. Bazı satırlar yukarıdaki*
*tablolarda da görünür (aynı olayın farklı görünümü, ek olay değil).*

- `+5.7s` **WARN** `BLOCKING_STATE_ENTERED` (MavsdkBackendBase): waiting_on=WAITING_MAVSDK_CONNECTION kind=BLOCKING_WAIT
- `+7.0s` **WARN** `HEALTH_STATE_CHANGED` (MavsdkBackendBase): MavsdkBackendBase -> DEGRADED
- `+8.0s` **WARN** `HEALTH_STATE_CHANGED` (MavsdkBackendBase): MavsdkBackendBase -> STALE
- `+9.0s` **CRITICAL** `HEALTH_STATE_CHANGED` (MavsdkBackendBase): MavsdkBackendBase -> DOWN
- `+20.7s` **CRITICAL** `MISSION_PHASE_CHANGED` (MissionContext): CONNECTING -> MISSION_FAILED (WAITING_MAVSDK_CONNECTION timed out after 15s)
- `+20.7s` **CRITICAL** `MISSION_FAILED` (Gorev2Orchestrator): WAITING_MAVSDK_CONNECTION timed out after 15s
- `+20.7s` **WARN** `RETURN_TO_START_FINISH_SKIPPED` (MasterMissionController): checkpoint never recorded -- landing in place
- `+20.7s` **CRITICAL** `MISSION_PHASE_CHANGED` (MissionContext): LANDING -> MISSION_FAILED (land_failed: Action plugin has not been initialized! Did you run `System.connect()`?)
- `+20.7s` **CRITICAL** `MISSION_FAILED` (MasterMissionController): land_failed: Action plugin has not been initialized! Did you run `System.connect()`?

## Olay sayımları

| kod | adet |
|---|---|
| `VISION_FRAME_PROCESSED` | 143 |
| `WATCHDOG_UPDATED` | 21 |
| `HEALTH_STATE_CHANGED` | 5 |
| `MISSION_PHASE_CHANGED` | 4 |
| `MISSION_STARTED` | 2 |
| `MISSION_FAILED` | 2 |
| `WATCHDOG_ARMED` | 1 |
| `BLOCKING_STATE_ENTERED` | 1 |
| `RETURN_TO_START_FINISH_SKIPPED` | 1 |
| `WATCHDOG_DISARMED` | 1 |
