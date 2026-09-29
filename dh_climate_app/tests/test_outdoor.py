from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from math import exp
from pathlib import Path
from types import SimpleNamespace

from dh_climate_app.config import parse_options
from dh_climate_app.core import Season
from dh_climate_app.outdoor import (
    TEMPERATURE_HISTORY_MODE_EMA_MINUTE_V1,
    TEMPERATURE_HISTORY_MODE_KEY,
    OutdoorEngine,
)
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

    def _states(self, temperature: object, humidity: object = "50") -> dict:
        return {
            "sensor.outdoor_temperature": temperature,
            "sensor.outdoor_humidity": humidity,
        }

    def _alpha(self) -> float:
        return 1.0 - exp(
            -60.0 / (self.config.outdoor.temperature_ema_minutes * 60.0)
        )

    def test_primary_source_seeds_ema_and_avg24(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        state = self.engine.evaluate(
            self._states("10.0"),
            observed_at=now,
        )
        self.assertEqual("sensor.outdoor_temperature", state.temperature_source)
        self.assertEqual(10.0, state.raw_temperature)
        self.assertEqual(10.0, state.current_temperature)
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
        self.assertEqual(9.5, state.raw_temperature)
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
        self.assertEqual(11.5, state.raw_temperature)
        self.assertEqual(11.5, state.current_temperature)

    def test_ema_waits_one_minute_and_smooths_step(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        first = self.engine.evaluate(
            self._states("10"),
            observed_at=now,
        )
        before_tick = self.engine.evaluate(
            self._states("20"),
            observed_at=now + timedelta(seconds=30),
            record_sample=False,
        )
        after_tick = self.engine.evaluate(
            self._states("20"),
            observed_at=now + timedelta(minutes=1),
            record_sample=False,
        )

        expected = 10.0 + self._alpha() * 10.0
        self.assertEqual(10.0, first.current_temperature)
        self.assertEqual(20.0, before_tick.raw_temperature)
        self.assertEqual(10.0, before_tick.current_temperature)
        self.assertAlmostEqual(expected, after_tick.current_temperature)

    def test_source_switch_uses_the_same_ema_path(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        first = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "10",
                "sensor.weather_temperature": "20",
                "sensor.outdoor_humidity": "50",
            },
            observed_at=now,
        )
        switched = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "unavailable",
                "sensor.weather_temperature": "20",
                "sensor.outdoor_humidity": "50",
            },
            observed_at=now + timedelta(seconds=10),
        )
        after_tick = self.engine.evaluate(
            {
                "sensor.outdoor_temperature": "unavailable",
                "sensor.weather_temperature": "20",
                "sensor.outdoor_humidity": "50",
            },
            observed_at=now + timedelta(minutes=1),
            record_sample=False,
        )

        expected = 10.0 + self._alpha() * 10.0
        self.assertEqual("sensor.outdoor_temperature", first.temperature_source)
        self.assertEqual("sensor.weather_temperature", switched.temperature_source)
        self.assertEqual(20.0, switched.raw_temperature)
        self.assertEqual(10.0, switched.current_temperature)
        self.assertAlmostEqual(expected, after_tick.current_temperature)

    def test_temperature_history_samples_each_minute_even_when_public_rounding_is_same(
        self,
    ) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.engine.evaluate(self._states("10.0"), observed_at=now)
        self.engine.evaluate(
            self._states("10.02"),
            observed_at=now + timedelta(minutes=1),
            record_sample=False,
        )

        samples = self.store.load_outdoor_samples(
            kind="temperature",
            since=now - timedelta(seconds=1),
        )
        self.assertEqual(2, len(samples))
        self.assertEqual(10.0, round(samples[0].value, 1))
        self.assertEqual(10.0, round(samples[1].value, 1))

    def test_avg24_uses_equal_cadence_filtered_samples(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        first = self.engine.evaluate(self._states("10"), observed_at=now)
        second = self.engine.evaluate(
            self._states("20"),
            observed_at=now + timedelta(minutes=1),
            record_sample=False,
        )
        third = self.engine.evaluate(
            self._states("20"),
            observed_at=now + timedelta(minutes=2),
            record_sample=False,
        )

        alpha = self._alpha()
        filtered_1 = 10.0
        filtered_2 = filtered_1 + alpha * (20.0 - filtered_1)
        filtered_3 = filtered_2 + alpha * (20.0 - filtered_2)
        expected_avg = (filtered_1 + filtered_2 + filtered_3) / 3.0

        self.assertEqual(10.0, first.avg_24h_temperature)
        self.assertAlmostEqual(filtered_2, second.current_temperature)
        self.assertAlmostEqual(filtered_3, third.current_temperature)
        self.assertAlmostEqual(expected_avg, third.avg_24h_temperature)

    def test_legacy_history_is_replayed_to_ema_minute_grid(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(minutes=2),
            value=10.0,
            source_name="legacy",
        )
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=now - timedelta(minutes=1),
            value=20.0,
            source_name="legacy",
        )

        state = self.engine.evaluate(
            self._states("20"),
            observed_at=now,
            record_sample=False,
        )

        alpha = self._alpha()
        first_tick = 10.0 + alpha * 10.0
        second_tick = first_tick + alpha * (20.0 - first_tick)
        samples = self.store.load_outdoor_samples(
            kind="temperature",
            since=now - timedelta(minutes=3),
        )

        self.assertEqual(
            TEMPERATURE_HISTORY_MODE_EMA_MINUTE_V1,
            self.store.get_metadata(TEMPERATURE_HISTORY_MODE_KEY),
        )
        self.assertEqual(3, len(samples))
        self.assertAlmostEqual(second_tick, state.current_temperature)
        self.assertEqual(20.0, state.raw_temperature)

    def test_restart_restores_filter_without_catching_up_downtime(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.engine.evaluate(self._states("10"), observed_at=now)
        before_restart = self.engine.evaluate(
            self._states("20"),
            observed_at=now + timedelta(minutes=1),
            record_sample=False,
        )

        restarted = OutdoorEngine(
            config=self.config.outdoor,
            store=self.store,
            hysteresis=self.config.global_config.hysteresis,
        )
        restored = restarted.evaluate(
            self._states("30"),
            observed_at=now + timedelta(minutes=10),
            record_sample=False,
        )

        self.assertAlmostEqual(
            before_restart.current_temperature,
            restored.current_temperature,
        )
        self.assertEqual(30.0, restored.raw_temperature)

    def test_temperature_mean_crossing_changes_season(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.store.set_metadata(
            TEMPERATURE_HISTORY_MODE_KEY,
            TEMPERATURE_HISTORY_MODE_EMA_MINUTE_V1,
        )
        for minutes in (2, 1):
            self.store.add_outdoor_sample(
                kind="temperature",
                observed_at=now - timedelta(minutes=minutes),
                value=10.0,
                source_name="filtered",
            )

        engine = OutdoorEngine(
            config=self.config.outdoor,
            store=self.store,
            hysteresis=self.config.global_config.hysteresis,
        )
        state = engine.evaluate(
            self._states("10"),
            observed_at=now,
            record_sample=False,
        )

        self.assertEqual(10.0, state.avg_24h_temperature)
        self.assertEqual(Season.HEAT, state.season)

    def test_all_live_sources_unavailable_forces_off(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.engine.evaluate(self._states("5"), observed_at=now)
        state = self.engine.evaluate(
            self._states("unavailable", "unavailable"),
            observed_at=now + timedelta(minutes=1),
            record_sample=False,
        )
        self.assertEqual(Season.OFF, state.season)
        self.assertFalse(state.available)
        self.assertIsNone(state.raw_temperature)
        self.assertIsNone(state.current_temperature)
        self.assertIsNotNone(state.avg_24h_temperature)

    def test_threshold_change_is_persistent(self) -> None:
        self.engine.set_thresholds(heat=8.0, cool=22.0)
        thresholds = self.store.get_season_thresholds()
        self.assertEqual((8.0, 22.0), (thresholds.heat, thresholds.cool))


if __name__ == "__main__":
    unittest.main()
