from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .config import AppConfig, DeviceConfig
from .core import Season, _numeric_state
from .ha_client import HaState
from .rooms import RoomState


@dataclass(frozen=True)
class Demand:
    """ON, OFF or UNKNOWN. Count is exact only when all candidates are known."""
    active: bool | None
    count: int | None
    members: tuple[dict[str, str], ...] = ()


def _combine(known: list[dict[str, str]], unknown: bool) -> Demand:
    return Demand(
        active=True if known else None if unknown else False,
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
            unknown = True
    return _combine(known, unknown)


def _climate_request(state: HaState, direction: str) -> bool | None:
    mode = state.state
    action = state.attributes.get("hvac_action")
    if mode not in {"heat", "cool", "heat_cool", "auto", "off"}:
        return None
    if mode == "off":
        return False if action in (None, "off", "idle") else None
    if action not in {"heating", "cooling", "idle", "off"}:
        return None
    if action in {"idle", "off"}:
        return False
    if (mode == "heat" and action != "heating") or (
        mode == "cool" and action != "cooling"
    ):
        return None
    return action == ("heating" if direction == "heat" else "cooling")


def _switch_request(
    device: DeviceConfig,
    state: HaState,
    snapshot: Mapping[str, HaState],
    direction: str,
) -> bool | None:
    if state.state not in {"on", "off"}:
        return None
    if device.device_class.value == "slow":
        if direction != "heat":
            return False
        # Opening a floor valve as a fail-safe is not itself a heat
        # request. A sensorless SLOW is not a thermostat.
        if device.temperature_sensor is None:
            return False
        screed = snapshot.get(device.temperature_sensor)
        if screed is None or _numeric_state(screed.state) is None:
            return None
    if device.actuator == "normal_open":
        return state.state == "off"
    return state.state == "on"


def device_demand(
    config: AppConfig,
    states: Mapping[str, HaState],
    direction: str,
    *,
    device_type: str | None = None,
    resource: str | None = None,
    room_states: Mapping[str, RoomState] | None = None,
) -> Demand:
    """Observe device requests without creating a second thermostat.

    Resource membership must be explicitly configured. Room demand is never
    counted as an independent resource input.
    """
    if direction not in {"heat", "cool"}:
        raise ValueError("direction must be heat or cool")
    if device_type not in {None, "hardware", "virtual"}:
        raise ValueError("invalid device_type")
    if resource not in {None, "home_heating", "vrf"}:
        raise ValueError("invalid resource")
    known: list[dict[str, str]] = []
    unknown = False
    for room in config.rooms:
        room_state = None if room_states is None else room_states.get(room.room_id)
        for device in room.devices:
            if device_type is not None and device.device_type != device_type:
                continue
            if resource is not None and device.resource != resource:
                continue
            if device.function not in {direction, "heat_cool"}:
                continue
            if room_states is not None and room_state is None:
                unknown = True
                continue
            if room_state is not None:
                if room_state.season.value != direction:
                    continue
                if direction == "cool" and room_state.window_cooling_blocked:
                    # Suppression is a command; only observed OFF proves
                    # the device stopped. Never claim false OFF pre-confirmation.
                    pass
            state = states.get(device.entity_id)
            if state is None or state.state in {"unknown", "unavailable"}:
                unknown = True
                continue
            if device.entity_id.startswith("climate."):
                active = _climate_request(state, direction)
            else:
                active = _switch_request(device, state, states, direction)
            if active is None:
                unknown = True
            elif active:
                known.append({
                    "entity_id": device.entity_id,
                    "room_id": room.room_id,
                    "room_name": room.name,
                    "device_type": device.device_type,
                })
    return _combine(known, unknown)


def resource_request(
    config: AppConfig,
    states: Mapping[str, HaState],
    direction: str,
    *,
    resource: str,
    room_states: Mapping[str, RoomState],
) -> Demand:
    if resource == "home_heating":
        if config.heating_source is None or direction != "heat":
            raise ValueError("home_heating request needs a configured HEAT source")
    elif resource == "vrf":
        if config.vrf_enabled is not True or direction != "cool":
            raise ValueError("VRF cool request needs vrf: on")
    else:
        raise ValueError("unknown resource")
    return device_demand(
        config, states, direction,
        resource=resource, room_states=room_states,
    )
