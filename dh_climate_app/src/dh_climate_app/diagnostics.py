"""Bounded, secret-aware support diagnostics for the Climate Explorer.

Export is initiated explicitly by an HA administrator. No HA secrets, full
Supervisor options, extra subscriptions or periodic polling are introduced.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import logging
import math
import re
from typing import Any, Mapping

SECRET_FIELD = re.compile(
    r"(?:password|passwd|secret|token|credential|authorization|cookie|"
    r"api[_-]?key|private[_-]?key|access[_-]?key|session[_-]?id|"
    r"author[_-]?id|user[_-]?id)",
    re.IGNORECASE,
)
SENSITIVE_PARAMETER = re.compile(
    r"([?&](?:access_token|token|api_key|password|secret|signature|"
    r"auth|code|key)=)[^&#\s]+", re.IGNORECASE,
)
AUTH_HEADER = re.compile(
    r"(\b(?:Bearer|Basic)\s+)[A-Za-z0-9._~+/-]+={0,2}",
    re.IGNORECASE,
)
URL_PASSWORD = re.compile(
    r"(https?://)[^/\s:@]+:[^/\s@]+@", re.IGNORECASE,
)


def mask_text(value: str) -> str:
    """Protect credentials pasted into incidental labels/error messages."""
    value = SENSITIVE_PARAMETER.sub(r"\1[REDACTED]", value)
    value = AUTH_HEADER.sub(r"\1[REDACTED]", value)
    return URL_PASSWORD.sub(r"\1[REDACTED]@", value)


def sanitize_export(value: Any, *, depth: int = 0) -> Any:
    """Allowlisted JSON primitives, recursive credential-key masking."""
    if depth >= 24:
        return "[DEPTH LIMIT]"
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[REDACTED]" if SECRET_FIELD.search(str(key))
                else sanitize_export(item, depth=depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_export(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, bool):
        return value
    return str(value)[:256]


ENTITY_ID = re.compile(
    r"^(?:sensor|binary_sensor|climate|humidifier|weather|number|switch|"
    r"input_boolean|input_number|input_select|input_text|select|fan|cover|"
    r"valve|water_heater)\.[a-z0-9_]+$"
)


def _referenced_entities(value: Any, result: set[str], *, depth: int = 0) -> None:
    """Collect only explicit HA-style IDs from configured/runtime data."""
    if depth > 20:
        return
    if isinstance(value, str) and ENTITY_ID.fullmatch(value):
        result.add(value)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            # Keys can be HA entity IDs in some config projections.
            if isinstance(key, str) and ENTITY_ID.fullmatch(key):
                result.add(key)
            _referenced_entities(item, result, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _referenced_entities(item, result, depth=depth + 1)


def scope_entity_catalog(
    catalog: Mapping[str, Any],
    *, manifest: Any = None, snapshot: Any = None,
    labels: Any = None, runtime: Any = None,
) -> dict[str, Any]:
    """Keep Climate-related HA entities, never an unrelated household dump.

    The Explorer's regular entity picker remains unchanged. The diagnostic
    file stores compact domain/integration counts for omitted entities.
    """
    used: set[str] = set()
    for part in (manifest, snapshot, runtime):
        _referenced_entities(part, used)
    raw_entities = catalog.get("entities")
    entries = raw_entities if isinstance(raw_entities, list) else []
    selected: list[dict[str, Any]] = []
    by_domain: dict[str, int] = {}
    by_integration: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        domain = str(entry.get("domain") or "unknown")
        integration = str(entry.get("integration") or "unknown")
        by_domain[domain] = by_domain.get(domain, 0) + 1
        by_integration[integration] = by_integration.get(integration, 0) + 1
        entity_id = entry.get("entity_id")
        if not isinstance(entity_id, str):
            continue
        if (
            entity_id in used or
            bool(entry.get("climate_source_id")) or
            entry.get("climate_avg24_sensor") is True or
            entity_id.startswith((
                "sensor.dh_climate_app_",
                "binary_sensor.dh_climate_app_",
                "climate.dh_climate_app_",
                "number.dh_climate_app_",
            ))
        ):
            selected.append(dict(entry))

    used_areas = {
        row.get("area_id") for row in selected
        if isinstance(row.get("area_id"), str)
    }
    if isinstance(labels, Mapping):
        room_areas = labels.get("room_areas")
        if isinstance(room_areas, Mapping):
            used_areas.update(
                value for value in room_areas.values()
                if isinstance(value, str)
            )
    raw_areas = catalog.get("areas")
    all_areas = raw_areas if isinstance(raw_areas, list) else []
    areas = [
        dict(area) for area in all_areas
        if isinstance(area, Mapping) and area.get("id") in used_areas
    ]
    return {
        "areas": areas,
        "entities": selected,
        "truncated": bool(catalog.get("truncated", False)),
        "diagnostic_scope": "configured_or_app_owned",
        "total_entities": len(entries),
        "omitted_entities": len(entries) - len(selected),
        "total_areas": len(all_areas),
        "counts_by_domain": dict(sorted(by_domain.items())),
        "counts_by_integration": dict(sorted(by_integration.items())),
    }


class BoundedDiagnosticLogHandler(logging.Handler):
    """Capture only warning/error messages from app loggers, up to 120 entries."""

    def __init__(self, capacity: int = 120) -> None:
        super().__init__(level=logging.WARNING)
        self.entries: deque[dict[str, str]] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            formatted = mask_text(self.format(record))[:3000]
            self.entries.append({
                "at": datetime.fromtimestamp(
                    record.created, tz=timezone.utc
                ).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": formatted,
            })
        except Exception:
            self.handleError(record)

    def snapshot(self) -> list[dict[str, str]]:
        return list(self.entries)
