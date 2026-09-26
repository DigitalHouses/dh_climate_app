from __future__ import annotations

import unittest
from datetime import datetime, timezone

from dh_climate_app.ha_client import HaState
from dh_climate_app.weather import (
    build_weather_state,
    precipitation_type_from_condition,
    select_weather_source,
)


class WeatherTests(unittest.TestCase):
    def test_precipitation_condition_mapping(self) -> None:
        self.assertEqual("rain", precipitation_type_from_condition("rainy"))
        self.assertEqual("rain", precipitation_type_from_condition("pouring"))
        self.assertEqual("snow", precipitation_type_from_condition("snowy"))
        self.assertEqual("mixed", precipitation_type_from_condition("snowy-rainy"))
        self.assertEqual("hail", precipitation_type_from_condition("hail"))
        self.assertEqual("none", precipitation_type_from_condition("cloudy"))

    def test_first_configured_weather_entity_is_used(self) -> None:
        self.assertEqual(
            "weather.home",
            select_weather_source(
                ("sensor.outdoor", "weather.home"),
                ("weather.backup",),
            ),
        )

    def test_hourly_precipitation_is_normalized_to_mm(self) -> None:
        now = datetime(2026, 9, 26, 11, 30, tzinfo=timezone.utc)
        state = HaState(
            entity_id="weather.home",
            state="rainy",
            attributes={"precipitation_unit": "in"},
            last_changed=now,
            last_updated=now,
        )
        response = {
            "service_response": {
                "weather.home": {
                    "forecast": [
                        {
                            "datetime": "2026-09-26T11:00:00+00:00",
                            "condition": "rainy",
                            "precipitation": 0.1,
                        },
                        {
                            "datetime": "2026-09-26T12:00:00+00:00",
                            "condition": "rainy",
                            "precipitation": 0.2,
                        },
                    ]
                }
            }
        }

        weather = build_weather_state(
            source_entity="weather.home",
            ha_state=state,
            hourly_forecast_response=response,
            observed_at=now,
        )
        assert weather is not None
        self.assertEqual("rain", weather.precipitation_type)
        self.assertAlmostEqual(2.54, weather.precipitation_mm or 0.0, places=3)
        self.assertEqual(
            "2026-09-26T11:00:00+00:00",
            weather.forecast_at.isoformat() if weather.forecast_at else None,
        )


if __name__ == "__main__":
    unittest.main()
