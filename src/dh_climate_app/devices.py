from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig, DeviceConfig
from .core import DeviceClass, HvacAction, Season
from .humidity import HumidityState
from .rooms import RoomState


@dataclass(frozen=True)
class DesiredDeviceState:
    entity_id: str
    domain: str
    power: bool | None = None
    hvac_mode: str | None = None
    target_temperature: float | None = None
    target_humidity: float | None = None
    source: str = ""

    @property
    def signature(self) -> tuple[object, ...]:
        return (
            self.entity_id,
            self.domain,
            self.power,
            self.hvac_mode,
            self.target_temperature,
            self.target_humidity,
            self.source,
        )


def _function_matches(function: str, action: HvacAction) -> bool:
    if action is HvacAction.HEATING:
        return function in {"heat", "heat_cool"}
    if action is HvacAction.COOLING:
        return function in {"cool", "heat_cool"}
    return False


def _thermal_inhibited(
    device: DeviceConfig,
    *,
    room_state: RoomState,
    outdoor_temperature: float | None,
    heating: bool,
) -> bool:
    if (
        device.window_policy == "turn_off"
        and room_state.window_state == "open"
    ):
        return True

    minimum = device.min_heating_outdoor_temperature
    if (
        heating
        and minimum is not None
        and outdoor_temperature is not None
        and outdoor_temperature < minimum
    ):
        return True

    return False


def compile_room_devices(
    *,
    config: AppConfig,
    room_states: dict[str, RoomState],
    humidity_states: dict[str, HumidityState],
    outdoor_temperature: float | None = None,
) -> list[DesiredDeviceState]:
    """Compile physical desired state from room truth.

    Window state remains context, not thermostat truth: it can inhibit only
    devices whose explicit window_policy is turn_off. Likewise the legacy
    low-outdoor-temperature AC safety is represented as an explicit
    per-device heating limit instead of a device-type registry.
    """
    desired: list[DesiredDeviceState] = []

    for room in config.rooms:
        state = room_states[room.room_id]
        for device in room.devices:
            domain = device.entity_id.split(".", 1)[0]

            if device.device_class is DeviceClass.SLOW:
                active = state.season is Season.HEAT
                if active and _thermal_inhibited(
                    device,
                    room_state=state,
                    outdoor_temperature=outdoor_temperature,
                    heating=True,
                ):
                    active = False
                desired.append(
                    DesiredDeviceState(
                        entity_id=device.entity_id,
                        domain=domain,
                        hvac_mode="heat" if active else "off",
                        target_temperature=(
                            device.target_temperature if active else None
                        ),
                        source=f"room:{room.room_id}:slow",
                    )
                )
                continue

            active = _function_matches(
                device.function,
                state.control_action,
            )
            heating = (
                active
                and state.control_action is HvacAction.HEATING
            )
            if active and _thermal_inhibited(
                device,
                room_state=state,
                outdoor_temperature=outdoor_temperature,
                heating=heating,
            ):
                active = False

            if domain == "switch":
                desired.append(
                    DesiredDeviceState(
                        entity_id=device.entity_id,
                        domain=domain,
                        power=active,
                        source=f"room:{room.room_id}:fast",
                    )
                )
            else:
                if active and state.control_action is HvacAction.HEATING:
                    mode = "heat"
                elif active and state.control_action is HvacAction.COOLING:
                    mode = "cool"
                else:
                    mode = "off"
                desired.append(
                    DesiredDeviceState(
                        entity_id=device.entity_id,
                        domain=domain,
                        hvac_mode=mode,
                        target_temperature=(
                            state.target_temperature if active else None
                        ),
                        source=f"room:{room.room_id}:fast",
                    )
                )

        humidity_state = humidity_states.get(room.room_id)
        actuator = room.humidity.actuator
        if humidity_state is not None and actuator is not None:
            entity_id = actuator.entity_id
            domain = entity_id.split(".", 1)[0]
            if domain == "switch":
                desired.append(
                    DesiredDeviceState(
                        entity_id=entity_id,
                        domain=domain,
                        power=humidity_state.active,
                        source=f"room:{room.room_id}:humidity",
                    )
                )
            else:
                desired.append(
                    DesiredDeviceState(
                        entity_id=entity_id,
                        domain=domain,
                        power=humidity_state.active,
                        target_humidity=humidity_state.target_humidity,
                        source=f"room:{room.room_id}:humidity",
                    )
                )

    return desired
