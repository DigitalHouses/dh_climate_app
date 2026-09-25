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
    def test_fast_slow_and_humidity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = parse_options(options())
            store = StateStore(Path(directory) / "dh_climate.db")
            store.initialize(config)
            room_engine = RoomEngine(config=config, store=store)
            humidity_engine = HumidityEngine(config=config, store=store)
            states = {
                "sensor.living_room_temperature": "21",
                "sensor.living_room_humidity": "55",
                "input_boolean.we_at_home": "on",
                "input_boolean.night_mode": "off",
            }
            rooms = room_engine.evaluate_all(states, season=Season.HEAT)
            humidity = humidity_engine.evaluate_all(states)
            desired = compile_room_devices(
                config=config,
                room_states=rooms,
                humidity_states=humidity,
            )
            by_id = {item.entity_id: item for item in desired}

            self.assertEqual("heat", by_id["climate.floor"].hvac_mode)
            self.assertEqual(27.0, by_id["climate.floor"].target_temperature)
            self.assertTrue(by_id["switch.radiator"].power)
            self.assertTrue(by_id["switch.dehumidifier"].power)


if __name__ == "__main__":
    unittest.main()
