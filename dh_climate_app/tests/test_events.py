from __future__ import annotations

import unittest
from datetime import datetime, timezone

from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.events import ClimateEventEngine
from dh_climate_app.outdoor import OutdoorState
from dh_climate_app.problems import Problem
from dh_climate_app.rooms import RoomState
from dh_climate_app.weather import WeatherState


NOW = datetime(2026, 9, 26, 11, 0, tzinfo=timezone.utc)


def outdoor(season: Season) -> OutdoorState:
    return OutdoorState(
        observed_at=NOW,
        current_temperature=10.0,
        current_humidity=80.0,
        avg_24h_temperature=10.0,
        avg_24h_humidity=75.0,
        temperature_source="weather.home",
        humidity_source="weather.home",
        heat_threshold=12.0,
        cool_threshold=20.0,
        hysteresis=0.5,
        season=season,
    )


def weather(kind: str, amount: float | None = None) -> WeatherState:
    condition = {
        "none": "cloudy",
        "rain": "rainy",
        "snow": "snowy",
        "mixed": "snowy-rainy",
    }[kind]
    return WeatherState(
        source_entity="weather.home",
        condition=condition,
        precipitation_type=kind,
        precipitation_mm=amount,
        forecast_at=NOW,
        observed_at=NOW,
    )


def room(window: str = "closed") -> RoomState:
    return RoomState(
        room_id="livingroom",
        name="Living Room",
        current_temperature=22.0,
        current_humidity=None,
        season=Season.HEAT,
        effective_profile=Profile.DAY,
        target_temperature=23.0,
        climate_control_enabled=True,
        control_action=HvacAction.HEATING,
        hvac_mode="auto",
        hvac_action=HvacAction.HEATING,
        window_state=window,
    )


class ClimateEventTests(unittest.TestCase):
    def test_first_observation_is_baseline(self) -> None:
        engine = ClimateEventEngine()
        events = engine.observe(
            outdoor=outdoor(Season.HEAT),
            weather=weather("none"),
            rooms={"livingroom": room()},
            problems=(),
            observed_at=NOW,
        )
        self.assertEqual((), events)

    def test_rain_to_snow_is_type_change(self) -> None:
        engine = ClimateEventEngine()
        engine.observe(
            outdoor=outdoor(Season.HEAT),
            weather=weather("rain", 1.2),
            rooms={"livingroom": room()},
            problems=(),
            observed_at=NOW,
        )
        events = engine.observe(
            outdoor=outdoor(Season.HEAT),
            weather=weather("snow", 0.8),
            rooms={"livingroom": room()},
            problems=(),
            observed_at=NOW,
        )
        self.assertEqual("precipitation_type_changed", events[0]["event_type"])
        self.assertEqual("rain", events[0]["previous_type"])
        self.assertEqual("snow", events[0]["current_type"])
        self.assertEqual(0.8, events[0]["precipitation_mm"])
        self.assertEqual(2, events[0]["schema_version"])

    def test_precipitation_start_and_stop(self) -> None:
        engine = ClimateEventEngine()
        engine.observe(
            outdoor=outdoor(Season.OFF),
            weather=weather("none"),
            rooms={"livingroom": room()},
            problems=(),
            observed_at=NOW,
        )
        started = engine.observe(
            outdoor=outdoor(Season.OFF),
            weather=weather("rain", 2.0),
            rooms={"livingroom": room()},
            problems=(),
            observed_at=NOW,
        )
        stopped = engine.observe(
            outdoor=outdoor(Season.OFF),
            weather=weather("none", 0.0),
            rooms={"livingroom": room()},
            problems=(),
            observed_at=NOW,
        )
        self.assertEqual("precipitation_started", started[0]["event_type"])
        self.assertEqual("precipitation_stopped", stopped[0]["event_type"])

    def test_season_window_and_problem_transitions(self) -> None:
        engine = ClimateEventEngine()
        engine.observe(
            outdoor=outdoor(Season.OFF),
            weather=weather("none"),
            rooms={"livingroom": room("closed")},
            problems=(),
            observed_at=NOW,
        )
        problem = Problem(
            code="room_temperature_unavailable",
            scope="room",
            room_id="livingroom",
        )
        events = engine.observe(
            outdoor=outdoor(Season.HEAT),
            weather=weather("none"),
            rooms={"livingroom": room("open")},
            problems=(problem,),
            observed_at=NOW,
        )
        self.assertEqual(
            {"season_changed", "window_opened", "problem_started"},
            {event["event_type"] for event in events},
        )
        recovered = engine.observe(
            outdoor=outdoor(Season.HEAT),
            weather=weather("none"),
            rooms={"livingroom": room("closed")},
            problems=(),
            observed_at=NOW,
        )
        self.assertEqual(
            {"window_closed", "problem_recovered"},
            {event["event_type"] for event in recovered},
        )


if __name__ == "__main__":
    unittest.main()
