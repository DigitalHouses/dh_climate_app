from __future__ import annotations

import unittest

from dh_climate_app.config import ConfigError, configured_entity_ids, parse_options
from dh_climate_app.core import DeviceClass, Profile


def options() -> dict:
    return {
        "hysteresis": 0.5,
        "humidity_hysteresis": 3.0,
        "night_mode": "input_boolean.night_mode",
        "we_at_home": "input_boolean.we_at_home",
        "heat_threshold_default": 12.0,
        "cool_threshold_default": 20.0,
        "outdoor_temperature_sources": (
            "sensor.outdoor_temperature, sensor.weather_temperature"
        ),
        "outdoor_humidity_sources": "sensor.outdoor_humidity",
        "rooms": [
            {
                "id": "living_room",
                "name": "Living room",
                "temperature_sensors": "sensor.living_room_temperature",
                "humidity_sensors": "sensor.living_room_humidity",
                "heat_day": 23,
                "heat_night": 22,
                "heat_away": 18,
                "heat_antifreeze": 10,
                "cool_day": 24,
                "cool_night": 24,
                "cool_away": 28,
                "fast_heat": "switch.radiator",
                "fast_cool": "climate.living_room_ac",
                "slow_heat": "climate.floor",
                "slow_target": 27,
                "humidity_mode": "dehumidifier",
                "humidity_target": 50,
                "humidity_actuator": "switch.dehumidifier",
            }
        ],
        "telemetry_enabled": False,
        "log_level": "info",
    }


class ConfigTests(unittest.TestCase):
    def test_parse_valid_options(self) -> None:
        config = parse_options(options())
        self.assertEqual(0.5, config.global_config.hysteresis)
        self.assertEqual(
            ("sensor.outdoor_temperature", "sensor.weather_temperature"),
            config.outdoor.temperature_sources,
        )
        self.assertEqual("living_room", config.rooms[0].room_id)
        self.assertEqual(DeviceClass.FAST, config.rooms[0].devices[0].device_class)
        self.assertEqual(DeviceClass.SLOW, config.rooms[0].devices[-1].device_class)
        self.assertEqual(27.0, config.rooms[0].devices[-1].target_temperature)
        self.assertEqual(10.0, config.rooms[0].targets.heat[Profile.ANTIFREEZE])

    def test_configured_entity_ids_contains_all_bindings(self) -> None:
        config = parse_options(options())
        entity_ids = configured_entity_ids(config)
        self.assertIn("sensor.outdoor_temperature", entity_ids)
        self.assertIn("sensor.living_room_temperature", entity_ids)
        self.assertIn("climate.floor", entity_ids)
        self.assertIn("switch.dehumidifier", entity_ids)

    def test_empty_installation_config_is_safe(self) -> None:
        raw = options()
        raw["outdoor_temperature_sources"] = ""
        raw["outdoor_humidity_sources"] = ""
        raw["rooms"] = []
        config = parse_options(raw)
        self.assertEqual((), config.outdoor.temperature_sources)
        self.assertEqual((), config.outdoor.humidity_sources)
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

    def test_comma_lists_keep_order_and_deduplicate(self) -> None:
        raw = options()
        raw["outdoor_temperature_sources"] = (
            "sensor.first, sensor.second, sensor.first"
        )
        config = parse_options(raw)
        self.assertEqual(
            ("sensor.first", "sensor.second"),
            config.outdoor.temperature_sources,
        )

    def test_fast_climate_can_be_heat_and_cool(self) -> None:
        raw = options()
        raw["rooms"][0]["fast_heat"] = "climate.heatpump"
        raw["rooms"][0]["fast_cool"] = "climate.heatpump"
        config = parse_options(raw)
        device = next(
            item
            for item in config.rooms[0].devices
            if item.entity_id == "climate.heatpump"
        )
        self.assertEqual("heat_cool", device.function)

    def test_switch_cannot_be_heat_and_cool(self) -> None:
        raw = options()
        raw["rooms"][0]["fast_heat"] = "switch.reversible"
        raw["rooms"][0]["fast_cool"] = "switch.reversible"
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_slow_requires_explicit_target(self) -> None:
        raw = options()
        raw["rooms"][0].pop("slow_target")
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_active_humidity_requires_explicit_target(self) -> None:
        raw = options()
        raw["rooms"][0].pop("humidity_target")
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_room_targets_follow_facade_range(self) -> None:
        raw = options()
        raw["rooms"][0]["heat_day"] = 40
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_slow_requires_climate_domain(self) -> None:
        raw = options()
        raw["rooms"][0]["slow_heat"] = "switch.floor"
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_humidity_control_requires_sensor(self) -> None:
        raw = options()
        raw["rooms"][0]["humidity_sensors"] = ""
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_same_actuator_cannot_be_owned_twice(self) -> None:
        raw = options()
        raw["rooms"][0]["humidity_actuator"] = "switch.radiator"
        with self.assertRaises(ConfigError):
            parse_options(raw)


if __name__ == "__main__":
    unittest.main()
