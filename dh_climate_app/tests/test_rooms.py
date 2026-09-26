from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dh_climate_app.config import parse_options
from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.persistence import StateStore
from dh_climate_app.rooms import RoomEngine, aggregate_window_state
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


    def test_window_aggregation_matches_legacy_contract(self) -> None:
        self.assertEqual(
            "not_configured",
            aggregate_window_state((), {}),
        )
        sensors = (
            "binary_sensor.window_a",
            "binary_sensor.window_b",
        )
        self.assertEqual(
            "closed",
            aggregate_window_state(
                sensors,
                {
                    "binary_sensor.window_a": "off",
                    "binary_sensor.window_b": "closed",
                },
            ),
        )
        self.assertEqual(
            "unknown",
            aggregate_window_state(
                sensors,
                {
                    "binary_sensor.window_a": "off",
                    "binary_sensor.window_b": "unavailable",
                },
            ),
        )
        self.assertEqual(
            "open",
            aggregate_window_state(
                sensors,
                {
                    "binary_sensor.window_a": "unavailable",
                    "binary_sensor.window_b": "on",
                },
            ),
        )

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
        self.assertEqual("auto", room.hvac_mode)

    def test_heat_off_hides_action_but_retains_antifreeze(self) -> None:
        self.store.set_climate_control_enabled("living_room", False)
        states = {
            "sensor.living_room_temperature": "5",
            "sensor.living_room_humidity": "45",
            "input_boolean.we_at_home": "on",
            "input_boolean.night_mode": "off",
        }
        room = self.engine.evaluate_all(states, season=Season.HEAT)["living_room"]
        self.assertEqual(Profile.DAY, room.effective_profile)
        self.assertEqual(23.0, room.target_temperature)
        self.assertEqual(Profile.ANTIFREEZE, room.control_profile)
        self.assertEqual(10.0, room.control_target_temperature)
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

    def test_interseason_room_stays_readable_but_off(self) -> None:
        room = self.engine.evaluate_all(
            {
                "sensor.living_room_temperature": "22",
                "input_boolean.we_at_home": "on",
                "input_boolean.night_mode": "off",
            },
            season=Season.OFF,
        )["living_room"]
        self.assertTrue(room.available)
        self.assertEqual("off", room.hvac_mode)
        self.assertEqual(HvacAction.OFF, room.hvac_action)
        self.assertIsNone(room.target_temperature)

    def test_unavailable_presence_uses_away_profile(self) -> None:
        room = self.engine.evaluate_all(
            {
                "sensor.living_room_temperature": "20",
                "input_boolean.we_at_home": "unavailable",
                "input_boolean.night_mode": "off",
            },
            season=Season.HEAT,
        )["living_room"]
        self.assertEqual(Profile.AWAY, room.effective_profile)
        self.assertEqual(18.0, room.target_temperature)


if __name__ == "__main__":
    unittest.main()
