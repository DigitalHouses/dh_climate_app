"""Read-only Operations projection from authoritative Climate Runtime state.

No Home Assistant entity, control algorithm or physical asset is invented here.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from .hydraulics import HydraulicsConfig, hydraulic_snapshot


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return round(number, 2) if math.isfinite(number) else None


def _friendly_name(entity_id: str | None, states: Mapping[str, Any]) -> str | None:
    """Only the HA friendly_name; never extrapolate it from room or entity IDs."""
    if not entity_id:
        return None
    observed = states.get(entity_id)
    if observed is None:
        return None
    attributes = observed.attributes
    raw = attributes.get("friendly_name") if isinstance(attributes, Mapping) else None
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    return name[:160] if name and name != entity_id else None


def _entity(entity_id: str | None, states: Mapping[str, Any]) -> dict[str, Any] | None:
    if not entity_id:
        return None
    observed = states.get(entity_id)
    return {
        "entity_id": entity_id,
        "friendly_name": _friendly_name(entity_id, states),
        "state": observed.state if observed is not None else None,
        # Strictly whitelist the native HA unit (do not guess Celsius for
        # every sensor; RPM, pressure, percent, and device states differ).
        "unit": (
            observed.attributes.get("unit_of_measurement")[:24]
            if observed is not None
            and isinstance(observed.attributes, Mapping)
            and isinstance(observed.attributes.get("unit_of_measurement"), str)
            else None
        ),
        "available": observed is not None and observed.state not in ("unknown", "unavailable", ""),
        "last_updated": (
            observed.last_updated.isoformat() if observed is not None else None
        ),
        "attributes": (
            {
                "temperature": _number(observed.attributes.get("temperature")),
                "humidity": _number(observed.attributes.get("humidity")),
            }
            if observed is not None and entity_id.startswith("weather.")
            else {}
        ),
    }


def _signals(signals: Mapping[str, str], states: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {"role": role, **_entity(entity_id, states)}
        for role, entity_id in signals.items()
        if entity_id
    ]


def build_operations_snapshot(
    *, config: Any, outdoor: Any | None, weather: Any | None,
    room_states: Mapping[str, Any], health: Any | None,
    problems: tuple[Any, ...], demands: Mapping[tuple[str, str], Any],
    states: Mapping[str, Any], version: str, ha_connected: bool,
    source_readings: Mapping[str, float | None] | None = None,
) -> dict[str, Any]:
    """Assemble a small, transport-safe view; no state estimation or commands."""
    online = bool(ha_connected)
    source_readings = source_readings or {}
    registry = config.outdoor
    providers_raw = getattr(registry, "providers", ())
    physical_raw = getattr(registry, "physical_sensors", ())
    source_model = getattr(registry, "source_model", "legacy")
    provider_index = {p.provider_id: p for p in providers_raw}
    physical_index = {p.sensor_id: p for p in physical_raw}

    def source_entry(source_id: str) -> dict[str, Any]:
        if source_model != "sensors":
            return _entity(source_id, states) or {}
        if source_id in physical_index:
            original = physical_index[source_id].entity_id
            quantity = physical_index[source_id].quantity
        else:
            source_provider, _, quantity = source_id.rpartition(".")
            provider = provider_index.get(source_provider)
            original = provider.entity_id if provider is not None else ""
        value = source_readings.get(source_id) if online else None
        return {
            "entity_id": source_id, "original_entity_id": original,
            "quantity": quantity,
            "friendly_name": _friendly_name(original, states),
            "state": value,
            "available": value is not None,
            "last_updated": (
                states[original].last_updated.isoformat() if original in states else None
            ),
            "attributes": {},
        }

    providers = [
        {
            "id": p.provider_id,
            "entity_id": p.entity_id,
            "friendly_name": _friendly_name(p.entity_id, states),
            "temperature": (
                _number(source_readings.get(p.provider_id + ".temperature"))
                if online else None
            ),
            "humidity": (
                _number(source_readings.get(p.provider_id + ".humidity"))
                if online else None
            ),
        } for p in providers_raw
    ] if source_model == "sensors" else []
    physical_sensors = [
        {
            "id": p.sensor_id,
            "entity_id": p.entity_id,
            "quantity": p.quantity,
            "friendly_name": _friendly_name(p.entity_id, states),
            # The engine-normalized reading is retained for °C/% presentation.
            # The raw HA entity is included solely for showing its actual
            # value and native unit even if the engine cannot accept it.
            "value": _number(source_readings.get(p.sensor_id)) if online else None,
            "observed": _entity(p.entity_id, states if online else {}),
        } for p in physical_raw
    ] if source_model == "sensors" else []
    rooms: list[dict[str, Any]] = []
    for room in config.rooms:
        state = room_states.get(room.room_id) if online else None
        rooms.append({
            "id": room.room_id,
            "name": room.name,
            "friendly_name": _friendly_name(
                f"climate.dh_climate_app_{room.room_id}", states
            ),
            "climate_entity": f"climate.dh_climate_app_{room.room_id}",
            "health": (
                health.rooms.get(room.room_id, "unknown")
                if health is not None and online else "unknown"
            ),
            "temperature": _number(state.current_temperature) if state is not None else None,
            "humidity": _number(state.current_humidity) if state is not None else None,
            "target": _number(state.target_temperature) if state is not None else None,
            "profile": state.effective_profile.value if state is not None else None,
            "hvac_mode": state.hvac_mode if state is not None else None,
            "hvac_action": state.hvac_action.value if state is not None else None,
            "window_state": state.window_state if state is not None else None,
            "window_cooling_blocked": (
                state.window_cooling_blocked if state is not None else None
            ),
            "sensors": {
                "temperature": [_entity(e, states) for e in room.temperature_sensors],
                "humidity": [_entity(e, states) for e in room.humidity_sensors],
                "window": [_entity(e, states) for e in room.window_sensors],
            },
            "devices": [
                {
                    "entity_id": device.entity_id,
                    "device_type": device.device_type,
                    "role": (
                        "slow_heat" if device.device_class.value == "slow"
                        else "fast_heat_cool" if device.function == "heat_cool"
                        else "fast_cool" if device.function == "cool"
                        else "fast_heat"
                    ),
                    "resource": device.resource,
                    "observed": _entity(device.entity_id, states),
                    "hvac_action": (
                        states[device.entity_id].attributes.get("hvac_action")
                        if device.entity_id in states else None
                    ),
                } for device in room.devices
            ],
        })

    resources = []
    for resource_id, resource in config.resources.items():
        resources.append({
            "id": resource_id,
            "signals": _signals(resource.signals, states),
            "pumps": [
                {"id": p.part_id, "name": p.name, "signals": _signals(p.signals, states)}
                for p in resource.pumps
            ],
            "circuits": [
                {"id": p.part_id, "name": p.name, "signals": _signals(p.signals, states)}
                for p in resource.circuits
            ],
        })

    return {
        "schema_version": 1,
        "app": {
            "version": version,
            "ha_connected": online,
            "health": (
                health.climate_state if online and health is not None else "unknown"
            ),
            "problems": [p.payload() for p in problems] if online else [],
        },
        "weather": {
            "season": outdoor.season.value if online and outdoor is not None else None,
            "raw_temperature": _number(outdoor.raw_temperature) if online and outdoor is not None else None,
            "temperature": _number(outdoor.current_temperature) if online and outdoor is not None else None,
            "avg24": _number(outdoor.avg_24h_temperature) if online and outdoor is not None else None,
            "avg24_input_sources": (
                list(getattr(outdoor, "temperature_history_sources", ()))
                if online and outdoor is not None else []
            ),
            "heat_threshold": (
                _number(getattr(outdoor, "heat_threshold", None))
                if online and outdoor is not None else None
            ),
            "cool_threshold": (
                _number(getattr(outdoor, "cool_threshold", None))
                if online and outdoor is not None else None
            ),
            "season_hysteresis": (
                _number(getattr(outdoor, "hysteresis", None))
                if online and outdoor is not None else None
            ),
            "humidity": _number(outdoor.current_humidity) if online and outdoor is not None else None,
            "source": outdoor.temperature_source if online and outdoor is not None else None,
            "humidity_source": getattr(outdoor, "humidity_source", None) if online and outdoor is not None else None,
            "condition_source": weather.source_entity if online and weather is not None else None,
            "stale": outdoor.stale if online and outdoor is not None else None,
            "condition": weather.condition if online and weather is not None else None,
            "precipitation_mm": _number(weather.precipitation_mm) if online and weather is not None else None,
            "source_model": source_model,
            "providers": providers,
            "physical_sensors": physical_sensors,
            "temperature_sources": [
                source_entry(e) for e in config.outdoor.temperature_sources
            ],
            "humidity_sources": [
                source_entry(e) for e in config.outdoor.humidity_sources
            ],
        },
        "home": {
            "heating_source": config.heating_source,
            "vrf_enabled": config.vrf_enabled,
            "presence": _entity(config.global_config.we_at_home, states),
            "night": _entity(config.global_config.night_mode, states),
            "resources": resources,
            "hydraulics": hydraulic_snapshot(
                getattr(config, "hydraulics", HydraulicsConfig()),
                states if online else {}, _signals, _entity,
            ),
        },
        "demands": [
            {"layer": layer, "direction": direction,
             "active": demand.active, "count": demand.count,
             "members": list(demand.members)}
            for (layer, direction), demand in sorted(demands.items())
        ] if online else [],
        "rooms": rooms,
    }
