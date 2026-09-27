from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from dh_climate_app.config import parse_options
from dh_climate_app.core import Sample, Season
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
        self.assertEqual("sensor.outdoor_temperature", state.temperature_source)
        self.assertEqual(10.0, state.avg_24h_temperature)
        self.assertEqual(Season.HEAT, state.season)

    def test_weather_entity_uses_temperature_and_humidity_attributes(self) -> None:
        raw = options()
        raw["outdoor_temperature_sources"] = "weather.forecast_home_assistant"
        raw["outdoor_humidity_sources"] = "weather.forecast_home_assistant"
        config = parse_options(raw)
        engine = OutdoorEngine(
            config=config.outdoor,
            store=self.store,
            hysteresis=config.global_config.hysteresis,
        )
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        state = engine.evaluate(
            {
                "weather.forecast_home_assistant": SimpleNamespace(
                    state="partlycloudy",
                    attributes={"temperature": 9.5, "humidity": 73},
                )
            },
            observed_at=now,
        )
        self.assertEqual(9.5, state.current_temperature)
        self.assertEqual(73.0, state.current_humidity)
        self.assertEqual(
            "weather.forecast_home_assistant",
            state.temperature_source,
        )
        self.assertEqual(
            "weather.forecast_home_assistant",
            state.humidity_source,
        )

    def test_priority_falls_back_to_second_source(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        state = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "unavailable",
                "sensor.weather_temperature": "11.5",
                "sensor.outdoor_humidity": "45",
            },
            observed_at=now,
        )
        self.assertEqual("sensor.weather_temperature", state.temperature_source)
        self.assertEqual(11.5, state.current_temperature)

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

    def test_temperature_avg24_empty_history_starts_at_live_temperature(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.engine.bootstrap_temperature_history(
            [],
            source_name="sensor.dh_climate_app_outdoor_temperature",
        )

        state = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "18.2",
                "sensor.outdoor_humidity": "50",
            },
            observed_at=now,
            record_sample=True,
        )

        self.assertEqual(18.2, state.avg_24h_temperature)

    def test_temperature_avg24_recorder_bootstrap_matches_statistics_mean(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.engine.bootstrap_temperature_history(
            [
                Sample(now - timedelta(hours=23), 20.0),
                Sample(now - timedelta(hours=1), 10.0),
            ],
            source_name="sensor.dh_climate_app_outdoor_temperature",
        )

        state = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "10",
                "sensor.outdoor_humidity": "50",
            },
            observed_at=now,
            record_sample=True,
        )

        # HA Statistics restores the two Recorder samples, then receives the
        # App's startup publication of the current public temperature.
        self.assertAlmostEqual((20.0 + 10.0 + 10.0) / 3.0, state.avg_24h_temperature)

    def test_temperature_avg24_samples_public_one_decimal_transitions(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.engine.bootstrap_temperature_history(
            [],
            source_name="sensor.dh_climate_app_outdoor_temperature",
        )

        first = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "10.01",
                "sensor.outdoor_humidity": "50",
            },
            observed_at=now,
            record_sample=True,
        )
        same_public_value = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "10.04",
                "sensor.outdoor_humidity": "50",
            },
            observed_at=now + timedelta(minutes=1),
            record_sample=True,
        )
        next_public_value = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "10.06",
                "sensor.outdoor_humidity": "50",
            },
            observed_at=now + timedelta(minutes=2),
            record_sample=True,
        )

        self.assertEqual(10.0, first.avg_24h_temperature)
        self.assertEqual(10.0, same_public_value.avg_24h_temperature)
        self.assertAlmostEqual(10.05, next_public_value.avg_24h_temperature)

    def test_temperature_avg24_matches_statistics_mean(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=23),
            value=20.0,
            source_name="primary",
        )
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=1),
            value=10.0,
            source_name="primary",
        )

        state = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "10",
                "sensor.outdoor_humidity": "50",
            },
            observed_at=now,
            record_sample=False,
        )

        self.assertEqual(15.0, state.avg_24h_temperature)

    def test_temperature_avg24_ignores_sample_before_window(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=24, seconds=1),
            value=30.0,
            source_name="primary",
        )
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=20),
            value=20.0,
            source_name="primary",
        )
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(minutes=1),
            value=10.0,
            source_name="primary",
        )

        state = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "10",
                "sensor.outdoor_humidity": "50",
            },
            observed_at=now,
            record_sample=False,
        )

        self.assertEqual(15.0, state.avg_24h_temperature)

    def test_temperature_avg24_survives_engine_restart(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        for hours, value in ((23, 9.0), (8, 15.0), (1, 21.0)):
            self.store.add_outdoor_sample(
                kind="temperature",
                observed_at=now - timedelta(hours=hours),
                value=value,
                source_name="primary",
            )

        restarted = OutdoorEngine(
            config=self.config.outdoor,
            store=self.store,
            hysteresis=self.config.global_config.hysteresis,
        )
        state = restarted.evaluate(
            {
                "sensor.outdoor_temperature": "21",
                "sensor.outdoor_humidity": "50",
            },
            observed_at=now,
            record_sample=False,
        )

        self.assertEqual(15.0, state.avg_24h_temperature)

    def test_temperature_mean_crossing_changes_season(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=23),
            value=20.0,
            source_name="primary",
        )
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=1),
            value=0.0,
            source_name="primary",
        )

        state = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "0",
                "sensor.outdoor_humidity": "50",
            },
            observed_at=now,
            record_sample=False,
        )

        self.assertEqual(10.0, state.avg_24h_temperature)
        self.assertEqual(Season.HEAT, state.season)

    def test_all_live_sources_unavailable_forces_off(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(hours=1),
            value=5.0,
            source_name="primary",
        )
        state = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "unavailable",
                "sensor.outdoor_humidity": "unavailable",
            },
            observed_at=now,
            record_sample=False,
        )
        self.assertEqual(Season.OFF, state.season)
        self.assertFalse(state.available)
        self.assertIsNotNone(state.avg_24h_temperature)

    def test_threshold_change_is_persistent(self) -> None:
        self.engine.set_thresholds(heat=8.0, cool=22.0)
        thresholds = self.store.get_season_thresholds()
        self.assertEqual((8.0, 22.0), (thresholds.heat, thresholds.cool))


if __name__ == "__main__":
    unittest.main()
