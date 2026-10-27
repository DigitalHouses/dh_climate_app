from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .config import AppConfig
from .ha_client import HaState
from .rooms import RoomState


@dataclass(frozen=True)
class Demand:
    """A definite ON, a definite OFF, or unknown (None).

    Count is only authoritative when every candidate is known.
    A confirmed ON remains true even when other candidates are unknown.
    """
    active: bool | None
    count: int | None
    members: tuple[dict[str, str], ...] = ()


def _combine(known: list[dict[str, str]], unknown: bool) -> Demand:
    active = True if known else None if unknown else False
    return Demand(
        active=active,
        count=None if unknown else len(known),
        members=tuple(known) if not unknown else (),
    )


def room_demand(
    config: AppConfig,
    states: Mapping[str, RoomState],
    direction: str,
) -> Demand:
    if direction not in {"heat", "cool"}:
        raise ValueError("direction must be heat or cool")
    requested = "heating" if direction == "heat" else "cooling"
    known: list[dict[str, str]] = []
    unknown = False
    for room in config.rooms:
        state = states.get(room.room_id)
        if state is None or not state.available:
            unknown = True
            continue
        mode = str(state.hvac_mode)
        action = str(state.hvac_action)
        if mode not in {"heat", "cool", "off"} or action not in {
            "heating", "cooling", "idle", "off"
        }:
            unknown = True
        elif mode == direction and action == requested:
            known.append({"id": room.room_id, "name": room.name})
        elif action in {"heating", "cooling"} and not (
            (mode == "heat" and action == "heating")
            or (mode == "cool" and action == "cooling")
        ):
            # Contradictory mode/action is not a confirmed OFF.
            unknown = True
        # Otherwise this room has no demand in the requested direction.
    return _combine(known, unknown)


def device_demand(
    config: AppConfig,
    states: Mapping[str, HaState],
    direction: str,
) -> Demand:
    if direction not in {"heat", "cool"}:
        raise ValueError("direction must be heat or cool")
    requested = "heating" if direction == "heat" else "cooling"
    known: list[dict[str, str]] = []
    unknown = False
    for room in config.rooms:
        for device in room.devices:
            if device.control != "device" or device.function not in {
                direction, "heat_cool"
            }:
                continue
            state = states.get(device.entity_id)
            if state is None or state.state in {"unknown", "unavailable"}:
                unknown = True
                continue
            mode = state.state
            action = state.attributes.get("hvac_action")
            if mode not in {"heat", "cool", "heat_cool", "off", "auto"}:
                unknown = True
            elif action is None and mode == "off":
                # A confirmed OFF is not requesting heat or cool.
                continue
            elif action not in {"heating", "cooling", "idle", "off"}:
                unknown = True
            elif action == requested and mode in {direction, "heat_cool", "auto"}:
                known.append({
                    "entity_id": device.entity_id,
                    "room_id": room.room_id,
                    "room_name": room.name,
                })
            elif action in {"heating", "cooling"} and mode == "off":
                unknown = True
            elif action in {"heating", "cooling"} and (
                (mode == "heat" and action != "heating")
                or (mode == "cool" and action != "cooling")
            ):
                unknown = True
            # Otherwise action is idle/off or demand is opposite direction.
    return _combine(known, unknown)


def actual_demand(
    source: str,
    states: Mapping[str, HaState],
) -> bool | None:
    """Read only the explicitly configured aggregator binary sensor."""
    if not source:
        return None
    state = states.get(source)
    if state is None:
        return None
    if state.state == "on":
        return True
    if state.state == "off":
        return False
    return None
