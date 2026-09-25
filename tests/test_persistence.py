from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dh_climate_app.config import parse_options
from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.persistence import StateStore
from test_config import options


class PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = StateStore(Path(self.temp_dir.name) / "dh_climate.db")
        self.config = parse_options(options())
        self.store.initialize(self.config)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_initial_seed(self) -> None:
        thresholds = self.store.get_season_thresholds()
        self.assertEqual(12.0, thresholds.heat)
        self.assertEqual(20.0, thresholds.cool)
        self.assertEqual(
            23.0,
            self.store.get_room_target("living_room", Season.HEAT, Profile.DAY),
        )
        self.assertEqual(50.0, self.store.get_humidity_target("living_room"))

    def test_runtime_changes_survive_reinitialize(self) -> None:
        self.store.set_season_thresholds(11.0, 21.0)
        self.store.set_room_target(
            "living_room", Season.HEAT, Profile.DAY, 24.0
        )
        self.store.set_previous_action("living_room", HvacAction.HEATING)
        self.store.initialize(self.config)

        thresholds = self.store.get_season_thresholds()
        self.assertEqual((11.0, 21.0), (thresholds.heat, thresholds.cool))
        self.assertEqual(
            24.0,
            self.store.get_room_target("living_room", Season.HEAT, Profile.DAY),
        )
        self.assertEqual(
            HvacAction.HEATING,
            self.store.get_previous_action("living_room"),
        )

    def test_outdoor_samples(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=2),
            value=10.0,
            source_name="primary",
        )
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now,
            value=12.0,
            source_name="primary",
        )
        rows = self.store.load_outdoor_samples(
            kind="temperature",
            since=now - timedelta(hours=24),
        )
        self.assertEqual([10.0, 12.0], [row.value for row in rows])
        self.assertTrue(self.store.integrity_check())

    def test_window_load_includes_last_sample_before_window(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=25),
            value=8.0,
            source_name="primary",
        )
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=12),
            value=16.0,
            source_name="primary",
        )
        rows = self.store.load_outdoor_samples(
            kind="temperature",
            since=now - timedelta(hours=24),
            include_previous=True,
        )
        self.assertEqual([8.0, 16.0], [row.value for row in rows])


if __name__ == "__main__":
    unittest.main()
