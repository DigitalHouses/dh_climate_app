from __future__ import annotations

import tempfile
from copy import deepcopy
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

    def test_upgrade_keeps_targets_and_thresholds_and_seeds_new_room(self) -> None:
        self.store.set_season_thresholds(11.0, 22.0)
        self.store.set_room_target("living_room", Season.HEAT, Profile.AWAY, 19.5)
        self.store.set_room_target("living_room", Season.COOL, Profile.NIGHT, 26.5)
        self.store.set_humidity_target("living_room", 57.0)
        raw = deepcopy(options())
        for key in ("heat_threshold_default", "cool_threshold_default", "hysteresis"):
            raw.pop(key, None)
        raw["temperature_hysteresis"] = 0.5
        for room in raw["rooms"]:
            for key in ("heat_day", "heat_night", "heat_away", "heat_antifreeze",
                        "cool_day", "cool_night", "cool_away", "humidity_target"):
                room.pop(key, None)
        new_room = deepcopy(raw["rooms"][0])
        new_room.update(id="new_room", name="Новая комната", fast_heat="",
                        fast_cool="", slow_heat="", humidity_mode="off",
                        humidity_actuator="")
        raw["rooms"].append(new_room)
        updated_config = parse_options(raw)
        self.store.initialize(updated_config)
        self.store.initialize(updated_config)
        thresholds = self.store.get_season_thresholds()
        self.assertEqual((11.0, 22.0), (thresholds.heat, thresholds.cool))
        self.assertEqual(19.5, self.store.get_room_target("living_room", Season.HEAT, Profile.AWAY))
        self.assertEqual(26.5, self.store.get_room_target("living_room", Season.COOL, Profile.NIGHT))
        self.assertEqual(57.0, self.store.get_humidity_target("living_room"))
        self.assertEqual(23.0, self.store.get_room_target("new_room", Season.HEAT, Profile.DAY))
        self.assertEqual(30.0, self.store.get_room_target("new_room", Season.COOL, Profile.AWAY))
        self.assertTrue(self.store.integrity_check())

    def test_season_bound_preserves_old_out_of_range_row(self) -> None:
        with self.store.connect() as db:
            db.execute("UPDATE season_settings SET cool_threshold=29.8 WHERE singleton=1")
        self.store.initialize(self.config)
        self.assertEqual(29.8, self.store.get_season_thresholds().cool)
        for heat, cool in ((4.9, 20), (10, 25.1), (25, 25), (20, 19)):
            with self.assertRaises(ValueError):
                self.store.set_season_thresholds(heat, cool)
        self.assertEqual(29.8, self.store.get_season_thresholds().cool)
        self.store.set_season_thresholds(10, 25)

    def test_metadata_round_trip(self) -> None:
        self.assertIsNone(self.store.get_metadata("outdoor_filter"))
        self.store.set_metadata("outdoor_filter", "ema_minute_v1")
        self.assertEqual(
            "ema_minute_v1",
            self.store.get_metadata("outdoor_filter"),
        )

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

    def test_prune_keeps_one_pre_window_baseline(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=30),
            value=5.0,
            source_name="primary",
        )
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=26),
            value=8.0,
            source_name="primary",
        )
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=12),
            value=16.0,
            source_name="primary",
        )
        deleted = self.store.prune_outdoor_samples(now=now)
        self.assertEqual(1, deleted)
        rows = self.store.load_outdoor_samples(
            kind="temperature",
            since=now - timedelta(hours=24),
            include_previous=True,
        )
        self.assertEqual([8.0, 16.0], [row.value for row in rows])


if __name__ == "__main__":
    unittest.main()
