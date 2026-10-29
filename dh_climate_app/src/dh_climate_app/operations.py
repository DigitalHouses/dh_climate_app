"""Read-only Operations projection from authoritative Climate Runtime state.

No Home Assistant entity, control algorithm or physical asset is invented here.
"""
from __future__ import annotations

import math
from typing import Any, Mapping


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return round(number, 2) if math.isfinite(number) else None


def _entity(entity_id: str | None, states: Mapping[str, Any]) -> dict[str, Any] | None:
    if not entity_id:
        return None
    observed = states.get(entity_id)
    return {
        "entity_id": entity_id,
        "state": observed.state if observed is not None else None,
        "available": observed is not None and observed.state not in ("unknown", "unavailable", ""),
        "last_updated": (
            observed.last_updated.isoformat() if observed is not None else None
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
) -> dict[str, Any]:
    """Assemble a small, transport-safe view; no state estimation or commands."""
    online = bool(ha_connected)
    rooms: list[dict[str, Any]] = []
    for room in config.rooms:
        state = room_states.get(room.room_id) if online else None
        rooms.append({
            "id": room.room_id,
            "name": room.name,
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
            "humidity": _number(outdoor.current_humidity) if online and outdoor is not None else None,
            "source": outdoor.temperature_source if online and outdoor is not None else None,
            "stale": outdoor.stale if online and outdoor is not None else None,
            "condition": weather.condition if online and weather is not None else None,
            "precipitation_mm": _number(weather.precipitation_mm) if online and weather is not None else None,
            "temperature_sources": [
                _entity(e, states) for e in config.outdoor.temperature_sources
            ],
            "humidity_sources": [
                _entity(e, states) for e in config.outdoor.humidity_sources
            ],
        },
        "home": {
            "heating_source": config.heating_source,
            "vrf_enabled": config.vrf_enabled,
            "presence": _entity(config.global_config.we_at_home, states),
            "night": _entity(config.global_config.night_mode, states),
            "resources": resources,
        },
        "demands": [
            {"layer": layer, "direction": direction,
             "active": demand.active, "count": demand.count,
             "members": list(demand.members)}
            for (layer, direction), demand in sorted(demands.items())
        ] if online else [],
        "rooms": rooms,
    }
