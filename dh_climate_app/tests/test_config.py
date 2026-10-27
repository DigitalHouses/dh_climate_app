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
    """Only the new declarative Supervisor contract is accepted at runtime."""

    @staticmethod
    def target() -> dict:
        return {
            "night_mode": "input_boolean.night_mode",
            "we_at_home": "input_boolean.we_at_home",
            "outdoor": {
                "temperature_sources": [
                    "sensor.outdoor_temperature", "weather.secondary",
                    "sensor.outdoor_temperature",
                ],
                "humidity_sources": ["sensor.outdoor_humidity"],
            },
            "rooms": [{
                "id": "living_room",
                "name": "Гостиная",
                "temperature_sensors": ["sensor.living_room_temperature"],
                "humidity_sensors": ["sensor.living_room_humidity"],
                "window_sensors": [],
                "devices": [
                    {"entity": "switch.radiator", "role": "fast_heat", "control": "app"},
                    {"entity": "climate.floor", "role": "slow_heat", "control": "device"},
                    {"entity": "climate.ac", "role": "fast_heat", "control": "app",
                     "reversible": True},
                ],
                "humidity_mode": "dehumidifier",
                "humidity_actuator": "switch.dehumidifier",
            }],
            "log_level": "info",
        }

    def test_parse_valid_options(self):
        config = parse_options(self.target())
        self.assertEqual("living_room", config.rooms[0].room_id)
        self.assertEqual(DeviceClass.SLOW, config.rooms[0].devices[1].device_class)
        self.assertEqual(
            ("sensor.outdoor_temperature", "weather.secondary"),
            config.outdoor.temperature_sources,
        )
        self.assertEqual(
            ("sensor.living_room_temperature",), config.rooms[0].temperature_sensors,
        )

    def test_configured_entity_ids_contains_all_bindings(self):
        config = parse_options(self.target())
        found = configured_entity_ids(config)
        self.assertIn("climate.floor", found)
        self.assertIn("sensor.outdoor_humidity", found)
        self.assertIn("switch.dehumidifier", found)

    def test_initial_installation_without_rooms_is_safe(self):
        data = self.target()
        data["rooms"] = []
        data["outdoor"] = {"temperature_sources": [], "humidity_sources": []}
        config = parse_options(data)
        self.assertEqual((), config.rooms)
        self.assertEqual((), config.outdoor.temperature_sources)

    def test_old_csv_and_operational_parameters_are_rejected(self):
        data = self.target()
        data["temperature_hysteresis"] = 0.5
        with self.assertRaisesRegex(ConfigError, "obsolete"):
            parse_options(data)
        del data["temperature_hysteresis"]
        data["rooms"][0]["temperature_sensors"] = "sensor.living_room_temperature"
        with self.assertRaises(ConfigError):
            parse_options(data)

    def test_legacy_room_device_keys_are_rejected(self):
        data = self.target()
        data["rooms"][0]["slow_target"] = 27
        with self.assertRaisesRegex(ConfigError, "obsolete"):
            parse_options(data)

    def test_reversible_single_physical_owner(self):
        config = parse_options(self.target())
        ac = next(d for d in config.rooms[0].devices if d.entity_id == "climate.ac")
        self.assertEqual("heat_cool", ac.function)
        self.assertEqual(1, sum(d.entity_id == "climate.ac" for d in config.rooms[0].devices))

    def test_duplicate_room_or_actuator_rejected(self):
        data = self.target()
        data["rooms"].append(dict(data["rooms"][0]))
        with self.assertRaisesRegex(ConfigError, "duplicates"):
            parse_options(data)
        data = self.target()
        data["rooms"][0]["devices"].append(
            {"entity": "switch.radiator", "role": "fast_cool", "control": "app"}
        )
        with self.assertRaisesRegex(ConfigError, "duplicate physical"):
            parse_options(data)

    def test_humidity_requires_sensors_and_explicit_actuator(self):
        data = self.target()
        data["rooms"][0]["humidity_sensors"] = []
        with self.assertRaises(ConfigError):
            parse_options(data)
        data = self.target()
        data["rooms"][0]["humidity_actuator"] = "switch.radiator"
        with self.assertRaisesRegex(ConfigError, "owned"):
            parse_options(data)


if __name__ == "__main__":
    unittest.main()
