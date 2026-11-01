"""On-demand, read-only Home Assistant entity catalogue for the Explorer picker.

No subscriptions, persistent registry mirror or new polling timers. Only
whitelisted UI fields leave the app; no credentials or arbitrary attributes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from typing import Any, Mapping

import websockets

LOGGER = logging.getLogger(__name__)
PICKER_DOMAINS = frozenset({
    "sensor", "binary_sensor", "climate", "switch", "humidifier",
    "weather", "number",
})
MAX_ENTITIES = 8000
CLIMATE_WEATHER_UNIQUE_ID = re.compile(
    r"^dh_climate_app_provider_([a-z][a-z0-9_]{0,63})_(temperature|humidity)$"
)


def _weather_number(attributes: Mapping[str, Any], key: str, domain: str) -> float | None:
    if domain != "weather":
        return None
    value = attributes.get(key)
    if type(value) not in (int, float):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _string(value: Any, limit: int = 160) -> str | None:
    if not isinstance(value, str):
        return None
    clean = value.strip()
    return clean[:limit] if clean else None


def build_catalog(
    states: list[Mapping[str, Any]],
    registry: Mapping[str, Any] | list[Mapping[str, Any]],
    devices: list[Mapping[str, Any]],
    areas: list[Mapping[str, Any]],
) -> dict[str, Any]:
    area_names = {
        a["area_id"]: _string(a.get("name"), 100)
        for a in areas if isinstance(a, Mapping)
        and isinstance(a.get("area_id"), str)
    }
    device_map = {
        d["id"]: d for d in devices if isinstance(d, Mapping)
        and isinstance(d.get("id"), str)
    }
    entries = registry.get("entities", []) if isinstance(registry, Mapping) else registry
    entity_map: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        entity_id = entry.get("ei", entry.get("entity_id"))
        if isinstance(entity_id, str):
            entity_map[entity_id] = entry

    result = []
    seen: set[str] = set()
    for state in states:
        if not isinstance(state, Mapping):
            continue
        entity_id = state.get("entity_id")
        if not isinstance(entity_id, str) or "." not in entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        if domain not in PICKER_DOMAINS or entity_id in seen:
            continue
        seen.add(entity_id)
        attributes = state.get("attributes")
        attributes = attributes if isinstance(attributes, Mapping) else {}
        reg = entity_map.get(entity_id, {})
        dev_id = reg.get("di", reg.get("device_id"))
        device = device_map.get(dev_id, {})
        area_id = reg.get("ai", reg.get("area_id")) or device.get("area_id")
        raw_state = state.get("state")
        available = raw_state not in ("unknown", "unavailable", None)
        raw_unique_id = reg.get("uid", reg.get("unique_id"))
        source_match = (
            CLIMATE_WEATHER_UNIQUE_ID.fullmatch(raw_unique_id)
            if isinstance(raw_unique_id, str) and domain == "sensor"
            else None
        )
        result.append({
            "entity_id": entity_id,
            # Only expose app-owned unique IDs, as a logical source key.
            "climate_source_id": (
                source_match.group(1) + "." + source_match.group(2)
                if source_match else None
            ),
            "name": _string(attributes.get("friendly_name")) or
                    _string(reg.get("en", reg.get("name"))) or entity_id,
            "domain": domain,
            "device_class": _string(attributes.get("device_class"), 64),
            "unit": _string(attributes.get("unit_of_measurement"), 24),
            "state": _string(raw_state, 80),
            "available": bool(available),
            "area_id": area_id if isinstance(area_id, str) else None,
            "area_name": area_names.get(area_id),
            "device_name": _string(device.get("name_by_user") or device.get("name")),
            # HA Entity Registry platform: compact pl or full platform.
            # Never infer integration origin from name or domain.
            "integration": _string(reg.get("pl", reg.get("platform")), 64),
            # Explicit whitelist: weather state is a condition string.
            # Temperature/humidity are attributes; no other HA attributes leak.
            "temperature": _weather_number(attributes, "temperature", domain),
            "temperature_unit": (
                _string(attributes.get("temperature_unit"), 8)
                if domain == "weather" else None
            ),
            "humidity": _weather_number(attributes, "humidity", domain),
        })
        if len(result) >= MAX_ENTITIES:
            break
    result.sort(key=lambda e: (e["name"].casefold(), e["entity_id"]))
    return {
        "areas": [
            {"id": area_id, "name": area_name}
            for area_id, area_name in sorted(
                area_names.items(), key=lambda x: (x[1] or "").casefold()
            )
        ],
        "entities": result,
        "truncated": len(result) >= MAX_ENTITIES,
    }


class EntityCatalog:
    def __init__(self, *, token: str,
                 websocket_url: str = "ws://supervisor/core/websocket",
                 ttl_seconds: float = 30):
        self.token = token
        self.websocket_url = websocket_url
        self.ttl_seconds = ttl_seconds
        self._expires = 0.0
        self._cached: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> dict[str, Any]:
        async with self._lock:
            if self._cached is not None and time.monotonic() < self._expires:
                return self._cached
            data = await asyncio.wait_for(self._fetch(), timeout=25)
            self._cached = data
            self._expires = time.monotonic() + self.ttl_seconds
            return data

    async def _fetch(self) -> dict[str, Any]:
        async with websockets.connect(
            self.websocket_url, ping_interval=20, ping_timeout=10,
            open_timeout=8, close_timeout=3, max_size=16 * 1024 * 1024,
        ) as ws:
            hello = json.loads(await ws.recv())
            if hello.get("type") != "auth_required":
                raise RuntimeError("Unexpected HA WebSocket handshake")
            await ws.send(json.dumps({"type": "auth", "access_token": self.token}))
            auth = json.loads(await ws.recv())
            if auth.get("type") != "auth_ok":
                raise RuntimeError("HA WebSocket authorization failed")

            async def request(id_: int, type_: str) -> Any:
                await ws.send(json.dumps({"id": id_, "type": type_}))
                response = json.loads(await ws.recv())
                if response.get("type") != "result" or response.get("id") != id_:
                    raise RuntimeError("Unexpected HA WebSocket reply")
                if not response.get("success"):
                    raise RuntimeError(f"HA catalogue command unavailable: {type_}")
                return response.get("result")

            states = await request(1, "get_states")
            # The area/device registries are optional enrichment. A missing
            # registry must not make the basic entity search unusable.
            reg, dev, areas = {}, [], []
            for id_, command in (
                (2, "config/entity_registry/list_for_display"),
                (3, "config/device_registry/list"),
                (4, "config/area_registry/list"),
            ):
                try:
                    value = await request(id_, command)
                    if id_ == 2 and isinstance(value, (dict, list)):
                        reg = value
                    elif id_ == 3 and isinstance(value, list):
                        dev = value
                    elif id_ == 4 and isinstance(value, list):
                        areas = value
                except RuntimeError as exc:
                    LOGGER.warning("HA catalogue enrichment: %s", exc)
            # The compact display registry can omit unique_id. A full
            # registry read lets us resolve renamed HA entity_ids reliably.
            # The command is optional: fallback keeps the picker usable
            # with restricted HA credentials.
            try:
                full = await request(5, "config/entity_registry/list")
                if isinstance(full, list):
                    reg = full
            except RuntimeError as exc:
                LOGGER.debug("Full entity registry unavailable: %s", exc)
            if not isinstance(states, list):
                raise RuntimeError("HA states catalogue unavailable")
            return build_catalog(states, reg, dev, areas)
