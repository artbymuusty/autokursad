"""In-memory payload actuator for phase tests.

KEEP THIS IN STEP WITH GzPayloadActuator. This double fell behind twice and
both times it surfaced as a spurious phase-test failure rather than as a
real defect:

  * Görev 3 Faz 3 gained a real drop verification (it now reads the released
    payload's pose and rejects a "drop" that left the payload in the air);
    the mock had no get_released_payload_pose and the redrop tests died with
    AttributeError.
  * Görev 3 Faz 1 gained the hook-pose-based seating gate and its closed-loop
    alignment (2026-08-26); the mock had none of the hook accessors.

The defaults model a NOMINAL rig -- hook already aligned, pickup seats,
payload lifts with the vehicle and lands on target -- so a phase test that
wants a failure has to ask for one explicitly.
"""
from typing import List, Tuple

from core.interfaces.i_payload_actuator import IPayloadActuator

# Where the mock's released payload comes to rest: on the Kırmızı Üçgen, at
# the payload's own half-height, i.e. genuinely on the ground.
_RESTING_POSE = (0.0, 40.0, 0.035)


class MockPayloadActuator(IPayloadActuator):
    def __init__(self, pickup_succeeds: bool = True, drop_succeeds: bool = True,
                 hook_offset=(0.0, 0.0), released_pose=_RESTING_POSE):
        self.calls: List[Tuple[str, dict]] = []
        self._pickup_succeeds = pickup_succeeds
        self._drop_succeeds = drop_succeeds
        self._hook_offset = hook_offset
        self._released_pose = released_pose
        self._attached = False
        self._payload_z = 0.035
        # Where the hook nose sits relative to the vehicle origin, (north, east).
        # Zero = hanging plumb; non-zero = displaced by rope swing.
        self.hook_ned_offset = (0.0, 0.0)
        # While the payload rides the hook it climbs with the vehicle. The
        # phase reads payload_altitude_m once before the verification climb
        # and once after, and requires the difference to exceed
        # PICKUP_LIFT_CONFIRM_M, so a static value would read as "never left
        # the ground" no matter how the phase behaved.
        self.lift_per_read_m = 1.0

    # ---------------------------------------------------------- Görev 2 --
    async def release_payload_at_mavi_altigen(self) -> bool:
        self.calls.append(('release_payload_at_mavi_altigen', {}))
        return True

    async def release_payload_at_kirmizi_ucgen(self) -> bool:
        self.calls.append(('release_payload_at_kirmizi_ucgen', {}))
        return True

    # ---------------------------------------------------------- Görev 3 --
    async def activate_pickup_mechanism(self, altitude_m=None,
                                        deck_height_m=None, on_retry=None) -> bool:
        self.calls.append(('activate_pickup_mechanism', {}))
        if self._pickup_succeeds:
            self._attached = True
        return self._pickup_succeeds

    async def activate_drop_mechanism(self) -> bool:
        self.calls.append(('activate_drop_mechanism', {}))
        if self._drop_succeeds:
            self._attached = False
            self._payload_z = self._released_pose[2]
        return self._drop_succeeds

    async def set_winch(self, extension_m: float) -> bool:
        self.calls.append(('set_winch', {'extension_m': extension_m}))
        return True

    # ------------------------------------------------- hook observability --
    def is_hook_attached(self) -> bool:
        return self._attached

    def payload_altitude_m(self, color: str):
        z = self._payload_z
        if self._attached:
            self._payload_z += self.lift_per_read_m
        return z

    def hook_nose_ned_offset_m(self):
        """Hook nose position relative to the vehicle origin, as (north, east).

        This is the HOOK half of the visual-alignment error; the receiver half
        comes from the camera. Defaults to a hook hanging plumb under the body
        origin; set `hook_ned_offset` to model a rope-displaced hook, which is
        the case the visual servo exists to handle.
        """
        return self.hook_ned_offset

    def hook_to_receiver_offset_world(self, color: str):
        """World (d_east, d_north) from hook nose to receiver axis."""
        return self._hook_offset

    def hook_lateral_error_m(self, color: str):
        off = self.hook_to_receiver_offset_world(color)
        if off is None:
            return None
        return (off[0] ** 2 + off[1] ** 2) ** 0.5

    def magnet_gap_m(self, color: str):
        """Deprecated alias -- never measured a magnet. See GzPayloadActuator."""
        return self.hook_lateral_error_m(color)

    # ------------------------------------------------- release verification --
    async def get_released_payload_pose(self, shape_type: str):
        self.calls.append(('get_released_payload_pose', {'shape_type': shape_type}))
        return self._released_pose

    def get_released_payload_tilt_deg(self, shape_type: str):
        return 0.0
