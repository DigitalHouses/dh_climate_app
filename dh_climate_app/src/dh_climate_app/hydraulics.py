"""Read-only hydraulic resource graph, independent of the HVAC control engine.

All objects are explicit. Links point to one canonical device in the manifest;
missing telemetry remains missing, never a fabricated OFF or zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Callable, Mapping

SLUG = re.compile(r"^[a-z0-9][a-z0-9_]*$")
ENTITY_DOMAINS = (
    "sensor", "binary_sensor", "switch", "climate", "number",
    "input_boolean", "input_number", "valve", "select",
)
NODE_KINDS = ("separators", "groups", "circuits", "pumps", "actuators", "valves", "aggregators")


@dataclass(frozen=True)
class HydraulicItem:
    item_id: str
    name: str
    signals: Mapping[str, str]
    # Optional edges. A pump/valve/actuator has one canonical declaration
    # and may be referenced by more than one group/circuit.
    separator_id: str | None = None
    group_id: str | None = None
    aggregator_id: str | None = None
    temperature_class: str | None = None
    room_id: str | None = None
    pump_ids: tuple[str, ...] = ()
    actuator_ids: tuple[str, ...] = ()
    valve_ids: tuple[str, ...] = ()
    terminals: tuple["HydraulicTerminal", ...] = ()
    device_type: str | None = None


@dataclass(frozen=True)
class HydraulicTerminal:
    item_id: str
    name: str
    room_id: str | None = None
    entity_id: str | None = None


@dataclass(frozen=True)
class HydraulicsConfig:
    separators: tuple[HydraulicItem, ...] = ()
    groups: tuple[HydraulicItem, ...] = ()
    circuits: tuple[HydraulicItem, ...] = ()
    pumps: tuple[HydraulicItem, ...] = ()
    actuators: tuple[HydraulicItem, ...] = ()
    valves: tuple[HydraulicItem, ...] = ()
    aggregators: tuple[HydraulicItem, ...] = ()


def _reject(message: str) -> None:
    # Imported lazily: config.py imports this module's dataclasses.
    from .config import ConfigError
    raise ConfigError(message)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _reject(f"{path} must be an object")
    return value


def _id(value: Any, path: str) -> str:
    if not isinstance(value, str) or not SLUG.fullmatch(value):
        _reject(f"{path} must be a lowercase snake_case id")
    return value


def _name(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 160:
        _reject(f"{path} must have a name (1-160 characters)")
    return value.strip()


def _optional_id(value: Any, path: str) -> str | None:
    return None if value is None else _id(value, path)


def _id_list(value: Any, path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        _reject(f"{path} must be a list")
    ids = tuple(_id(item, f"{path}[{i}]") for i, item in enumerate(value))
    if len(ids) != len(set(ids)):
        _reject(f"{path} contains duplicate references")
    return ids


def parse_hydraulics(
    raw: Any, *, room_ids: set[str],
    entity_parser: Callable[..., str],
) -> HydraulicsConfig:
    if raw is None:
        return HydraulicsConfig()
    config = _mapping(raw, "hydraulics")
    if set(config) - set(NODE_KINDS):
        _reject(f"hydraulics: unknown keys: {sorted(set(config) - set(NODE_KINDS))}")
    result: dict[str, tuple[HydraulicItem, ...]] = {}
    allowed_base = {"id", "name", "signals"}
    specific = {
        "separators": set(),
        "groups": {"separator_id", "temperature_class", "aggregator_id",
                   "pump_ids", "actuator_ids", "valve_ids"},
        "circuits": {"group_id", "room_id", "pump_ids", "actuator_ids",
                     "valve_ids", "terminals"},
        "pumps": set(), "actuators": set(), "valves": set(),
        "aggregators": {"device_type"},
    }

    for kind in NODE_KINDS:
        entries = config.get(kind, [])
        if not isinstance(entries, list):
            _reject(f"hydraulics.{kind} must be a list")
        used: set[str] = set()
        nodes: list[HydraulicItem] = []
        for i, raw_item in enumerate(entries):
            path = f"hydraulics.{kind}[{i}]"
            item = _mapping(raw_item, path)
            extra = set(item) - allowed_base - specific[kind]
            if extra:
                _reject(f"{path}: unknown keys: {sorted(extra)}")
            item_id = _id(item.get("id"), f"{path}.id")
            if item_id in used:
                _reject(f"{path}: duplicate id {item_id}")
            used.add(item_id)
            name = _name(item.get("name"), f"{path}.name")
            raw_signals = _mapping(item.get("signals", {}), f"{path}.signals")
            signals: dict[str, str] = {}
            for role, entity in raw_signals.items():
                role_id = _id(role, f"{path}.signals key")
                signals[role_id] = entity_parser(
                    entity, f"{path}.signals.{role_id}", ENTITY_DOMAINS,
                )

            terminals: list[HydraulicTerminal] = []
            if kind == "circuits":
                raw_terminals = item.get("terminals", [])
                if not isinstance(raw_terminals, list):
                    _reject(f"{path}.terminals must be a list")
                terminal_ids: set[str] = set()
                for j, raw_terminal in enumerate(raw_terminals):
                    tp = f"{path}.terminals[{j}]"
                    terminal = _mapping(raw_terminal, tp)
                    if set(terminal) - {"id", "name", "room_id", "entity_id"}:
                        _reject(f"{tp}: unknown keys")
                    tid = _id(terminal.get("id"), f"{tp}.id")
                    if tid in terminal_ids:
                        _reject(f"{tp}: duplicate id {tid}")
                    terminal_ids.add(tid)
                    terminal_room = _optional_id(terminal.get("room_id"), f"{tp}.room_id")
                    if terminal_room and terminal_room not in room_ids:
                        _reject(f"{tp}.room_id references unknown room {terminal_room}")
                    entity_id = (
                        entity_parser(terminal["entity_id"], f"{tp}.entity_id", ENTITY_DOMAINS)
                        if "entity_id" in terminal else None
                    )
                    terminals.append(HydraulicTerminal(
                        tid, _name(terminal.get("name"), f"{tp}.name"),
                        terminal_room, entity_id,
                    ))

            room_id = _optional_id(item.get("room_id"), f"{path}.room_id")
            if room_id and room_id not in room_ids:
                _reject(f"{path}.room_id references unknown room {room_id}")
            temperature_class = item.get("temperature_class")
            if kind == "groups":
                if temperature_class not in ("high", "low"):
                    _reject(f"{path}.temperature_class must be high or low")
            device_type = item.get("device_type")
            if kind == "aggregators" and device_type not in ("hardware", "virtual"):
                _reject(f"{path}.device_type must be hardware or virtual")
            nodes.append(HydraulicItem(
                item_id=item_id, name=name, signals=signals,
                separator_id=_optional_id(item.get("separator_id"), f"{path}.separator_id"),
                group_id=_optional_id(item.get("group_id"), f"{path}.group_id"),
                aggregator_id=_optional_id(item.get("aggregator_id"), f"{path}.aggregator_id"),
                temperature_class=temperature_class,
                room_id=room_id,
                pump_ids=_id_list(item.get("pump_ids", []), f"{path}.pump_ids"),
                actuator_ids=_id_list(item.get("actuator_ids", []), f"{path}.actuator_ids"),
                valve_ids=_id_list(item.get("valve_ids", []), f"{path}.valve_ids"),
                terminals=tuple(terminals), device_type=device_type,
            ))
        result[kind] = tuple(nodes)

    known = {kind: {part.item_id for part in parts} for kind, parts in result.items()}
    for kind in ("groups", "circuits"):
        for part in result[kind]:
            path = f"hydraulics.{kind}.{part.item_id}"
            parents = (
                {"separator_id": "separators", "aggregator_id": "aggregators"}
                if kind == "groups" else {"group_id": "groups"}
            )
            for attr, target_kind in parents.items():
                ref = getattr(part, attr)
                if ref and ref not in known[target_kind]:
                    _reject(f"{path}.{attr}: unknown {target_kind} id {ref}")
            for attr, target_kind in (
                ("pump_ids", "pumps"), ("actuator_ids", "actuators"),
                ("valve_ids", "valves"),
            ):
                for ref in getattr(part, attr):
                    if ref not in known[target_kind]:
                        _reject(f"{path}.{attr}: unknown {target_kind} id {ref}")

    return HydraulicsConfig(**result)


def hydraulic_entity_ids(config: HydraulicsConfig) -> frozenset[str]:
    result: set[str] = set()
    for kind in NODE_KINDS:
        for part in getattr(config, kind):
            result.update(part.signals.values())
            result.update(t.entity_id for t in part.terminals if t.entity_id)
    return frozenset(result)


def hydraulic_snapshot(
    config: HydraulicsConfig,
    states: Mapping[str, Any],
    signals_fn: Callable[..., list[dict[str, Any]]],
    entity_fn: Callable[..., dict[str, Any] | None],
) -> dict[str, Any]:
    """Project only configured equipment and the actual HA values of its sensors."""
    out: dict[str, Any] = {}
    for kind in NODE_KINDS:
        items = []
        for part in getattr(config, kind):
            items.append({
                "id": part.item_id, "name": part.name,
                "signals": signals_fn(part.signals, states),
                "separator_id": part.separator_id,
                "group_id": part.group_id,
                "aggregator_id": part.aggregator_id,
                "temperature_class": part.temperature_class,
                "room_id": part.room_id,
                "pump_ids": list(part.pump_ids),
                "actuator_ids": list(part.actuator_ids),
                "valve_ids": list(part.valve_ids),
                "device_type": part.device_type,
                "terminals": [
                    {"id": t.item_id, "name": t.name,
                     "room_id": t.room_id,
                     "entity_id": t.entity_id,
                     "observed": entity_fn(t.entity_id, states)}
                    for t in part.terminals
                ],
            })
        out[kind] = items
    return out
