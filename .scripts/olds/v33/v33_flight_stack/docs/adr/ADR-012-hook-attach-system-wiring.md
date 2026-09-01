# ADR-012 — Wiring HookAttachSystem: Runtime Re-Attach to a World-Loaded Body

**Status:** Accepted (mechanism verified in isolation; not yet reachable through the full Görev 3 mission flow — see Consequences)
**Date:** 2026-08-20
**Supersedes:** nothing (fills a gap ADR-011 left open: ADR-011 covers *release*, this covers *re-attach*)
**Scope:** `Tools/simulation/gz/models/x500_mono_cam_down/model.sdf`, `gz_system/gz_payload_actuator.py`, `core/config/parameters.py`. `core/mission/gorev3_pickup.py`/`gorev3_redrop.py` (the flight-side alignment/verification logic) are unchanged — this ADR only wires the actuator methods they already call.

## Context

Mission Flow V3's Görev 3 ("Topla ve Taşı") needs the vehicle to physically re-attach to a payload it dropped during Görev 2. This is the mirror image of ADR-011's problem, not a repeat of it.

ADR-011 established that a body must **exist from world load** to get reliable collision pairs in this gz-sim 8.15 build, and that release should be a `DetachableJoint` freed by a detach message. That mechanism cannot be reused for catch: the stock `gz-sim-detachable-joint-system`'s `attachRequested` flag defaults to `true` and is never reset, so it auto-attaches the instant its configured child model becomes resolvable — correct for a payload that starts mounted, wrong for one that must stay free on the ground until an explicit "pick up" command, possibly minutes later.

`src/modules/simulation/gz_plugins/hook_attach/HookAttachSystem.cc` was already written and compiled for exactly this (`libHookAttachSystem.dylib` present in the build tree) — attach only on an explicit message carrying the target child model's name, output state on `/hook/state` — but was never referenced by any `.sdf`/`.world` file. `gz_system/gz_payload_actuator.py`'s own `activate_pickup_mechanism()`/`activate_drop_mechanism()` carried `TODO[GOREV3]` comments describing exactly this missing wire.

## Decision

**One `HookAttachSystem` instance, added to `x500_mono_cam_down/model.sdf`**, alongside the two existing `DetachableJoint` blocks (same file, same pattern):

```xml
<plugin filename="libHookAttachSystem.dylib" name="hook_attach::HookAttachSystem">
  <parent_link>base_link</parent_link>
  <child_link>link</child_link>
  <attach_topic>/hook/attach</attach_topic>
  <detach_topic>/hook/detach</detach_topic>
  <output_topic>/hook/state</output_topic>
</plugin>
```

One instance suffices — unlike `DetachableJoint`, the target child model is **not fixed in SDF**; it comes from the `/hook/attach` message body (a `StringMsg`), matching the plugin's own design ("the dropped payload's spawned name isn't known until PayloadDropSystem actually drops it" — the plugin's own comment, from before ADR-011 fixed payload naming to be static; the reasoning about *when* the target is knowable still holds even though the name itself is now static).

`parent_link` is set to `base_link` (the C++ default, `hook_rope_link`, does not exist on this airframe) — identical to how both `DetachableJoint` blocks already override it.

**Target is hardcoded to `payload_red`.** `PayloadInterlock` (Görev 2 Rapor Bölüm 11.1) makes Mavi Altıgen's release complete before Kırmızı Üçgen's, unconditionally — a real competition rule, not an implementation choice (confirmed with the user before F0). Since Görev 3's pickup target is always the *first* payload released, and that is always Mavi Altıgen → `payload_red`, the color is a compile-time constant (`GOREV3_PICKUP_TARGET_COLOR = "red"` in `gz_payload_actuator.py`) with a comment pointing at the invariant it depends on, not a parameter threaded through from mission state.

**Confirmation is pose-based, not `/hook/state`-based.** `GzPoseMonitor`'s own docstring documents that a one-shot `gz topic -e -n 1` subscription costs ~2 s of gz-transport discovery and is a slow-joiner risk; this was independently reproduced during F3's isolated test — a `gz topic -e -n 1` sampled immediately after publishing the attach/detach request missed the `/hook/state` message on repeated attempts, while the *physical* pose evidence (below) was unambiguous throughout. `activate_pickup_mechanism()` therefore polls the existing `_relative_drop()` helper (vehicle *z* − payload *z*, already used by the release path) until it settles near zero — genuine attachment, not a flag — capped by `V3_CATCH_PAYLOAD_TIMEOUT_S` (15 s, the value the operator specified; this is the one timeout point in the whole V3 flow). `activate_drop_mechanism()` reuses the existing `_at_rest_height()` check the same way the release path already does, best-effort, no separate timeout (matching the spec's "one timeout point" framing).

## Evidence

**Isolated test** (before any Python wiring existed, raw `gz topic` CLI against the loaded plugin): `payload_red` at rest (`z≈0.025`) → `/hook/attach "payload_red"` → vehicle hovering (~0.9 m) → `payload_red` jumped to `z≈0.74`, tracking the airborne vehicle → `/hook/detach true` → `payload_red` back at `z≈0.018` (its natural rest height). Requesting attach for a nonexistent model name never produced a state transition inside 15 s+ (multiple probes, up to ~16.2 s).

**Wired-code test** (the actual `GzPayloadActuator.activate_pickup_mechanism()`/`activate_drop_mechanism()`, called directly, no mission orchestrator involved): `payload_red` at rest (`z≈0.025`) → vehicle armed and hovering at 1.84 m → `activate_pickup_mechanism() → True`, `payload_red` observed at `z≈1.085` (tracking the vehicle) → `activate_drop_mechanism() → True`, `payload_red` observed at `z≈0.024` (back at rest) → a repeat attach request against a nonexistent model correctly returned `False` after the full 15 s window (~16.1 s including polling overhead).

Neither test used the mission orchestrator (`Gorev3PickupPhase`) — see Consequences.

## Consequences

> **⚠️ CORRECTION (2026-08-23):** the paragraph below is WRONG on one point
> and is retained only as a historical record. `KIRMIZI_DIKDORTGEN` and the
> `payload_red` model are the SAME OBJECT — a 0.30 × 0.225 m red box,
> statically declared at `default.sdf:181`. No rectangle ground model needed
> to be added. `Gorev3PickupPhase` has since completed end-to-end in SITL five
> times (`mission_20260820_215953`, `20260821_180553`, `_181527`, `_183622`,
> `_184251`). The two "Kırmızı Dikdörtgen bulunamadı" failures were a detector
> bug (`_overlaps_committed()` had no colour check, fixed 2026-08-20 21:54),
> not a missing object. See `payload/KNOWN_ISSUES.md` §4.

**Not yet reachable through the real Görev 3 flow.** `Gorev3PickupPhase.run()` still calls `activate_pickup_mechanism()` only *after* visually locating `KIRMIZI_DIKDORTGEN` (`_locate_target_with_retries()`). `Tools/simulation/gz/worlds/default.sdf` declares exactly two ground targets, `blue_hexagon` and `red_triangle` — ~~no rectangle model exists at all~~, a limitation already flagged in the F0/F1/F2 reports and confirmed live in F2's SITL run ("Kırmızı Dikdörtgen bulunamadı"). This ADR does not change that: adding a rectangle ground model is a separate SDF change, out of scope here (F3's brief was the attach mechanism, not the vision target), and requires its own authorization. Until it exists, `Gorev3PickupPhase` will keep failing at the vision-acquisition step, never reaching the code this ADR wires up — the mechanism is proven, the path to it in a full flight is not yet open.

**`/hook/state` is live but unused by the Python side.** The topic works (confirmed receiving `data: true` once, mid-investigation) — a future caller with a more robust subscription (a persistent background reader, the same pattern `GzPoseMonitor` already uses for `dynamic_pose/info`, rather than one-shot CLI echoes) could consume it directly instead of inferring attachment from pose. Not built now: pose-based confirmation was already proven sufficient and reuses code that exists.

**Real hardware.** `real_system.yaml`'s `mission_v3.servo2_actuator_channel`/`servo3_actuator_channel` remain `null` — no source of truth for these values exists anywhere in the repository (F0 finding, unchanged). `real_payload_actuator.py`'s pickup/drop methods are still simulation-only stubs; this ADR covers Gazebo only.

**`GOREV3_PICKUP_TARGET_COLOR = "red"` is an invariant, not a lookup.** If `PayloadInterlock`'s fixed release order is ever relaxed, this constant (and the comment pointing at why it is safe today) must be revisited.
