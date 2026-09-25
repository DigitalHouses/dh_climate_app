from __future__ import annotations

from dataclasses import asdict, dataclass

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
) -> tuple[Problem, ...]:
    problems: list[Problem] = []

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
                entity_id=item.entity_id,
                details=item.details,
            )
        )

    return tuple(problems)
