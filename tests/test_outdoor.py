from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dh_climate_app.config import parse_options
from dh_climate_app.core import Season
from dh_climate_app.outdoor import OutdoorEngine
from dh_climate_app.persistence import StateStore
from test_config import options


class OutdoorEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = parse_options(options())
        self.store = StateStore(Path(self.temp_dir.name) / "dh_climate.db")
        self.store.initialize(self.config)
        self.engine = OutdoorEngine(
            config=self.config.outdoor,
            store=self.store,
            hysteresis=self.config.global_config.hysteresis,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_primary_source_and_avg24(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        state = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "10.0",
                "sensor.outdoor_humidity": "50",
            },
            observed_at=now,
        )
        self.assertEqual("primary", state.temperature_source)
        self.assertEqual(10.0, state.avg_24h_temperature)
        self.assertEqual(Season.HEAT, state.season)

    def test_rolling_average_changes_season(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=24),
            value=10.0,
            source_name="primary",
        )
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=12),
            value=22.0,
            source_name="primary",
        )
        state = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "22",
                "sensor.outdoor_humidity": "50",
            },
            observed_at=now,
            record_sample=False,
        )
        self.assertAlmostEqual(16.0, state.avg_24h_temperature)
        self.assertEqual(Season.OFF, state.season)

    def test_threshold_change_is_persistent(self) -> None:
        self.engine.set_thresholds(heat=8.0, cool=22.0)
        thresholds = self.store.get_season_thresholds()
        self.assertEqual((8.0, 22.0), (thresholds.heat, thresholds.cool))


if __name__ == "__main__":
    unittest.main()
