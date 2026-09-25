from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from dh_climate_app.core import (
    HvacAction,
    PrioritizedSource,
    Profile,
    Sample,
    Season,
    average_available,
    decide_season,
    effective_profile,
    fast_device_should_run,
    next_hvac_action,
    select_prioritized_value,
    slow_device_should_run,
    time_weighted_average,
)


class CoreTests(unittest.TestCase):
    def test_prioritized_source_falls_back(self) -> None:
        sources = [
            PrioritizedSource("primary", "sensor.primary"),
            PrioritizedSource("backup", "sensor.backup"),
        ]
        selected = select_prioritized_value(
            sources,
            {"sensor.primary": "unavailable", "sensor.backup": "12.5"},
        )
        self.assertEqual(("backup", 12.5), selected)

    def test_room_average_ignores_unavailable(self) -> None:
        self.assertEqual(22.0, average_available(["21.0", "unavailable", 23.0]))

    def test_time_weighted_average(self) -> None:
        end = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        samples = [
            Sample(end - timedelta(hours=24), 10.0),
            Sample(end - timedelta(hours=12), 20.0),
        ]
        self.assertAlmostEqual(15.0, time_weighted_average(samples, window_end=end))

    def test_season_contract(self) -> None:
        self.assertEqual(
            Season.HEAT,
            decide_season(10.0, heat_threshold=12.0, cool_threshold=20.0, hysteresis=0.5),
        )
        self.assertEqual(
            Season.OFF,
            decide_season(15.0, heat_threshold=12.0, cool_threshold=20.0, hysteresis=0.5),
        )
        self.assertEqual(
            Season.COOL,
            decide_season(21.0, heat_threshold=12.0, cool_threshold=20.0, hysteresis=0.5),
        )

    def test_profile_precedence(self) -> None:
        self.assertEqual(
            Profile.ANTIFREEZE,
            effective_profile(
                season=Season.HEAT,
                climate_control_enabled=False,
                we_at_home=False,
                night_mode=True,
            ),
        )
        self.assertEqual(
            Profile.AWAY,
            effective_profile(
                season=Season.COOL,
                climate_control_enabled=True,
                we_at_home=False,
                night_mode=True,
            ),
        )

    def test_heat_hysteresis_is_stateful(self) -> None:
        self.assertEqual(
            HvacAction.HEATING,
            next_hvac_action(
                season=Season.HEAT,
                current_temperature=21.0,
                target_temperature=22.0,
                hysteresis=0.5,
                previous_action=HvacAction.IDLE,
            ),
        )
        self.assertEqual(
            HvacAction.HEATING,
            next_hvac_action(
                season=Season.HEAT,
                current_temperature=22.0,
                target_temperature=22.0,
                hysteresis=0.5,
                previous_action=HvacAction.HEATING,
            ),
        )
        self.assertEqual(
            HvacAction.IDLE,
            next_hvac_action(
                season=Season.HEAT,
                current_temperature=22.5,
                target_temperature=22.0,
                hysteresis=0.5,
                previous_action=HvacAction.HEATING,
            ),
        )

    def test_device_classes(self) -> None:
        self.assertTrue(
            fast_device_should_run(function=Season.HEAT, room_action=HvacAction.HEATING)
        )
        self.assertFalse(
            fast_device_should_run(function=Season.HEAT, room_action=HvacAction.IDLE)
        )
        self.assertTrue(slow_device_should_run(season=Season.HEAT))
        self.assertFalse(slow_device_should_run(season=Season.COOL))


if __name__ == "__main__":
    unittest.main()
