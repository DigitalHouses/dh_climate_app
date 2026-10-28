"""Target-contract checks independent of historical options fixtures."""
import unittest

from dh_climate_app.config import ConfigError, configured_entity_ids, parse_options
from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.devices import compile_room_devices
from dh_climate_app.rooms import RoomState


def options(*devices, sensors=None, outdoor=None):
    return {
        "night_mode": "",
        "we_at_home": "",
        "outdoor": outdoor or {
            "temperature_sources": [
                "sensor.outdoor_a", "weather.forecast", "sensor.outdoor_b"
            ],
            "humidity_sources": ["weather.forecast", "sensor.outdoor_humidity"],
        },
        "rooms": [{
            "id": "bedroom",
            "name": "Спальня",
            "temperature_sensors": sensors or ["sensor.bedroom_air"],
            "humidity_sensors": [],
            "window_sensors": [],
            "devices": list(devices),
        }],
    }


def device(entity, role, control, **extra):
    payload = {"entity": entity, "role": role,
               "device_type": "virtual" if control == "app" else "hardware", **extra}
    if role == "slow_heat" and control == "app" and entity.startswith("switch."):
        payload.setdefault("screed_sensor_unavailable", "open")
    return payload


def state(season=Season.HEAT, action=HvacAction.IDLE, target=23.0):
    return RoomState(
        room_id="bedroom", name="Спальня",
        current_temperature=23.0, current_humidity=None,
        season=season, effective_profile=Profile.DAY,
        target_temperature=target, climate_control_enabled=True,
        control_action=action, hvac_mode=season.value, hvac_action=action,
        control_target_temperature=target,
    )


def compiled(config, room_state=None, **kwargs):
    return compile_room_devices(
        config=config,
        room_states={"bedroom": room_state or state()},
        humidity_states={}, outdoor_temperature=10.0, **kwargs,
    )


class TargetTopologyTests(unittest.TestCase):
    def test_nested_source_priority_and_room_lists(self):
        config = parse_options(options())
        self.assertEqual(config.outdoor.temperature_sources,
                         ("sensor.outdoor_a", "weather.forecast", "sensor.outdoor_b"))
        self.assertEqual(config.rooms[0].temperature_sensors,
                         ("sensor.bedroom_air",))

    def test_legacy_options_are_not_a_runtime_contract(self):
        with self.assertRaisesRegex(ConfigError, "obsolete"):
            parse_options({"outdoor_temperature_sources": "weather.forecast"})
        with self.assertRaises(ConfigError):
            parse_options(options(sensors="sensor.bedroom_air"))

    def test_duplicate_physical_ownership_fails(self):
        d = device("switch.floor", "slow_heat", "app",
                   actuator="normal_closed")
        with self.assertRaisesRegex(ConfigError, "duplicate physical"):
            parse_options(options(d, d))

    def test_device_rejects_switch(self):
        with self.assertRaisesRegex(ConfigError, "requires climate"):
            parse_options(options(device("switch.thermostat", "fast_heat", "device")))

    def test_slow_switch_requires_known_polarity(self):
        with self.assertRaisesRegex(ConfigError, "explicit actuator"):
            parse_options(options(device("switch.floor", "slow_heat", "app")))

    def test_slow_climate_app_is_not_assumed_autonomous(self):
        with self.assertRaisesRegex(ConfigError, "requires device_type=hardware"):
            parse_options(options(device("climate.floor", "slow_heat", "app")))

    def test_external_screed_sensor_requires_slow_switch(self):
        with self.assertRaisesRegex(ConfigError, "external screed"):
            parse_options(options(device(
                "climate.air", "fast_heat", "device",
                temperature_sensor="sensor.floor",
            )))

    def test_valid_screed_sensor_in_cache_allowlist(self):
        config = parse_options(options(device(
            "switch.floor", "slow_heat", "app", actuator="normal_closed",
            temperature_sensor="sensor.floor",
        )))
        self.assertIn("sensor.floor", configured_entity_ids(config))

    def test_slow_sensorless_nc_energized_only_in_heat(self):
        config = parse_options(options(device(
            "switch.floor", "slow_heat", "app", actuator="normal_closed",
        )))
        self.assertTrue(compiled(config)[0].power)
        self.assertFalse(compiled(config, state(season=Season.COOL))[0].power)

    def test_slow_sensorless_no_inverse_polarity(self):
        config = parse_options(options(device(
            "switch.floor", "slow_heat", "app", actuator="normal_open",
        )))
        self.assertFalse(compiled(config)[0].power)
        self.assertTrue(compiled(config, state(season=Season.OFF))[0].power)

    def test_screed_regulates_independently_from_room_air(self):
        config = parse_options(options(device(
            "switch.floor", "slow_heat", "app", actuator="normal_closed",
            temperature_sensor="sensor.floor",
        )))
        kw = {"slow_targets": {"bedroom": 27.0}}
        self.assertTrue(compiled(config, screed_values={"sensor.floor": 26.0}, **kw)[0].power)
        self.assertFalse(compiled(config, screed_values={"sensor.floor": 28.0}, **kw)[0].power)
        self.assertTrue(compiled(
            config, screed_values={"sensor.floor": "unavailable"}, **kw,
        )[0].power)

    def test_unseeded_slow_floor_does_not_invent_temperature(self):
        config = parse_options(options(device(
            "climate.floor", "slow_heat", "device",
        )))
        cmd = compiled(config)[0]
        self.assertEqual(cmd.hvac_mode, "off")
        self.assertIsNone(cmd.target_temperature)

    def test_slow_device_receives_numeric_setpoint(self):
        config = parse_options(options(device(
            "climate.floor", "slow_heat", "device",
        )))
        cmd = compiled(config, slow_targets={"bedroom": 27.0})[0]
        self.assertEqual((cmd.hvac_mode, cmd.target_temperature), ("heat", 27.0))

    def test_fast_device_does_not_pulse_on_room_idle(self):
        config = parse_options(options(device(
            "climate.radiator", "fast_heat", "device",
        )))
        cmd = compiled(config, state(action=HvacAction.IDLE))[0]
        self.assertEqual((cmd.hvac_mode, cmd.target_temperature), ("heat", 23.0))

    def test_fast_app_respects_room_idle(self):
        config = parse_options(options(device(
            "climate.ac", "fast_heat", "app",
        )))
        self.assertEqual(compiled(config, state(action=HvacAction.IDLE))[0].hvac_mode, "off")

    def test_reversible_has_one_desired_state_and_stale_outdoor_safety(self):
        config = parse_options(options(device(
            "climate.ac", "fast_heat", "app", reversible=True,
        )))
        self.assertEqual(len(config.rooms[0].devices), 1)
        demand = state(action=HvacAction.HEATING)
        cmd = compile_room_devices(
            config=config, room_states={"bedroom": demand}, humidity_states={},
            outdoor_temperature=None,
        )[0]
        self.assertEqual(cmd.hvac_mode, "off")

    def test_invalid_device_roles_and_flags(self):
        for extra in ({"reversible": True}, {"window_off": "yes"}):
            with self.subTest(extra=extra), self.assertRaises(ConfigError):
                parse_options(options(device("switch.floor", "fast_heat", "app", **extra)))


if __name__ == "__main__":
    unittest.main()
