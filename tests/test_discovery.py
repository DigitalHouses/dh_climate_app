from __future__ import annotations

import unittest
from datetime import datetime, timezone

from dh_climate_app.core import Season
from dh_climate_app.discovery import (
    diagnostic_discovery_payloads,
    season_discovery_payload,
    season_state_topics,
)
from dh_climate_app.outdoor import OutdoorState


class DiscoveryTests(unittest.TestCase):
    def test_season_climate_is_two_threshold_heat_cool(self) -> None:
        payload = season_discovery_payload("0.1.0")
        self.assertEqual(["heat_cool"], payload["modes"])
        self.assertIn("temperature_low_command_topic", payload)
        self.assertIn("temperature_high_command_topic", payload)
        self.assertEqual(
            ["dh_climate_app"],
            payload["device"]["identifiers"],
        )

    def test_common_diagnostics_exist(self) -> None:
        diagnostics = diagnostic_discovery_payloads("0.1.0")
        self.assertIn("version", diagnostics)
        self.assertIn("started_at", diagnostics)
        started = diagnostics["started_at"][1]
        self.assertEqual("timestamp", started["device_class"])
        self.assertEqual("diagnostic", started["entity_category"])

    def test_heat_maps_to_heating_action(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        state = OutdoorState(
            observed_at=now,
            current_temperature=10.0,
            current_humidity=50.0,
            avg_24h_temperature=10.5,
            avg_24h_humidity=49.0,
            temperature_source="primary",
            humidity_source="primary",
            heat_threshold=12.0,
            cool_threshold=20.0,
            hysteresis=0.5,
            season=Season.HEAT,
        )
        topics = season_state_topics(state)
        action_topic = next(
            topic for topic in topics if topic.endswith("/hvac_action")
        )
        self.assertEqual("heating", topics[action_topic])


if __name__ == "__main__":
    unittest.main()
