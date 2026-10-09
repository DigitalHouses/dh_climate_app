from __future__ import annotations

from datetime import datetime, timezone
import unittest

from dh_climate_app.auto_fast import AutoFastClimateTargets
from dh_climate_app.devices import DesiredDeviceState
from dh_climate_app.ha_client import HaState


def actual(*, minimum=16, maximum=32, step=1):
    now = datetime.now(timezone.utc)
    return HaState(
        "climate.bedroom_ac",
        "off",
        {"min_temp": minimum, "max_temp": maximum, "target_temp_step": step},
        now,
        now,
    )


def demand(mode="heat", *, target=25.0, room=23.7):
    return DesiredDeviceState(
        entity_id="climate.bedroom_ac",
        domain="climate",
        hvac_mode=mode,
        target_temperature=target if mode != "off" else None,
        source="room:bedroom:fast",
        automatic_temperature=True,
        room_temperature=room,
    )


class AutoFastClimateTests(unittest.TestCase):
    def setUp(self):
        self.policy = AutoFastClimateTargets()
        self.states = {"climate.bedroom_ac": actual()}

    def target(self, desired, now=0):
        result = self.policy.apply([desired], self.states, now_monotonic=now)
        return result[0].target_temperature

    def test_heat_uses_room_error_to_boost_physical_target(self):
        self.assertEqual(29.0, self.target(demand()))

    def test_cool_uses_symmetric_negative_boost(self):
        self.assertEqual(21.0, self.target(demand("cool", target=26, room=28)))

    def test_device_limits_and_step(self):
        self.assertEqual(32, self.target(demand(target=31, room=22)))
        self.policy.reset()
        self.assertEqual(16, self.target(demand("cool", target=17, room=30)))

    def test_no_ir_chatter_from_room_temperature_changes(self):
        self.assertEqual(29, self.target(demand(target=25, room=24), now=0))
        self.assertEqual(29, self.target(demand(target=25, room=24.1), now=5))
        self.assertEqual(29, self.target(demand(target=25, room=24.2), now=100))

    def test_escalate_once_per_stalled_twenty_minute_window(self):
        self.assertEqual(29, self.target(demand(target=25, room=24), now=0))
        self.assertEqual(29, self.target(demand(target=25, room=24.0), now=1199))
        self.assertEqual(30, self.target(demand(target=25, room=24.0), now=1200))
        self.assertEqual(30, self.target(demand(target=25, room=24.0), now=1201))
        self.assertEqual(31, self.target(demand(target=25, room=24.0), now=2400))
        self.assertEqual(32, self.target(demand(target=25, room=24.0), now=3600))
        self.assertEqual(32, self.target(demand(target=25, room=24.0), now=4800))

    def test_progress_resets_stall_reference_without_sending_command(self):
        self.assertEqual(29, self.target(demand(target=25, room=24), now=0))
        self.assertEqual(29, self.target(demand(target=25, room=24.4), now=1200))
        self.assertEqual(30, self.target(demand(target=25, room=24.4), now=2400))

    def test_changed_room_target_starts_a_new_cycle(self):
        self.assertEqual(29, self.target(demand(target=25, room=24), now=0))
        self.assertEqual(30, self.target(demand(target=26, room=25), now=10))

    def test_off_and_restart_reset_cycle(self):
        self.assertEqual(29, self.target(demand(target=25, room=24), now=0))
        self.assertEqual(None, self.target(demand("off"), now=10))
        self.assertEqual(30, self.target(demand(target=25, room=23), now=20))
        self.policy.reset()
        self.assertEqual(28, self.target(demand(target=25, room=26), now=30))

    def test_missing_device_capability_never_guesses(self):
        self.states = {"climate.bedroom_ac": actual(step=None)}
        self.assertEqual(25, self.target(demand()))

    def test_other_climate_devices_are_not_transformed(self):
        generic = DesiredDeviceState(
            entity_id="climate.floor",
            domain="climate",
            hvac_mode="heat",
            target_temperature=27,
            source="room:bedroom:fast",
        )
        self.assertEqual(
            generic,
            self.policy.apply([generic], self.states, now_monotonic=0)[0],
        )


if __name__ == "__main__":
    unittest.main()
