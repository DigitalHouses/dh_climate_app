from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .ha_client import HaState


PRECIPITATION_TYPES = frozenset({"rain", "snow", "mixed", "hail"})
_RAIN_CONDITIONS = frozenset({"rainy", "pouring", "lightning-rainy"})
_SNOW_CONDITIONS = frozenset({"snowy"})
_MIXED_CONDITIONS = frozenset({"snowy-rainy"})
_HAIL_CONDITIONS = frozenset({"hail"})


@dataclass(frozen=True)
class WeatherState:
    source_entity: str
    condition: str
    precipitation_type: str
    precipitation_mm: float | None
    forecast_at: datetime | None
    observed_at: datetime

    @property
    def precipitation_active(self) -> bool:
        return self.precipitation_type in PRECIPITATION_TYPES


def select_weather_source(
    temperature_sources: Sequence[str],
    humidity_sources: Sequence[str],
) -> str | None:
    seen: set[str] = set()
    for entity_id in (*temperature_sources, *humidity_sources):
        if entity_id in seen:
            continue
        seen.add(entity_id)
        if entity_id.startswith("weather."):
            return entity_id
    return None


def precipitation_type_from_condition(condition: str) -> str:
    normalized = str(condition or "").strip().lower()
    if normalized in _RAIN_CONDITIONS:
        return "rain"
    if normalized in _SNOW_CONDITIONS:
        return "snow"
    if normalized in _MIXED_CONDITIONS:
        return "mixed"
    if normalized in _HAIL_CONDITIONS:
        return "hail"
    if normalized in {"unknown", "unavailable", ""}:
        return "unknown"
    return "none"


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _to_mm(value: object, unit: object) -> float | None:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None

    normalized = str(unit or "mm").strip().lower()
    if normalized == "mm":
        return round(amount, 3)
    if normalized == "cm":
        return round(amount * 10.0, 3)
    if normalized in {"in", "inch", "inches"}:
        return round(amount * 25.4, 3)
    return None


def _forecast_entries(
    response: Mapping[str, Any] | None,
    entity_id: str,
) -> list[Mapping[str, Any]]:
    if not isinstance(response, Mapping):
        return []
    service_response = response.get("service_response")
    if isinstance(service_response, Mapping):
        container = service_response
    else:
        container = response
    item = container.get(entity_id)
    if not isinstance(item, Mapping):
        return []
    raw = item.get("forecast")
    if not isinstance(raw, list):
        return []
    return [entry for entry in raw if isinstance(entry, Mapping)]


def _current_hour_entry(
    entries: Sequence[Mapping[str, Any]],
    observed_at: datetime,
) -> Mapping[str, Any] | None:
    if not entries:
        return None

    dated: list[tuple[datetime, Mapping[str, Any]]] = []
    for entry in entries:
        parsed = _parse_datetime(entry.get("datetime"))
        if parsed is not None:
            dated.append((parsed, entry))
    if not dated:
        return entries[0]

    dated.sort(key=lambda item: item[0])
    observed = observed_at.astimezone(timezone.utc)
    previous: Mapping[str, Any] | None = None
    for stamp, entry in dated:
        stamp_utc = stamp.astimezone(timezone.utc)
        if stamp_utc > observed:
            return previous or entry
        previous = entry
    return previous


def build_weather_state(
    *,
    source_entity: str,
    ha_state: HaState | None,
    hourly_forecast_response: Mapping[str, Any] | None,
    observed_at: datetime,
) -> WeatherState | None:
    if ha_state is None:
        return None

    condition = ha_state.state.strip().lower()
    precipitation_type = precipitation_type_from_condition(condition)
    entry = _current_hour_entry(
        _forecast_entries(hourly_forecast_response, source_entity),
        observed_at,
    )

    precipitation_mm: float | None = None
    forecast_at: datetime | None = None
    if entry is not None:
        precipitation_mm = _to_mm(
            entry.get("precipitation"),
            ha_state.attributes.get("precipitation_unit"),
        )
        forecast_at = _parse_datetime(entry.get("datetime"))

    return WeatherState(
        source_entity=source_entity,
        condition=condition,
        precipitation_type=precipitation_type,
        precipitation_mm=precipitation_mm,
        forecast_at=forecast_at,
        observed_at=observed_at,
    )
