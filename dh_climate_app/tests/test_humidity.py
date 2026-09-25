from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dh_climate_app.config import parse_options
from dh_climate_app.humidity import HumidityEngine, next_humidity_active
from dh_climate_app.persistence import StateStore
from test_config import options


class HumidityTests(unittest.TestCase):
    def test_dehumidifier_hysteresis(self) -> None:
        self.assertTrue(
            next_humidity_active(
                controller_type="dehumidifier",
                current_humidity=55,
                target_humidity=50,
                hysteresis=3,
                previous_active=False,
            )
        )
        self.assertTrue(
            next_humidity_active(
                controller_type="dehumidifier",
                current_humidity=51,
                target_humidity=50,
                hysteresis=3,
                previous_active=True,
            )
        )
        self.assertFalse(
            next_humidity_active(
                controller_type="dehumidifier",
                current_humidity=47,
                target_humidity=50,
                hysteresis=3,
                previous_active=True,
            )
        )

    def test_engine(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = parse_options(options())
            store = StateStore(Path(directory) / "dh_climate.db")
            store.initialize(config)
            engine = HumidityEngine(config=config, store=store)
            state = engine.evaluate_all(
                {"sensor.living_room_humidity": "55"}
            )["living_room"]
            self.assertTrue(state.active)
            self.assertEqual("drying", state.action)


if __name__ == "__main__":
    unittest.main()
