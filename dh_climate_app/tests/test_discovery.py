from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from dh_climate_app.config import parse_options
from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.discovery import (
    diagnostic_discovery_payloads,
    outdoor_discovery_payloads,
    outdoor_state_topics,
    weather_discovery_payloads,
    room_climate_discovery_payload,
    room_climate_state_topics,
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
        self.assertIn("event", diagnostics)
        event = diagnostics["event"][1]
        self.assertEqual("event", event["default_entity_id"].split(".")[0])
        self.assertEqual(1, event["qos"])
        self.assertIn("precipitation_type_changed", event["event_types"])
        self.assertIn("problem_recovered", event["event_types"])
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

        attrs_topic = next(
            topic for topic in topics if topic.endswith("/attributes")
        )
        attrs = json.loads(topics[attrs_topic])
        self.assertEqual(10.0, attrs["current_temperature"])
        self.assertEqual(10.5, attrs["avg_24h_temperature"])
        self.assertEqual(12.0, attrs["heat_threshold"])
        self.assertEqual(20.0, attrs["cool_threshold"])
        self.assertEqual(0.5, attrs["hysteresis"])

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
            hvac_mode="heat",
            hvac_action=HvacAction.HEATING,
        )
        payload = room_climate_discovery_payload(room, state, "0.1.0")
        self.assertEqual(["off", "heat", "cool"], payload["modes"])
        self.assertEqual("all", payload["availability_mode"])
        self.assertEqual(2, len(payload["availability"]))
        self.assertEqual(
            ["dh_climate_app_room_living_room"],
            payload["device"]["identifiers"],
        )
        self.assertEqual("dh_climate_app", payload["device"]["via_device"])
        self.assertEqual(["day", "night", "away"], payload["preset_modes"])
        self.assertEqual(
            "DigitalHouses/Global/dh_climate_app/rooms/living_room/climate/profile",
            payload["preset_mode_state_topic"],
        )
        self.assertEqual(
            "DigitalHouses/Global/dh_climate_app/rooms/living_room/climate/set/profile",
            payload["preset_mode_command_topic"],
        )
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
        self.assertEqual(
            [{"topic": "DigitalHouses/Global/dh_climate_app/availability"}],
            target["availability"],
        )
        self.assertEqual("all", target["availability_mode"])
        self.assertEqual(
            "number.dh_climate_app_living_room_heat_night",
            target["default_entity_id"],
        )

    def test_room_state_exposes_profile_and_native_action(self) -> None:
        state = RoomState(
            room_id="living_room",
            name="Living Room",
            current_temperature=21.0,
            current_humidity=45.0,
            season=Season.HEAT,
            effective_profile=Profile.AWAY,
            target_temperature=18.0,
            climate_control_enabled=True,
            control_action=HvacAction.IDLE,
            hvac_mode="heat",
            hvac_action=HvacAction.IDLE,
        )
        topics = room_climate_state_topics(
            state,
            published_profile="away",
            published_target=18.0,
        )
        base = "DigitalHouses/Global/dh_climate_app/rooms/living_room/climate"
        self.assertEqual("heat", topics[f"{base}/hvac_mode"])
        self.assertEqual("idle", topics[f"{base}/hvac_action"])
        self.assertEqual("away", topics[f"{base}/profile"])
        self.assertEqual("18.0", topics[f"{base}/target_temperature"])

    def test_room_discovery_capabilities_are_stable_across_seasons(self) -> None:
        config = parse_options(options())
        room = config.rooms[0]
        for season in (Season.HEAT, Season.COOL, Season.OFF):
            with self.subTest(season=season):
                state = RoomState(
                    room_id=room.room_id,
                    name=room.name,
                    current_temperature=22.0,
                    current_humidity=45.0,
                    season=season,
                    effective_profile=Profile.DAY,
                    target_temperature=None if season is Season.OFF else 24.0,
                    climate_control_enabled=True,
                    control_action=HvacAction.IDLE,
                    hvac_mode=(
                        "off"
                        if season is Season.OFF
                        else season.value
                    ),
                    hvac_action=(
                        HvacAction.OFF
                        if season is Season.OFF
                        else HvacAction.IDLE
                    ),
                )
                payload = room_climate_discovery_payload(room, state, "0.1.16")
                self.assertEqual(["off", "heat", "cool"], payload["modes"])

    def test_outdoor_ui_sensors_use_current_values(self) -> None:
        discovery = outdoor_discovery_payloads("0.1.9")
        temperature = discovery["outdoor_temperature"][1]
        humidity = discovery["outdoor_humidity"][1]

        self.assertEqual(
            "sensor.dh_climate_app_outdoor_temperature",
            temperature["default_entity_id"],
        )
        self.assertEqual("temperature", temperature["device_class"])
        self.assertEqual("measurement", temperature["state_class"])
        self.assertEqual("°C", temperature["unit_of_measurement"])

        self.assertEqual(
            "sensor.dh_climate_app_outdoor_humidity",
            humidity["default_entity_id"],
        )
        self.assertEqual("humidity", humidity["device_class"])
        self.assertEqual("measurement", humidity["state_class"])
        self.assertEqual("%", humidity["unit_of_measurement"])

        now = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
        state = OutdoorState(
            observed_at=now,
            current_temperature=20.9,
            current_humidity=39.0,
            avg_24h_temperature=18.685370883826664,
            avg_24h_humidity=42.0,
            temperature_source="weather.forecast_home_assistant",
            humidity_source="weather.forecast_home_assistant",
            heat_threshold=15.0,
            cool_threshold=20.0,
            hysteresis=0.5,
            season=Season.OFF,
        )
        topics = outdoor_state_topics(state)
        self.assertEqual(
            "20.9",
            topics["DigitalHouses/Global/dh_climate_app/outdoor/temperature"],
        )
        self.assertEqual(
            "39.0",
            topics["DigitalHouses/Global/dh_climate_app/outdoor/humidity"],
        )
        attrs = json.loads(
            topics["DigitalHouses/Global/dh_climate_app/outdoor/attributes"]
        )
        self.assertEqual(18.7, attrs["avg_24h_temperature"])

    def test_weather_precipitation_discovery(self) -> None:
        weather = weather_discovery_payloads("0.1.8")
        precipitation_type = weather["precipitation_type"][1]
        precipitation_amount = weather["precipitation_amount"][1]
        self.assertEqual(
            "sensor.dh_climate_app_precipitation_type",
            precipitation_type["default_entity_id"],
        )
        self.assertEqual(
            "sensor.dh_climate_app_precipitation_amount",
            precipitation_amount["default_entity_id"],
        )
        self.assertEqual("precipitation", precipitation_amount["device_class"])
        self.assertEqual("mm", precipitation_amount["unit_of_measurement"])

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
