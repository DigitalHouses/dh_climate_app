from __future__ import annotations

import unittest

from dh_climate_app.config import ConfigError, configured_entity_ids, parse_options
from dh_climate_app.core import DeviceClass, Profile


def options() -> dict:
    return {
        "global": {
            "hysteresis": 0.5,
            "humidity_hysteresis": 3.0,
            "night_mode": "input_boolean.night_mode",
            "we_at_home": "input_boolean.we_at_home",
        },
        "outdoor": {
            "heat_threshold_default": 12.0,
            "cool_threshold_default": 20.0,
            "sources": [
                {
                    "name": "primary",
                    "temperature": "sensor.outdoor_temperature",
                    "humidity": "sensor.outdoor_humidity",
                }
            ],
        },
        "rooms": [
            {
                "id": "living_room",
                "name": "Living room",
                "temperature_sensors": ["sensor.living_room_temperature"],
                "humidity_sensors": ["sensor.living_room_humidity"],
                "targets": {
                    "heat": {
                        "day": 23,
                        "night": 22,
                        "away": 18,
                        "antifreeze": 10,
                    },
                    "cool": {"day": 24, "night": 24, "away": 28},
                },
                "devices": [
                    {
                        "entity_id": "climate.floor",
                        "class": "slow",
                        "function": "heat",
                        "target_temperature": 27,
                    },
                    {
                        "entity_id": "switch.radiator",
                        "class": "fast",
                        "function": "heat",
                    },
                ],
                "humidity": {
                    "enabled": True,
                    "type": "dehumidifier",
                    "target_default": 50,
                    "actuator": {"entity_id": "switch.dehumidifier"},
                },
            }
        ],
        "telemetry_enabled": False,
        "log_level": "info",
    }


class ConfigTests(unittest.TestCase):
    def test_parse_valid_options(self) -> None:
        config = parse_options(options())
        self.assertEqual(0.5, config.global_config.hysteresis)
        self.assertEqual("primary", config.outdoor.sources[0].name)
        self.assertEqual("living_room", config.rooms[0].room_id)
        self.assertEqual(DeviceClass.SLOW, config.rooms[0].devices[0].device_class)
        self.assertEqual(10.0, config.rooms[0].targets.heat[Profile.ANTIFREEZE])

    def test_configured_entity_ids_contains_all_bindings(self) -> None:
        config = parse_options(options())
        entity_ids = configured_entity_ids(config)
        self.assertIn("sensor.outdoor_temperature", entity_ids)
        self.assertIn("sensor.living_room_temperature", entity_ids)
        self.assertIn("climate.floor", entity_ids)
        self.assertIn("switch.dehumidifier", entity_ids)

    def test_slow_climate_requires_target(self) -> None:
        raw = options()
        raw["rooms"][0]["devices"][0].pop("target_temperature")
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_switch_cannot_be_heat_cool(self) -> None:
        raw = options()
        raw["rooms"][0]["devices"][1]["function"] = "heat_cool"
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_humidity_control_requires_sensor(self) -> None:
        raw = options()
        raw["rooms"][0]["humidity_sensors"] = []
        with self.assertRaises(ConfigError):
            parse_options(raw)


if __name__ == "__main__":
    unittest.main()
