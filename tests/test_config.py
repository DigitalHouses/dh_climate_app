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
        },
        "outdoor_sources": [
            {
                "name": "primary",
                "temperature": "sensor.outdoor_temperature",
                "humidity": "sensor.outdoor_humidity",
            }
        ],
        "rooms": [
            {
                "id": "living_room",
                "name": "Living room",
                "temperature_sensors": "sensor.living_room_temperature",
                "humidity_sensors": "sensor.living_room_humidity",
                "window_sensors": "",
                "heat_day": 23,
                "heat_night": 22,
                "heat_away": 18,
                "heat_antifreeze": 10,
                "cool_day": 24,
                "cool_night": 24,
                "cool_away": 28,
            }
        ],
        "devices": [
            {
                "room_id": "living_room",
                "entity_id": "climate.floor",
                "class": "slow",
                "function": "heat",
                "target_temperature": 27,
                "window_policy": "ignore",
            },
            {
                "room_id": "living_room",
                "entity_id": "switch.radiator",
                "class": "fast",
                "function": "heat",
                "window_policy": "ignore",
            },
        ],
        "humidity_controls": [
            {
                "room_id": "living_room",
                "type": "dehumidifier",
                "target_default": 50,
                "actuator_entity_id": "switch.dehumidifier",
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
        self.assertEqual("dehumidifier", config.rooms[0].humidity.controller_type)

    def test_comma_separated_sensor_lists(self) -> None:
        raw = options()
        raw["rooms"][0]["temperature_sensors"] = (
            "sensor.room_a, sensor.room_b"
        )
        raw["rooms"][0]["window_sensors"] = (
            "binary_sensor.window_a,binary_sensor.window_b"
        )
        config = parse_options(raw)
        self.assertEqual(
            ("sensor.room_a", "sensor.room_b"),
            config.rooms[0].temperature_sensors,
        )
        self.assertEqual(
            ("binary_sensor.window_a", "binary_sensor.window_b"),
            config.rooms[0].window_sensors,
        )

    def test_configured_entity_ids_contains_all_bindings(self) -> None:
        raw = options()
        raw["rooms"][0]["window_sensors"] = "binary_sensor.window"
        config = parse_options(raw)
        entity_ids = configured_entity_ids(config)
        self.assertIn("sensor.outdoor_temperature", entity_ids)
        self.assertIn("sensor.living_room_temperature", entity_ids)
        self.assertIn("binary_sensor.window", entity_ids)
        self.assertIn("climate.floor", entity_ids)
        self.assertIn("switch.dehumidifier", entity_ids)

    def test_empty_installation_config_is_safe(self) -> None:
        raw = options()
        raw["outdoor_sources"] = []
        raw["rooms"] = []
        raw["devices"] = []
        raw["humidity_controls"] = []
        config = parse_options(raw)
        self.assertEqual((), config.outdoor.sources)
        self.assertEqual((), config.rooms)
        self.assertEqual(
            frozenset(
                {
                    "input_boolean.night_mode",
                    "input_boolean.we_at_home",
                }
            ),
            configured_entity_ids(config),
        )

    def test_slow_climate_requires_target(self) -> None:
        raw = options()
        raw["devices"][0].pop("target_temperature")
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_switch_cannot_be_heat_cool(self) -> None:
        raw = options()
        raw["devices"][1]["function"] = "heat_cool"
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_humidity_control_requires_sensor(self) -> None:
        raw = options()
        raw["rooms"][0]["humidity_sensors"] = ""
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_slow_switch_is_rejected(self) -> None:
        raw = options()
        raw["devices"][0] = {
            "room_id": "living_room",
            "entity_id": "switch.floor",
            "class": "slow",
            "function": "heat",
            "window_policy": "ignore",
        }
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_same_actuator_cannot_be_owned_twice(self) -> None:
        raw = options()
        raw["humidity_controls"][0]["actuator_entity_id"] = "switch.radiator"
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_device_must_reference_existing_room(self) -> None:
        raw = options()
        raw["devices"][0]["room_id"] = "missing"
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_low_outdoor_limit_requires_heat_capability(self) -> None:
        raw = options()
        raw["devices"][1]["function"] = "cool"
        raw["devices"][1]["min_heating_outdoor_temperature"] = -10
        with self.assertRaises(ConfigError):
            parse_options(raw)


if __name__ == "__main__":
    unittest.main()
