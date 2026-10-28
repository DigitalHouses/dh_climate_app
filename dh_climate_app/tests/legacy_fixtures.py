"""Historical regression fixture transformer (tests only).

The production parser deliberately accepts ONLY the new nested Supervisor YAML.
Regression tests written for pre-target snapshots use this adapter so they
continue checking execution/recorder/temperature logic without introducing
legacy configuration support into the App.
"""
from __future__ import annotations

from dataclasses import replace

from dh_climate_app.config import _room_targets, parse_options


def _entities(value):
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [v.strip() for v in str(value).replace("\n", ",").split(",") if v.strip()]


def parse_legacy_fixture(raw):
    outdoor = {
        "temperature_sources": _entities(raw.get("outdoor_temperature_sources")),
        "humidity_sources": _entities(raw.get("outdoor_humidity_sources")),
    }
    new_rooms = []
    source_rooms = raw.get("rooms", [])
    for room in source_rooms:
        fast_heat = _entities(room.get("fast_heat"))
        fast_cool = _entities(room.get("fast_cool"))
        slow_heat = _entities(room.get("slow_heat"))
        devices = []
        for entity in fast_heat + [e for e in fast_cool if e not in fast_heat]:
            heat = entity in fast_heat
            cool = entity in fast_cool
            devices.append({
                "entity": entity,
                "role": "fast_heat" if heat else "fast_cool",
                "device_type": "virtual",
                "reversible": heat and cool,
            })
        for entity in slow_heat:
            devices.append({
                "entity": entity, "role": "slow_heat",
                "device_type": "hardware" if entity.startswith("climate.") else "virtual",
                **({"screed_sensor_unavailable": "open"} if entity.startswith("switch.") else {}),
                **({"actuator": "normal_closed"} if entity.startswith("switch.") else {}),
            })
        new_rooms.append({
            "id": room["id"],
            "name": room["name"],
            "temperature_sensors": _entities(room.get("temperature_sensors")),
            "humidity_sensors": _entities(room.get("humidity_sensors")),
            "window_sensors": _entities(room.get("window_sensors")),
            "humidity_mode": room.get("humidity_mode", "off"),
            "humidity_actuator": room.get("humidity_actuator", ""),
            "devices": devices,
        })
    modern = {
        "night_mode": raw.get("night_mode", ""),
        "we_at_home": raw.get("we_at_home", ""),
        "outdoor": outdoor,
        "rooms": new_rooms,
        "log_level": raw.get("log_level", "info"),
        "telemetry_enabled": bool(raw.get("telemetry_enabled", False)),
    }
    config = parse_options(modern)
    hyst = raw.get("hysteresis", raw.get("temperature_hysteresis", 0.5))
    globals_ = replace(
        config.global_config,
        hysteresis=float(hyst),
        humidity_hysteresis=float(raw.get("humidity_hysteresis", 3)),
    )
    outdoor_ = replace(
        config.outdoor,
        heat_threshold_default=float(raw.get("heat_threshold_default", 10)),
        cool_threshold_default=float(raw.get("cool_threshold_default", 25)),
        temperature_ema_minutes=float(raw.get("outdoor_temperature_ema_minutes", 20)),
    )
    room_configs = []
    for index, (config_room, source_room) in enumerate(zip(config.rooms, source_rooms)):
        slow_target = source_room.get("slow_target")
        devices = tuple(
            replace(
                device,
                target_temperature=(
                    float(slow_target) if slow_target is not None
                    and device.device_class.value == "slow" else None
                ),
                min_heating_outdoor_temperature=(
                    float(raw.get("ac_min_outdoor_temperature", -10))
                    if device.function == "heat_cool" else None
                ),
            )
            for device in config_room.devices
        )
        humidity = config_room.humidity
        if humidity.enabled and "humidity_target" in source_room:
            humidity = replace(
                humidity, target_default=float(source_room["humidity_target"])
            )
        room_configs.append(replace(
            config_room,
            targets=_room_targets(source_room, f"rooms[{index}]"),
            devices=devices, humidity=humidity,
        ))
    return replace(
        config,
        global_config=globals_, outdoor=outdoor_,
        rooms=tuple(room_configs),
    )
