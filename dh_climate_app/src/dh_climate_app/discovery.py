from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from .config import RoomConfig
from .humidity import HumidityState
from .outdoor import OutdoorState
from .rooms import RoomState


DISCOVERY_PREFIX = "homeassistant"
BASE_TOPIC = "DigitalHouses/Global/dh_climate_app"
SEASON_BASE = f"{BASE_TOPIC}/season"
SEASON_AVAILABILITY_TOPIC = f"{SEASON_BASE}/availability"
ROOMS_BASE = f"{BASE_TOPIC}/rooms"
SYSTEM_STATE_TOPIC = f"{BASE_TOPIC}/state"
SYSTEM_AVAILABILITY_TOPIC = f"{BASE_TOPIC}/availability"
SYSTEM_PROBLEM_TOPIC = f"{BASE_TOPIC}/problem"
SYSTEM_PROBLEM_ATTRIBUTES_TOPIC = f"{BASE_TOPIC}/problem_attributes"

SYSTEM_DEVICE_ID = "dh_climate_app"
SEASON_OBJECT_ID = "dh_climate_app_season"


def _origin(app_version: str) -> dict[str, str]:
    return {
        "name": "DigitalHouses Climate App",
        "sw_version": app_version,
    }


def system_device(app_version: str) -> dict[str, Any]:
    return {
        "identifiers": [SYSTEM_DEVICE_ID],
        "name": "DigitalHouses Climate",
        "manufacturer": "Digital Houses",
        "model": "Climate App",
        "sw_version": app_version,
    }


def room_device(room: RoomConfig, app_version: str) -> dict[str, Any]:
    return {
        "identifiers": [f"dh_climate_app_room_{room.room_id}"],
        "name": room.name,
        "manufacturer": "Digital Houses",
        "model": "Climate Room",
        "sw_version": app_version,
        "via_device": SYSTEM_DEVICE_ID,
    }


def season_discovery_payload(app_version: str) -> dict[str, Any]:
    return {
        "name": "Настройка сезонов",
        "unique_id": SEASON_OBJECT_ID,
        "default_entity_id": f"climate.{SEASON_OBJECT_ID}",
        "availability": [
            {"topic": SYSTEM_AVAILABILITY_TOPIC},
            {"topic": SEASON_AVAILABILITY_TOPIC},
        ],
        "availability_mode": "all",
        "current_temperature_topic": f"{SEASON_BASE}/current_temperature",
        "current_humidity_topic": f"{SEASON_BASE}/current_humidity",
        "mode_state_topic": f"{SEASON_BASE}/hvac_mode",
        "mode_command_topic": f"{SEASON_BASE}/set/hvac_mode",
        "temperature_low_state_topic": f"{SEASON_BASE}/target_temp_low",
        "temperature_low_command_topic": f"{SEASON_BASE}/set/target_temp_low",
        "temperature_high_state_topic": f"{SEASON_BASE}/target_temp_high",
        "temperature_high_command_topic": f"{SEASON_BASE}/set/target_temp_high",
        "action_topic": f"{SEASON_BASE}/hvac_action",
        "json_attributes_topic": f"{SEASON_BASE}/attributes",
        "min_temp": -40.0,
        "max_temp": 50.0,
        "temp_step": 0.1,
        "modes": ["heat_cool"],
        "retain": True,
        "device": system_device(app_version),
        "origin": _origin(app_version),
    }


def diagnostic_discovery_payloads(app_version: str) -> dict[str, tuple[str, dict[str, Any]]]:
    device = system_device(app_version)
    origin = _origin(app_version)
    return {
        "version": (
            f"{DISCOVERY_PREFIX}/sensor/dh_climate_app_version/config",
            {
                "name": "Version",
                "unique_id": "dh_climate_app_version",
                "default_entity_id": "sensor.dh_climate_app_version",
                "state_topic": SYSTEM_STATE_TOPIC,
                "value_template": "{{ value_json.app_version }}",
                "entity_category": "diagnostic",
                "device": device,
                "origin": origin,
            },
        ),
        "started_at": (
            f"{DISCOVERY_PREFIX}/sensor/dh_climate_app_started_at/config",
            {
                "name": "Started at",
                "unique_id": "dh_climate_app_started_at",
                "default_entity_id": "sensor.dh_climate_app_started_at",
                "state_topic": SYSTEM_STATE_TOPIC,
                "value_template": "{{ value_json.started_at }}",
                "device_class": "timestamp",
                "entity_category": "diagnostic",
                "device": device,
                "origin": origin,
            },
        ),
        "problem": (
            f"{DISCOVERY_PREFIX}/binary_sensor/dh_climate_app_problem/config",
            {
                "name": "Problem",
                "unique_id": "dh_climate_app_problem",
                "default_entity_id": "binary_sensor.dh_climate_app_problem",
                "device_class": "problem",
                "state_topic": SYSTEM_PROBLEM_TOPIC,
                "payload_on": "ON",
                "payload_off": "OFF",
                "json_attributes_topic": SYSTEM_PROBLEM_ATTRIBUTES_TOPIC,
                "entity_category": "diagnostic",
                "device": device,
                "origin": origin,
            },
        ),
        "delete_telemetry": (
            f"{DISCOVERY_PREFIX}/button/dh_climate_app_delete_telemetry/config",
            {
                "name": "Delete telemetry data",
                "unique_id": "dh_climate_app_delete_telemetry",
                "default_entity_id": "button.dh_climate_app_delete_telemetry",
                "command_topic": f"{BASE_TOPIC}/system/set/delete_telemetry",
                "payload_press": "DELETE",
                "entity_category": "config",
                "icon": "mdi:delete-outline",
                "availability_topic": SYSTEM_AVAILABILITY_TOPIC,
                "device": device,
                "origin": origin,
            },
        ),
    }


def season_discovery_topic() -> str:
    return f"{DISCOVERY_PREFIX}/climate/{SEASON_OBJECT_ID}/config"


def room_base(room_id: str) -> str:
    return f"{ROOMS_BASE}/{room_id}"


def room_climate_discovery_topic(room_id: str) -> str:
    object_id = f"dh_climate_app_{room_id}"
    return f"{DISCOVERY_PREFIX}/climate/{object_id}/config"


def room_profile_discovery_topic(room_id: str) -> str:
    object_id = f"dh_climate_app_{room_id}_profile"
    return f"{DISCOVERY_PREFIX}/select/{object_id}/config"


def room_humidity_discovery_topic(room_id: str) -> str:
    object_id = f"dh_climate_app_{room_id}_humidity"
    return f"{DISCOVERY_PREFIX}/humidifier/{object_id}/config"


def room_climate_discovery_payload(
    room: RoomConfig,
    state: RoomState,
    app_version: str,
) -> dict[str, Any]:
    base = room_base(room.room_id)
    if state.season.value == "heat":
        modes = ["off", "heat"]
    elif state.season.value == "cool":
        modes = ["off", "cool"]
    else:
        modes = ["off"]

    return {
        "name": "Thermostat",
        "unique_id": f"dh_climate_app_{room.room_id}",
        "default_entity_id": f"climate.dh_climate_app_{room.room_id}",
        "availability": [
            {"topic": SYSTEM_AVAILABILITY_TOPIC},
            {"topic": f"{base}/climate/availability"},
        ],
        "availability_mode": "all",
        "current_temperature_topic": f"{base}/climate/current_temperature",
        "current_humidity_topic": f"{base}/climate/current_humidity",
        "temperature_state_topic": f"{base}/climate/target_temperature",
        "temperature_command_topic": f"{base}/climate/set/target_temperature",
        "mode_state_topic": f"{base}/climate/hvac_mode",
        "mode_command_topic": f"{base}/climate/set/hvac_mode",
        "action_topic": f"{base}/climate/hvac_action",
        "json_attributes_topic": f"{base}/climate/attributes",
        "modes": modes,
        "min_temp": 5.0,
        "max_temp": 35.0,
        "temp_step": 0.5,
        "retain": True,
        "device": room_device(room, app_version),
        "origin": _origin(app_version),
    }


def room_profile_discovery_payload(
    room: RoomConfig,
    app_version: str,
) -> dict[str, Any]:
    base = room_base(room.room_id)
    return {
        "name": "Profile",
        "unique_id": f"dh_climate_app_{room.room_id}_profile",
        "default_entity_id": f"select.dh_climate_app_{room.room_id}_profile",
        "state_topic": f"{base}/climate/profile",
        "command_topic": f"{base}/climate/set/profile",
        "options": ["day", "night", "away"],
        "availability": [
            {"topic": SYSTEM_AVAILABILITY_TOPIC},
            {"topic": f"{base}/climate/availability"},
        ],
        "availability_mode": "all",
        "retain": True,
        "device": room_device(room, app_version),
        "origin": _origin(app_version),
    }


def room_humidity_discovery_payload(
    room: RoomConfig,
    app_version: str,
) -> dict[str, Any]:
    if not room.humidity.enabled or room.humidity.controller_type is None:
        raise ValueError(f"humidity control is not configured for {room.room_id}")
    base = room_base(room.room_id)
    return {
        "name": "Humidity",
        "unique_id": f"dh_climate_app_{room.room_id}_humidity",
        "default_entity_id": f"humidifier.dh_climate_app_{room.room_id}",
        "device_class": room.humidity.controller_type,
        "availability": [
            {"topic": SYSTEM_AVAILABILITY_TOPIC},
            {"topic": f"{base}/humidity/availability"},
        ],
        "availability_mode": "all",
        "state_topic": f"{base}/humidity/state",
        "command_topic": f"{base}/humidity/set/state",
        "payload_on": "ON",
        "payload_off": "OFF",
        "action_topic": f"{base}/humidity/action",
        "current_humidity_topic": f"{base}/humidity/current",
        "target_humidity_state_topic": f"{base}/humidity/target",
        "target_humidity_command_topic": f"{base}/humidity/set/target",
        "min_humidity": 0,
        "max_humidity": 100,
        "retain": True,
        "device": room_device(room, app_version),
        "origin": _origin(app_version),
    }


def _number(value: float | None, precision: int = 1) -> str:
    # MQTT climate/humidifier numeric state uses None to clear stale values.
    if value is None:
        return "None"
    return f"{value:.{precision}f}"


def season_state_topics(state: OutdoorState) -> dict[str, str]:
    action = {
        "heat": "heating",
        "cool": "cooling",
        "off": "idle",
    }[state.season.value]
    attrs = {
        "season": state.season.value,
        "current_temperature": state.current_temperature,
        "avg_24h_temperature": state.avg_24h_temperature,
        "temperature_source": state.temperature_source,
        "current_humidity": state.current_humidity,
        "avg_24h_humidity": state.avg_24h_humidity,
        "humidity_source": state.humidity_source,
        "hysteresis": state.hysteresis,
        "heat_threshold": state.heat_threshold,
        "cool_threshold": state.cool_threshold,
        "observed_at": state.observed_at.isoformat(),
    }
    return {
        f"{SEASON_BASE}/current_temperature": _number(state.avg_24h_temperature),
        f"{SEASON_BASE}/current_humidity": _number(state.avg_24h_humidity),
        f"{SEASON_BASE}/hvac_mode": "heat_cool",
        f"{SEASON_BASE}/hvac_action": action,
        f"{SEASON_BASE}/target_temp_low": _number(state.heat_threshold),
        f"{SEASON_BASE}/target_temp_high": _number(state.cool_threshold),
        f"{SEASON_BASE}/attributes": json.dumps(
            attrs,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def room_climate_state_topics(
    state: RoomState,
    *,
    published_profile: str,
    published_target: float | None,
) -> dict[str, str]:
    base = room_base(state.room_id)
    attrs = {
        "season": state.season.value,
        "effective_profile": state.effective_profile.value,
        "published_profile": published_profile,
        "climate_control_enabled": state.climate_control_enabled,
        "control_action": state.control_action.value,
        "window_state": state.window_state,
    }
    return {
        f"{base}/climate/availability": "online" if state.available else "offline",
        f"{base}/climate/current_temperature": _number(state.current_temperature),
        f"{base}/climate/current_humidity": _number(state.current_humidity),
        f"{base}/climate/target_temperature": _number(published_target),
        f"{base}/climate/hvac_mode": state.hvac_mode,
        f"{base}/climate/hvac_action": state.hvac_action.value,
        f"{base}/climate/profile": published_profile,
        f"{base}/climate/attributes": json.dumps(
            attrs,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def room_humidity_state_topics(state: HumidityState) -> dict[str, str]:
    base = room_base(state.room_id)
    return {
        f"{base}/humidity/availability": "online" if state.available else "offline",
        f"{base}/humidity/state": "ON" if state.control_enabled else "OFF",
        f"{base}/humidity/action": state.action,
        f"{base}/humidity/current": _number(state.current_humidity),
        f"{base}/humidity/target": _number(state.target_humidity),
    }


def system_state_payload(*, app_version: str, started_at: datetime) -> str:
    return json.dumps(
        {
            "app_version": app_version,
            "started_at": started_at.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def problem_state_payload(problems: tuple[object, ...]) -> tuple[str, str]:
    payloads = []
    for problem in problems:
        if hasattr(problem, "payload"):
            payloads.append(problem.payload())
        elif isinstance(problem, dict):
            payloads.append(problem)
        else:
            payloads.append({"code": str(problem)})
    state = "ON" if payloads else "OFF"
    attrs = json.dumps(
        {
            "count": len(payloads),
            "problems": payloads,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return state, attrs
