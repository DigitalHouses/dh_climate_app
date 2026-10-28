"""Read-only Home Assistant System Tree projection; no actuator commands."""
from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Mapping


def _part(text: str, entity: str | None = None) -> dict[str, str]:
    value = {"text": text}
    if entity:
        value["entity_id"] = entity
    return value


def _node(*parts: dict[str, str], children: list[dict] | None = None) -> dict:
    return {"parts": list(parts), "children": children if children is not None else []}


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


def _measurement(value: object, unit: str) -> str | None:
    number = _number(value)
    return f"{number:.1f}{unit}" if number is not None else None


def _snapshot_state(snapshot: Mapping[str, Any], entity_id: str) -> Any | None:
    state = snapshot.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", "none", ""):
        return None
    return state


def _source_parts(entity: str, snapshot: Mapping[str, Any], weather: Any | None) -> list[dict[str, str]]:
    parts = [_part(entity, entity)]
    state = _snapshot_state(snapshot, entity)
    if state is None:
        parts.append(_part(" · UNKNOWN"))
        return parts
    attrs = state.attributes
    is_weather = entity.startswith("weather.")
    if is_weather:
        temp = _measurement(attrs.get("temperature"), "°C")
        hum = _measurement(attrs.get("humidity"), "%")
        if temp is not None:
            parts.append(_part(f" · 🌡️ {temp}", entity))
        if hum is not None:
            parts.append(_part(f" · 💧 {hum}", entity))
    if weather is not None and weather.source_entity == entity:
        mm = _measurement(weather.precipitation_mm, " mm")
        if mm is not None:
            parts.append(_part(f" · 🌧️ {mm}", entity))
    return parts


def _source_chain(
    ids: tuple[str, ...], snapshot: Mapping[str, Any], weather: Any | None,
    *, kind: str,
) -> list[dict]:
    chain: dict | None = None
    for entity in reversed(ids):
        parts = _source_parts(entity, snapshot, weather)
        state = _snapshot_state(snapshot, entity)
        if state is not None and not entity.startswith("weather."):
            val = _measurement(state.state, "°C" if kind in ("temperature", "both") else "%")
            if val is not None:
                icon = " · 🌡️ " if kind in ("temperature", "both") else " · 💧 "
                parts.append(_part(icon + val, entity))
        chain = _node(*parts, children=[chain] if chain is not None else [])
    return [chain] if chain is not None else []


def _source_nodes(config: Any, snapshot: Mapping[str, Any], weather: Any | None) -> list[dict]:
    temperature_sources = config.outdoor.temperature_sources
    humidity_sources = config.outdoor.humidity_sources
    if temperature_sources == humidity_sources:
        return [_node(_part("🔗 SOURCES"), children=_source_chain(temperature_sources, snapshot, weather, kind="both"))] if temperature_sources else []
    children = []
    if temperature_sources:
        children.append(_node(_part("🌡️ TEMPERATURE SOURCES"), children=_source_chain(temperature_sources, snapshot, weather, kind="temperature")))
    if humidity_sources:
        children.append(_node(_part("💧 HUMIDITY SOURCES"), children=_source_chain(humidity_sources, snapshot, weather, kind="humidity")))
    return children


def _health_text(status: str) -> str:
    return {
        "healthy": "🟢 HEALTHY", "degraded": "🟠 DEGRADED",
        "critical": "🔴 CRITICAL", "unknown": "⚪ UNKNOWN",
    }.get(status, "⚪ UNKNOWN")


def _room_targets(room_id: str, values: Mapping[str, float | None], season: str) -> dict | None:
    if season not in ("heat", "cool"):
        return None
    spec = (
        (("heat_day", "☀️"), ("heat_night", "🌙"), ("heat_away", "🧳"), ("heat_antifreeze", "🛡️"))
        if season == "heat" else
        (("cool_day", "☀️"), ("cool_night", "🌙"), ("cool_away", "🧳"))
    )
    parts = [_part("🎯 " + season.upper() + ": ")]
    for key, icon in spec:
        val = _measurement(values.get(key), "")
        if val is not None:
            if len(parts) > 1:
                parts.append(_part(" · "))
            parts.append(_part(f"{icon}{val}", f"number.dh_climate_app_{room_id}_{key}"))
    if len(parts) == 1:
        return None
    parts.append(_part("°C"))
    return _node(*parts)


def _device_node(device: Any, snapshot: Mapping[str, Any]) -> dict:
    entity = device.entity_id
    state = _snapshot_state(snapshot, entity)
    domain = entity.split(".", 1)[0]
    friendly = state.attributes.get("friendly_name") if state is not None else None
    name = str(friendly).strip() if isinstance(friendly, str) and friendly.strip() else entity
    online = "🟢 AVAILABLE" if state is not None else "⚪ UNKNOWN"
    children = []
    control = "HARDWARE" if device.control == "device" else "VIRTUAL"
    kind = ("SLOW HEAT" if device.device_class.value == "slow" else
            "FAST HEAT/COOL" if device.function == "heat_cool" else
            "FAST COOL" if device.function == "cool" else "FAST HEAT")
    children.append(_node(_part(f"{kind} · {control}")))
    if state is not None:
        if domain == "climate":
            current = _measurement(state.attributes.get("current_temperature"), "°C")
            target = _measurement(state.attributes.get("temperature"), "°C")
            if current is not None or target is not None:
                children.append(_node(_part("🌡️ " + (current or "?") + " / " + (target or "?"), entity)))
            action = state.attributes.get("hvac_action")
            action_text = f" · {str(action).upper()}" if action in ("heating", "cooling", "idle", "off") else ""
            children.append(_node(_part("🔥 " + state.state.upper() + action_text, entity)))
        elif domain == "switch":
            children.append(_node(_part("🔌 " + state.state.upper(), entity)))
    return _node(_part(f"🔥 {name} · {online}", entity), children=[_node(_part(entity, entity), children=children)])


def _humidity_node(room: Any, state: Any | None, snapshot: Mapping[str, Any]) -> dict | None:
    if not room.humidity.enabled or room.humidity.actuator is None:
        return None
    entity = room.humidity.actuator.entity_id
    actual = _snapshot_state(snapshot, entity)
    subtype = room.humidity.controller_type or "humidity"
    status = "🟢 AVAILABLE" if actual is not None else "⚪ UNKNOWN"
    children = []
    if state is not None:
        val = _measurement(state.current_humidity, "%")
        target = _measurement(state.target_humidity, "%")
        if val is not None and target is not None:
            children.append(_node(_part(f"💧 {val} / {target}", f"humidifier.dh_climate_app_{room.room_id}_humidity")))
    if actual is not None:
        children.append(_node(_part(f"{subtype.upper()} · VIRTUAL · {actual.state.upper()}", entity)))
    return _node(_part(f"💧 {subtype.title()} · {status}", entity), children=[_node(_part(entity, entity), children=children)])


def _flatten(root: dict) -> list[dict]:
    lines: list[dict] = []
    def walk(node: dict, prefix: str, branch: str) -> None:
        lines.append({"prefix": prefix + branch, "parts": node["parts"]})
        children = node["children"]
        child_prefix = prefix + ("│  " if branch == "├─ " else "   " if branch else "")
        for i, child in enumerate(children):
            walk(child, child_prefix, "└─ " if i == len(children) - 1 else "├─ ")
    walk(root, "", "")
    return lines


def build_topology(
    *, config: Any, outdoor: Any, weather: Any | None,
    room_states: Mapping[str, Any], humidity_states: Mapping[str, Any],
    health: Any, snapshot: Mapping[str, Any], app_version: str,
    started_at: datetime, observed_at: datetime, ha_connected: bool,
    room_targets: Mapping[str, Mapping[str, float | None]],
) -> dict[str, Any]:
    """Stable click-addressable lines built from authoritative runtime inputs."""
    uptime_seconds = max(0, int((observed_at - started_at).total_seconds()))
    uptime_minutes = (uptime_seconds // 600) * 10
    root = _node(_part("🏠 dh_climate_app · " + _health_text(health.climate_state), "sensor.dh_climate_app_climate_health"))
    root["children"].append(_node(_part(("🟢 ONLINE" if ha_connected else "⚪ OFFLINE") + f" · v{app_version} · Uptime: ~{uptime_minutes // 60}h {uptime_minutes % 60}m", "sensor.dh_climate_app_version")))
    outdoor_children = [_node(_part("📅 SEASON: " + outdoor.season.value.upper(), "climate.dh_climate_app_season"))]
    avg = _measurement(outdoor.avg_24h_temperature, "°C")
    if avg is not None:
        outdoor_children.append(_node(_part("🌡️ AVG24: " + avg, "sensor.dh_climate_app_outdoor_temperature_avg24")))
    outdoor_children.extend(_source_nodes(config, snapshot, weather))
    out_health = "unknown" if outdoor.current_temperature is None and outdoor.last_valid_at is None else "degraded" if outdoor.stale else "healthy"
    root["children"].append(_node(_part("🌤️ OUTDOOR · " + _health_text(out_health)), children=outdoor_children))

    home = []
    for entity, title in ((config.global_config.night_mode, "🌙 NIGHT MODE"), (config.global_config.we_at_home, "🏡 PRESENCE")):
        if entity:
            state = _snapshot_state(snapshot, entity)
            home.append(_node(_part(f"{title}: " + (state.state.upper() if state is not None else "UNKNOWN"), entity)))
    root["children"].append(_node(_part("🏡 HOME · " + _health_text(health.global_state)), children=home))

    room_nodes = []
    for room in config.rooms:
        state = room_states.get(room.room_id)
        status = health.rooms.get(room.room_id, "unknown")
        climate = f"climate.dh_climate_app_{room.room_id}"
        children = []
        if state is not None:
            target_node = _room_targets(room.room_id, room_targets.get(room.room_id, {}), state.season.value)
            if target_node is not None:
                children.append(target_node)
            current = _measurement(state.current_temperature, "°C")
            target = _measurement(state.target_temperature, "°C")
            thermostat_children = []
            if current is not None or target is not None:
                thermostat_children.append(_node(_part("🌡️ " + (current or "?") + " / " + (target or "?"), climate)))
            thermostat_children.append(_node(_part("🔥 " + state.hvac_mode.upper() + " · " + state.hvac_action.value.upper() + " · " + state.effective_profile.value.upper(), climate)))
        else:
            thermostat_children = [_node(_part("⚪ UNKNOWN", climate))]
        thermostat_children.extend(_device_node(device, snapshot) for device in room.devices)
        humidity = _humidity_node(room, humidity_states.get(room.room_id), snapshot)
        if humidity is not None:
            thermostat_children.append(humidity)
        children.append(_node(_part("🎛️ " + climate, climate), children=thermostat_children))
        room_nodes.append(_node(_part("🏠 " + room.name + " · " + _health_text(status), f"sensor.dh_climate_app_{room.room_id}_health"), children=children))
    root["children"].append(_node(_part(f"🏘️ ROOMS · {len(config.rooms)}"), children=room_nodes))
    return {"schema_version": 1, "lines": _flatten(root)}
