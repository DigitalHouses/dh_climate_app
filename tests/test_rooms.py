from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dh_climate_app.config import parse_options
from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.persistence import StateStore
from dh_climate_app.rooms import ProfileEditOverlay, RoomEngine
from test_config import options


class RoomEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = parse_options(options())
        self.store = StateStore(Path(self.temp_dir.name) / "dh_climate.db")
        self.store.initialize(self.config)
        self.engine = RoomEngine(config=self.config, store=self.store)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_heat_room_demands_heat(self) -> None:
        states = {
            "sensor.living_room_temperature": "21.0",
            "sensor.living_room_humidity": "45",
            "input_boolean.we_at_home": "on",
            "input_boolean.night_mode": "off",
        }
        room = self.engine.evaluate_all(states, season=Season.HEAT)["living_room"]
        self.assertEqual(Profile.DAY, room.effective_profile)
        self.assertEqual(23.0, room.target_temperature)
        self.assertEqual(HvacAction.HEATING, room.control_action)
        self.assertEqual(HvacAction.HEATING, room.hvac_action)
        self.assertEqual("heat", room.hvac_mode)

    def test_heat_off_hides_action_but_retains_antifreeze(self) -> None:
        self.store.set_climate_control_enabled("living_room", False)
        states = {
            "sensor.living_room_temperature": "5",
            "sensor.living_room_humidity": "45",
        }
        room = self.engine.evaluate_all(states, season=Season.HEAT)["living_room"]
        self.assertEqual(Profile.ANTIFREEZE, room.effective_profile)
        self.assertEqual(10.0, room.target_temperature)
        self.assertEqual(HvacAction.HEATING, room.control_action)
        self.assertEqual(HvacAction.OFF, room.hvac_action)
        self.assertEqual("off", room.hvac_mode)

    def test_cool_off_is_real_off(self) -> None:
        self.store.set_climate_control_enabled("living_room", False)
        room = self.engine.evaluate_all(
            {"sensor.living_room_temperature": "30"},
            season=Season.COOL,
        )["living_room"]
        self.assertEqual(HvacAction.OFF, room.control_action)
        self.assertEqual("off", room.hvac_mode)


class ProfileOverlayTests(unittest.TestCase):
    def test_overlay_expires(self) -> None:
        overlay = ProfileEditOverlay(idle_timeout_seconds=10)
        overlay.select(
            "room",
            Profile.NIGHT,
            effective_profile=Profile.DAY,
            now_monotonic=100,
        )
        self.assertEqual(
            Profile.NIGHT,
            overlay.selected(
                "room",
                effective_profile=Profile.DAY,
                now_monotonic=105,
            ),
        )
        self.assertEqual(
            Profile.DAY,
            overlay.selected(
                "room",
                effective_profile=Profile.DAY,
                now_monotonic=111,
            ),
        )


if __name__ == "__main__":
    unittest.main()
