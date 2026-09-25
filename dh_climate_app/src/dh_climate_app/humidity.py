from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .config import AppConfig, RoomConfig
from .core import average_available
from .persistence import StateStore


@dataclass(frozen=True)
class HumidityState:
    room_id: str
    controller_type: str
    current_humidity: float | None
    target_humidity: float
    control_enabled: bool
    active: bool

    @property
    def available(self) -> bool:
        return self.current_humidity is not None

    @property
    def action(self) -> str:
        if not self.control_enabled:
            return "off"
        if not self.active:
            return "idle"
        return "humidifying" if self.controller_type == "humidifier" else "drying"


def next_humidity_active(
    *,
    controller_type: str,
    current_humidity: float | None,
    target_humidity: float,
    hysteresis: float,
    previous_active: bool,
) -> bool:
    if current_humidity is None:
        return False
    if controller_type == "humidifier":
        if current_humidity <= target_humidity - hysteresis:
            return True
        if current_humidity >= target_humidity + hysteresis:
            return False
        return previous_active
    if controller_type == "dehumidifier":
        if current_humidity >= target_humidity + hysteresis:
            return True
        if current_humidity <= target_humidity - hysteresis:
            return False
        return previous_active
    raise ValueError(f"unsupported humidity controller_type={controller_type}")


class HumidityEngine:
    def __init__(self, *, config: AppConfig, store: StateStore) -> None:
        self.config = config
        self.store = store

    def evaluate_all(
        self,
        states: Mapping[str, object],
    ) -> dict[str, HumidityState]:
        result: dict[str, HumidityState] = {}
        for room in self.config.rooms:
            if not room.humidity.enabled or room.humidity.controller_type is None:
                continue
            state = self._evaluate_room(room, states)
            result[room.room_id] = state
        return result

    def _evaluate_room(
        self,
        room: RoomConfig,
        states: Mapping[str, object],
    ) -> HumidityState:
        current = average_available(
            states.get(entity_id)
            for entity_id in room.humidity_sensors
        )
        target = self.store.get_humidity_target(room.room_id)
        if target is None:
            raise RuntimeError(f"humidity target missing for room={room.room_id}")

        enabled = self.store.get_humidity_control_enabled(room.room_id)
        previous = self.store.get_humidity_previous_active(room.room_id)
        active = False
        if enabled:
            active = next_humidity_active(
                controller_type=str(room.humidity.controller_type),
                current_humidity=current,
                target_humidity=target,
                hysteresis=self.config.global_config.humidity_hysteresis,
                previous_active=previous,
            )
        if active != previous:
            self.store.set_humidity_previous_active(room.room_id, active)

        return HumidityState(
            room_id=room.room_id,
            controller_type=str(room.humidity.controller_type),
            current_humidity=current,
            target_humidity=target,
            control_enabled=enabled,
            active=active,
        )
