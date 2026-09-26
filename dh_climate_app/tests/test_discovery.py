from __future__ import annotations

import unittest
from datetime import datetime, timezone

from dh_climate_app.config import parse_options
from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.discovery import (
    diagnostic_discovery_payloads,
    room_climate_discovery_payload,
    ROOM_TARGET_KEYS,
    room_humidity_discovery_payload,
    room_target_discovery_payload,
    season_discovery_payload,
    season_state_topics,
)
from dh_climate_app.outdoor import OutdoorState
from dh_climate_app.rooms import RoomState
from test_config import options


class DiscoveryTests(unittest.TestCase):
    def test_season_climate_is_two_threshold_heat_cool(self) -> None:
        payload = season_discovery_payload("0.1.0")
        self.assertEqual(["heat_cool"], payload["modes"])
        self.assertIn("temperature_low_command_topic", payload)
        self.assertIn("temperature_high_command_topic", payload)
        self.assertEqual("all", payload["availability_mode"])
        self.assertEqual(2, len(payload["availability"]))
        self.assertEqual(
            ["dh_climate_app"],
            payload["device"]["identifiers"],
        )

    def test_common_diagnostics_exist(self) -> None:
        diagnostics = diagnostic_discovery_payloads("0.1.0")
        self.assertIn("version", diagnostics)
        self.assertIn("started_at", diagnostics)
        self.assertIn("problem", diagnostics)
        self.assertIn("delete_telemetry", diagnostics)
        delete = diagnostics["delete_telemetry"][1]
        self.assertEqual(
            "DigitalHouses/Global/dh_climate_app/system/set/delete_telemetry",
            delete["command_topic"],
        )
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

    def test_missing_numeric_state_clears_mqtt_value(self) -> None:
        now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        state = OutdoorState(
            observed_at=now,
            current_temperature=None,
            current_humidity=None,
            avg_24h_temperature=None,
            avg_24h_humidity=None,
            temperature_source=None,
            humidity_source=None,
            heat_threshold=12.0,
            cool_threshold=20.0,
            hysteresis=0.5,
            season=Season.OFF,
        )
        topics = season_state_topics(state)
        temperature_topic = next(
            topic for topic in topics
            if topic.endswith("/current_temperature")
        )
        self.assertEqual("None", topics[temperature_topic])

    def test_room_is_separate_mqtt_device(self) -> None:
        config = parse_options(options())
        room = config.rooms[0]
        state = RoomState(
            room_id=room.room_id,
            name=room.name,
            current_temperature=22,
            current_humidity=45,
            season=Season.HEAT,
            effective_profile=Profile.DAY,
            target_temperature=23,
            climate_control_enabled=True,
            control_action=HvacAction.HEATING,
            hvac_mode="auto",
            hvac_action=HvacAction.HEATING,
        )
        payload = room_climate_discovery_payload(room, state, "0.1.0")
        self.assertEqual(["off", "auto"], payload["modes"])
        self.assertEqual("all", payload["availability_mode"])
        self.assertEqual(2, len(payload["availability"]))
        self.assertEqual(
            ["dh_climate_app_room_living_room"],
            payload["device"]["identifiers"],
        )
        self.assertEqual("dh_climate_app", payload["device"]["via_device"])
        self.assertNotIn("preset_modes", payload)
        self.assertNotIn("preset_mode_state_topic", payload)
        self.assertNotIn("preset_mode_command_topic", payload)
        self.assertNotIn("fan_modes", payload)
        self.assertNotIn("fan_mode_state_topic", payload)
        self.assertNotIn("fan_mode_command_topic", payload)

        self.assertEqual(7, len(ROOM_TARGET_KEYS))
        target = room_target_discovery_payload(
            room,
            "0.1.5",
            target_key="heat_night",
            name="Heat night target",
        )
        self.assertEqual("config", target["entity_category"])
        self.assertEqual("temperature", target["device_class"])
        self.assertFalse(target["visible_by_default"])
        self.assertIn("availability_topic", target)
        self.assertNotIn("availability", target)
        self.assertEqual(
            "number.dh_climate_app_living_room_heat_night",
            target["default_entity_id"],
        )

    def test_dehumidifier_facade(self) -> None:
        config = parse_options(options())
        payload = room_humidity_discovery_payload(
            config.rooms[0],
            "0.1.0",
        )
        self.assertEqual("dehumidifier", payload["device_class"])
        self.assertIn("target_humidity_command_topic", payload)


if __name__ == "__main__":
    unittest.main()
