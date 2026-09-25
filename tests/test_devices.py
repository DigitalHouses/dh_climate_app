from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dh_climate_app.config import parse_options
from dh_climate_app.devices import compile_room_devices
from dh_climate_app.core import Season
from dh_climate_app.humidity import HumidityEngine
from dh_climate_app.persistence import StateStore
from dh_climate_app.rooms import RoomEngine
from test_config import options


class DeviceCompilerTests(unittest.TestCase):
    def _build(self, raw: dict, states: dict, season: Season):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        config = parse_options(raw)
        store = StateStore(Path(directory.name) / "dh_climate.db")
        store.initialize(config)
        room_engine = RoomEngine(config=config, store=store)
        humidity_engine = HumidityEngine(config=config, store=store)
        rooms = room_engine.evaluate_all(states, season=season)
        humidity = humidity_engine.evaluate_all(states)
        return config, rooms, humidity

    def test_fast_slow_and_humidity(self) -> None:
        raw = options()
        states = {
            "sensor.living_room_temperature": "21",
            "sensor.living_room_humidity": "55",
            "input_boolean.we_at_home": "on",
            "input_boolean.night_mode": "off",
        }
        config, rooms, humidity = self._build(raw, states, Season.HEAT)
        desired = compile_room_devices(
            config=config,
            room_states=rooms,
            humidity_states=humidity,
            outdoor_temperature=5.0,
        )
        by_id = {item.entity_id: item for item in desired}

        self.assertEqual("heat", by_id["climate.floor"].hvac_mode)
        self.assertEqual(27.0, by_id["climate.floor"].target_temperature)
        self.assertTrue(by_id["switch.radiator"].power)
        self.assertTrue(by_id["switch.dehumidifier"].power)

    def test_open_window_inhibits_only_selected_device(self) -> None:
        raw = options()
        room = raw["rooms"][0]
        room["window_sensors"] = "binary_sensor.window"
        room["window_off_devices"] = "switch.radiator"

        states = {
            "sensor.living_room_temperature": "21",
            "sensor.living_room_humidity": "45",
            "binary_sensor.window": "on",
            "input_boolean.we_at_home": "on",
            "input_boolean.night_mode": "off",
        }
        config, rooms, humidity = self._build(raw, states, Season.HEAT)
        desired = compile_room_devices(
            config=config,
            room_states=rooms,
            humidity_states=humidity,
            outdoor_temperature=5.0,
        )
        by_id = {item.entity_id: item for item in desired}

        # SLOW floor is not listed in window_off_devices.
        self.assertEqual("heat", by_id["climate.floor"].hvac_mode)
        # FAST radiator is explicitly stopped.
        self.assertFalse(by_id["switch.radiator"].power)
        # Window is context only: thermostat truth remains heating.
        self.assertEqual("heating", rooms["living_room"].control_action.value)

    def test_low_outdoor_temperature_inhibits_reversible_climate(self) -> None:
        raw = options()
        room = raw["rooms"][0]
        room["fast_heat"] = "switch.radiator, climate.living_room_ac"
        room["fast_cool"] = "climate.living_room_ac"
        raw["ac_min_outdoor_temperature"] = -10.0

        states = {
            "sensor.living_room_temperature": "21",
            "sensor.living_room_humidity": "45",
            "input_boolean.we_at_home": "on",
            "input_boolean.night_mode": "off",
        }
        config, rooms, humidity = self._build(raw, states, Season.HEAT)

        desired = compile_room_devices(
            config=config,
            room_states=rooms,
            humidity_states=humidity,
            outdoor_temperature=-15.0,
        )
        by_id = {item.entity_id: item for item in desired}
        self.assertEqual("off", by_id["climate.living_room_ac"].hvac_mode)

        desired = compile_room_devices(
            config=config,
            room_states=rooms,
            humidity_states=humidity,
            outdoor_temperature=-5.0,
        )
        by_id = {item.entity_id: item for item in desired}
        self.assertEqual("heat", by_id["climate.living_room_ac"].hvac_mode)


if __name__ == "__main__":
    unittest.main()
