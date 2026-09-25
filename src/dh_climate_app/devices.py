from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig
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


def compile_room_devices(
    *,
    config: AppConfig,
    room_states: dict[str, RoomState],
    humidity_states: dict[str, HumidityState],
) -> list[DesiredDeviceState]:
    desired: list[DesiredDeviceState] = []

    for room in config.rooms:
        state = room_states[room.room_id]
        for device in room.devices:
            domain = device.entity_id.split(".", 1)[0]

            if device.device_class is DeviceClass.SLOW:
                active = state.season is Season.HEAT
                if domain == "switch":
                    desired.append(
                        DesiredDeviceState(
                            entity_id=device.entity_id,
                            domain=domain,
                            power=active,
                            source=f"room:{room.room_id}:slow",
                        )
                    )
                else:
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

            active = _function_matches(device.function, state.control_action)
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
