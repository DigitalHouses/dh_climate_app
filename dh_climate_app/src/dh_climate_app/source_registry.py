"""One normalized weather-source layer for both control and HA diagnostics.

Never read back the MQTT discovery entities published by this app.
The source of truth is the live HA weather/sensor state cache.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from .config import OutdoorConfig
from .core import _numeric_state


def _finite(raw: object) -> float | None:
    value = _numeric_state(raw)
    if value is None or not math.isfinite(value):
        return None
    return value


def _temperature(raw: object, unit: object) -> float | None:
    value = _finite(raw)
    if value is None:
        return None
    if unit in ("°C", "C"):
        return value
    if unit in ("°F", "F"):
        return (value - 32.0) * 5.0 / 9.0
    if unit in ("K",):
        return value - 273.15
    # Never infer local HA units when none were supplied.
    return None


def _humidity(raw: object) -> float | None:
    value = _finite(raw)
    return value if value is not None and 0 <= value <= 100 else None


def project_sensors(
    config: OutdoorConfig, states: Mapping[str, Any],
) -> dict[str, float | None]:
    """Map stable logical references to normalized measurements.

    No copy of the original HA state is modified, and no MQTT topic is read.
    """
    if config.source_model != "sensors":
        return {}
    readings: dict[str, float | None] = {}
    for provider in config.providers:
        state = states.get(provider.entity_id)
        if state is None or getattr(state, "state", None) in (
            "unknown", "unavailable", "", "none", None,
        ):
            attrs = {}
        else:
            attrs = getattr(state, "attributes", None) or {}
        readings[provider.provider_id + ".temperature"] = _temperature(
            attrs.get("temperature"), attrs.get("temperature_unit"),
        )
        readings[provider.provider_id + ".humidity"] = _humidity(
            attrs.get("humidity"),
        )

    for sensor in config.physical_sensors:
        state = states.get(sensor.entity_id)
        if state is None or getattr(state, "state", None) in (
            "unknown", "unavailable", "", "none", None,
        ):
            readings[sensor.sensor_id] = None
            continue
        raw = getattr(state, "state", None)
        attrs = getattr(state, "attributes", None) or {}
        readings[sensor.sensor_id] = (
            _temperature(raw, attrs.get("unit_of_measurement"))
            if sensor.quantity == "temperature" else _humidity(raw)
        )
    return readings


def weather_condition_entity(config: OutdoorConfig) -> str | None:
    """Forecast/condition remains associated with a real HA weather entity."""
    if config.source_model == "sensors":
        providers = {p.provider_id: p.entity_id for p in config.providers}
        for name in (*config.temperature_sources, *config.humidity_sources):
            if "." in name:
                provider_id = name.rsplit(".", 1)[0]
                if provider_id in providers:
                    return providers[provider_id]
        return config.providers[0].entity_id if config.providers else None

    from .weather import select_weather_source
    return select_weather_source(
        config.temperature_sources, config.humidity_sources,
    )


def source_entity(config: OutdoorConfig, source_id: str) -> str | None:
    """Resolve logical sensor identity to its original HA entity."""
    if config.source_model != "sensors":
        return source_id
    for provider in config.providers:
        if source_id in (
            provider.provider_id + ".temperature",
            provider.provider_id + ".humidity",
        ):
            return provider.entity_id
    for sensor in config.physical_sensors:
        if source_id == sensor.sensor_id:
            return sensor.entity_id
    return None
