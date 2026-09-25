from __future__ import annotations

from typing import Any

from .config import RoomConfig
from .core import Season


DISCOVERY_PREFIX = "homeassistant"
BASE_TOPIC = "DigitalHouses/Global/dh_climate_app"
SYSTEM_DEVICE_ID = "dh_climate_app"
MANUFACTURER = "Digital Houses"
MODEL = "DH Climate App"
ORIGIN_NAME = "DigitalHouses Climate App"
SUPPORT_URL = "https://github.com/DigitalHouses/dh_climate_app"


def _origin(app_version: str) -> dict[str, Any]:
    return {
        "name": ORIGIN_NAME,
        "sw_version": app_version,
        "support_url": SUPPORT_URL,
    }


def system_device(app_version: str) -> dict[str, Any]:
    return {
        "identifiers": [SYSTEM_DEVICE_ID],
        "name": "DigitalHouses Climate",
        "manufacturer": MANUFACTURER,
        "model": MODEL,
        "sw_version": app_version,
    }


def room_device(room: RoomConfig, app_version: str) -> dict[str, Any]:
    return {
        "identifiers": [f"dh_climate_app_room_{room.room_id}"],
        "name": f"DH Climate · {room.name}",
        "manufacturer": MANUFACTURER,
        "model": "DH Climate Room",
        "sw_version": app_version,
        "via_device": SYSTEM_DEVICE_ID,
    }


def discovery_topic(platform: str, object_id: str) -> str:
    return f"{DISCOVERY_PREFIX}/{platform}/{object_id}/config"


def _allowed_room_modes(season: Season) -> list[str]:
    if season is Season.HEAT:
        return ["off", "heat"]
    if season is Season.COOL:
        return ["off", "cool"]
    return ["off"]


def season_climate_discovery(app_version: str) -> tuple[str, dict[str, Any]]:
    object_id = "dh_climate_outdoor_season"
    base = f"{BASE_TOPIC}/season"
    payload = {
        "name": "Настройка сезонов",
        "unique_id": object_id,
        "default_entity_id": f"climate.{object_id}",
        "availability_topic": f"{base}/availability",
        "current_temperature_topic": f"{base}/current_temperature",
        "current_humidity_topic": f"{base}/current_humidity",
        "mode_state_topic": f"{base}/hvac_mode",
        "mode_command_topic": f"{base}/set/hvac_mode",
        "temperature_low_state_topic": f"{base}/target_temp_low",
        "temperature_low_command_topic": f"{base}/set/target_temp_low",
        "temperature_high_state_topic": f"{base}/target_temp_high",
        "temperature_high_command_topic": f"{base}/set/target_temp_high",
        "action_topic": f"{base}/hvac_action",
        "json_attributes_topic": f"{base}/attributes",
        "modes": ["heat_cool"],
        "min_temp": -40,
        "max_temp": 50,
        "temp_step": 0.1,
        "retain": False,
        "device": system_device(app_version),
        "origin": _origin(app_version),
    }
    return discovery_topic("climate", object_id), payload


def room_climate_discovery(
    room: RoomConfig,
    *,
    season: Season,
    app_version: str,
) -> tuple[str, dict[str, Any]]:
    object_id = f"dh_climate_{room.room_id}"
    base = f"{BASE_TOPIC}/rooms/{room.room_id}/climate"
    payload = {
        "name": room.name,
        "unique_id": object_id,
        "default_entity_id": f"climate.{object_id}",
        "availability_topic": f"{base}/availability",
        "current_temperature_topic": f"{base}/current_temperature",
        "temperature_state_topic": f"{base}/target_temperature",
        "temperature_command_topic": f"{base}/set/target_temperature",
        "mode_state_topic": f"{base}/hvac_mode",
        "mode_command_topic": f"{base}/set/hvac_mode",
        "action_topic": f"{base}/hvac_action",
        "fan_mode_state_topic": f"{base}/profile",
        "fan_mode_command_topic": f"{base}/set/profile",
        "fan_modes": ["day", "night", "away", "antifreeze"],
        "modes": _allowed_room_modes(season),
        "min_temp": 5,
        "max_temp": 35,
        "temp_step": 0.5,
        "json_attributes_topic": f"{base}/attributes",
        "retain": False,
        "device": room_device(room, app_version),
        "origin": _origin(app_version),
    }
    return discovery_topic("climate", object_id), payload


def room_humidity_discovery(
    room: RoomConfig,
    *,
    app_version: str,
) -> tuple[str, dict[str, Any]] | None:
    if not room.humidity.enabled or room.humidity.controller_type is None:
        return None

    object_id = f"dh_climate_{room.room_id}_humidity"
    base = f"{BASE_TOPIC}/rooms/{room.room_id}/humidity"
    payload: dict[str, Any] = {
        "name": "Humidity",
        "unique_id": object_id,
        "default_entity_id": f"humidifier.{object_id}",
        "availability_topic": f"{base}/availability",
        "state_topic": f"{base}/state",
        "command_topic": f"{base}/set/state",
        "current_humidity_topic": f"{base}/current_humidity",
        "target_humidity_state_topic": f"{base}/target_humidity",
        "target_humidity_command_topic": f"{base}/set/target_humidity",
        "min_humidity": 20,
        "max_humidity": 80,
        "device": room_device(room, app_version),
        "origin": _origin(app_version),
    }
    if room.humidity.controller_type == "dehumidifier":
        payload["device_class"] = "dehumidifier"
    else:
        payload["device_class"] = "humidifier"
    return discovery_topic("humidifier", object_id), payload


def diagnostic_discovery(app_version: str) -> dict[str, tuple[str, dict[str, Any]]]:
    base = f"{BASE_TOPIC}/system"
    common = {
        "availability_topic": f"{base}/availability",
        "device": system_device(app_version),
        "origin": _origin(app_version),
        "entity_category": "diagnostic",
    }
    version_id = "dh_climate_app_version"
    started_id = "dh_climate_app_started_at"
    return {
        "version": (
            discovery_topic("sensor", version_id),
            {
                **common,
                "name": "Version",
                "unique_id": version_id,
                "default_entity_id": f"sensor.{version_id}",
                "state_topic": f"{base}/version",
            },
        ),
        "started_at": (
            discovery_topic("sensor", started_id),
            {
                **common,
                "name": "Started at",
                "unique_id": started_id,
                "default_entity_id": f"sensor.{started_id}",
                "state_topic": f"{base}/started_at",
                "device_class": "timestamp",
            },
        ),
    }
