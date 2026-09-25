from __future__ import annotations

import unittest

from dh_climate_app.config import parse_options
from dh_climate_app.core import Season
from dh_climate_app.discovery import (
    diagnostic_discovery,
    room_climate_discovery,
    room_humidity_discovery,
    season_climate_discovery,
)
from test_config import options


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = parse_options(options())
        self.room = self.config.rooms[0]

    def test_season_facade_preserves_two_threshold_contract(self) -> None:
        topic, payload = season_climate_discovery("0.1.0")
        self.assertEqual(
            "homeassistant/climate/dh_climate_outdoor_season/config",
            topic,
        )
        self.assertEqual(["heat_cool"], payload["modes"])
        self.assertIn("temperature_low_command_topic", payload)
        self.assertIn("temperature_high_command_topic", payload)

    def test_room_is_its_own_mqtt_device(self) -> None:
        _, payload = room_climate_discovery(
            self.room,
            season=Season.HEAT,
            app_version="0.1.0",
        )
        self.assertEqual(
            ["dh_climate_app_room_living_room"],
            payload["device"]["identifiers"],
        )
        self.assertEqual(["off", "heat"], payload["modes"])
        self.assertEqual(
            "climate.dh_climate_living_room",
            payload["default_entity_id"],
        )

    def test_room_modes_follow_global_season(self) -> None:
        _, heat = room_climate_discovery(
            self.room,
            season=Season.HEAT,
            app_version="0.1.0",
        )
        _, cool = room_climate_discovery(
            self.room,
            season=Season.COOL,
            app_version="0.1.0",
        )
        _, off = room_climate_discovery(
            self.room,
            season=Season.OFF,
            app_version="0.1.0",
        )
        self.assertEqual(["off", "heat"], heat["modes"])
        self.assertEqual(["off", "cool"], cool["modes"])
        self.assertEqual(["off"], off["modes"])

    def test_optional_dehumidifier_stays_on_room_device(self) -> None:
        result = room_humidity_discovery(self.room, app_version="0.1.0")
        self.assertIsNotNone(result)
        _, payload = result
        self.assertEqual("dehumidifier", payload["device_class"])
        self.assertEqual(
            ["dh_climate_app_room_living_room"],
            payload["device"]["identifiers"],
        )
        self.assertEqual(
            "humidifier.dh_climate_living_room_humidity",
            payload["default_entity_id"],
        )

    def test_runtime_diagnostics_are_on_system_device(self) -> None:
        diagnostics = diagnostic_discovery("0.1.0")
        self.assertEqual(
            ["dh_climate_app"],
            diagnostics["version"][1]["device"]["identifiers"],
        )
        self.assertEqual(
            "timestamp",
            diagnostics["started_at"][1]["device_class"],
        )


if __name__ == "__main__":
    unittest.main()
