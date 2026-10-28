from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

from .config import AppConfig
from .core import DeviceClass, Season, _numeric_state

from .executor import ExecutionProblem
from .humidity import HumidityState
from .outdoor import OutdoorState
from .rooms import RoomState


@dataclass(frozen=True)
class Problem:
    code: str
    scope: str
    severity: str = "warning"
    room_id: str | None = None
    entity_id: str | None = None
    details: str | None = None

    def payload(self) -> dict[str, object]:
        return {
            key: value
            for key, value in asdict(self).items()
            if value is not None
        }


def collect_problems(
    *,
    outdoor: OutdoorState,
    rooms: dict[str, RoomState],
    humidity: dict[str, HumidityState],
    execution: tuple[ExecutionProblem, ...],
    config: AppConfig | None = None,
    sensor_values: Mapping[str, object] | None = None,
    slow_targets: Mapping[str, float | None] | None = None,
) -> tuple[Problem, ...]:
    problems: list[Problem] = []

    if outdoor.stale and outdoor.last_valid_at is not None:
        problems.append(
            Problem(
                code="outdoor_temperature_stale",
                scope="outdoor", severity="warning",
                details=f"last_valid_at={outdoor.last_valid_at}",
            )
        )
    if outdoor.current_temperature is None:
        problems.append(
            Problem(
                code="outdoor_temperature_unavailable",
                scope="outdoor",
                severity="critical",
            )
        )

    for room_id, state in rooms.items():
        if state.current_temperature is None:
            problems.append(
                Problem(
                    code="room_temperature_unavailable",
                    scope="room",
                    severity="critical",
                    room_id=room_id,
                )
            )
        if state.window_state == "unknown":
            problems.append(
                Problem(
                    code="room_window_state_unknown",
                    scope="room",
                    severity="warning",
                    room_id=room_id,
                )
            )

    if config is not None:
        sensor_values = sensor_values or {}
        slow_targets = slow_targets or {}
        for room in config.rooms:
            state = rooms.get(room.room_id)
            if state is None or state.season is not Season.HEAT:
                continue
            for device in room.devices:
                if device.device_class is not DeviceClass.SLOW:
                    continue
                needs_target = (
                    device.device_type == "hardware"
                    or device.temperature_sensor is not None
                )
                if needs_target and slow_targets.get(room.room_id) is None:
                    problems.append(
                        Problem(
                            code="slow_target_missing",
                            scope="room", severity="critical",
                            room_id=room.room_id, entity_id=device.entity_id,
                            details="No persisted screed target for active profile",
                        )
                    )
                if (
                    device.temperature_sensor is not None
                    and _numeric_state(
                        sensor_values.get(device.temperature_sensor)
                    ) is None
                ):
                    problems.append(
                        Problem(
                            code="slow_screed_sensor_unavailable",
                            scope="room", severity="warning",
                            room_id=room.room_id,
                            entity_id=device.temperature_sensor,
                            details=f"valve fallback {device.screed_sensor_unavailable.upper()} in HEAT",
                        )
                    )

    for room_id, state in humidity.items():
        if state.current_humidity is None:
            problems.append(
                Problem(
                    code="room_humidity_unavailable",
                    scope="humidity",
                    room_id=room_id,
                )
            )

    for item in execution:
        problems.append(
            Problem(
                code=f"device_{item.reason}",
                scope="device",
                severity="critical" if item.reason == "service_error" else "warning",
                room_id=item.room_id,
                entity_id=item.entity_id,
                details=item.details,
            )
        )

    return tuple(problems)
