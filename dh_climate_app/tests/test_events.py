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

    def test_season_event_rounds_temperature_fields(self) -> None:
        engine = ClimateEventEngine()
        engine.observe(
            outdoor=outdoor(Season.OFF),
            weather=weather("none"),
            rooms={"livingroom": room()},
            problems=(),
            observed_at=NOW,
        )
        changed = outdoor(Season.HEAT)
        changed = OutdoorState(
            observed_at=changed.observed_at,
            current_temperature=20.943,
            current_humidity=changed.current_humidity,
            avg_24h_temperature=18.685370883826664,
            avg_24h_humidity=changed.avg_24h_humidity,
            temperature_source=changed.temperature_source,
            humidity_source=changed.humidity_source,
            heat_threshold=19.54,
            cool_threshold=24.96,
            hysteresis=0.54,
            season=changed.season,
        )
        events = engine.observe(
            outdoor=changed,
            weather=weather("none"),
            rooms={"livingroom": room()},
            problems=(),
            observed_at=NOW,
        )
        event = events[0]
        self.assertEqual(20.9, event["current_temperature"])
        self.assertEqual(18.7, event["avg_24h_temperature"])
        self.assertEqual(19.5, event["heat_threshold"])
        self.assertEqual(25.0, event["cool_threshold"])
        self.assertEqual(0.5, event["hysteresis"])

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

    def test_device_problem_event_keeps_room_context(self) -> None:
        engine = ClimateEventEngine()
        engine.observe(
            outdoor=outdoor(Season.HEAT),
            weather=weather("none"),
            rooms={"livingroom": room()},
            problems=(),
            observed_at=NOW,
        )
        problem = Problem(
            code="device_unavailable",
            scope="device",
            room_id="livingroom",
            entity_id="climate.fast",
            details="Home Assistant entity is unavailable",
        )

        events = engine.observe(
            outdoor=outdoor(Season.HEAT),
            weather=weather("none"),
            rooms={"livingroom": room()},
            problems=(problem,),
            observed_at=NOW,
        )

        event = events[0]
        self.assertEqual("problem_started", event["event_type"])
        self.assertEqual("device_unavailable", event["problem_id"])
        self.assertEqual("livingroom", event["room_id"])
        self.assertEqual("climate.fast", event["entity_id"])


if __name__ == "__main__":
    unittest.main()
