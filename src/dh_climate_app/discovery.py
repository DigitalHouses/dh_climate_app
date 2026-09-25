from __future__ import annotations

from datetime import datetime
from typing import Any

from .outdoor import OutdoorState


DISCOVERY_PREFIX = "homeassistant"
BASE_TOPIC = "DigitalHouses/Global/dh_climate_app"
SEASON_BASE = f"{BASE_TOPIC}/season"
SYSTEM_STATE_TOPIC = f"{BASE_TOPIC}/state"
SYSTEM_AVAILABILITY_TOPIC = f"{BASE_TOPIC}/availability"

SYSTEM_DEVICE_ID = "dh_climate_app"
SEASON_OBJECT_ID = "dh_climate_app_season"


def system_device(app_version: str) -> dict[str, Any]:
    return {
        "identifiers": [SYSTEM_DEVICE_ID],
        "name": "DigitalHouses Climate",
        "manufacturer": "Digital Houses",
        "model": "Climate App",
        "sw_version": app_version,
    }


def season_discovery_payload(app_version: str) -> dict[str, Any]:
    return {
        "name": "Настройка сезонов",
        "unique_id": SEASON_OBJECT_ID,
        "default_entity_id": f"climate.{SEASON_OBJECT_ID}",
        "availability_topic": SYSTEM_AVAILABILITY_TOPIC,
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
        "origin": {
            "name": "DigitalHouses Climate App",
            "sw_version": app_version,
        },
    }


def diagnostic_discovery_payloads(app_version: str) -> dict[str, tuple[str, dict[str, Any]]]:
    device = system_device(app_version)
    origin = {"name": "DigitalHouses Climate App", "sw_version": app_version}
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
    }


def season_discovery_topic() -> str:
    return f"{DISCOVERY_PREFIX}/climate/{SEASON_OBJECT_ID}/config"


def season_state_topics(state: OutdoorState) -> dict[str, str]:
    def number(value: float | None) -> str:
        return "unknown" if value is None else f"{value:.1f}"

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

    import json

    return {
        f"{SEASON_BASE}/current_temperature": number(state.avg_24h_temperature),
        f"{SEASON_BASE}/current_humidity": number(state.avg_24h_humidity),
        f"{SEASON_BASE}/hvac_mode": "heat_cool",
        f"{SEASON_BASE}/hvac_action": action,
        f"{SEASON_BASE}/target_temp_low": number(state.heat_threshold),
        f"{SEASON_BASE}/target_temp_high": number(state.cool_threshold),
        f"{SEASON_BASE}/attributes": json.dumps(
            attrs,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


def system_state_payload(*, app_version: str, started_at: datetime) -> str:
    import json

    return json.dumps(
        {
            "app_version": app_version,
            "started_at": started_at.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
