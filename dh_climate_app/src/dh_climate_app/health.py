"""Climate health is a reduction of authoritative Problems, not another FSM."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .outdoor import OutdoorState
from .problems import Problem
from .rooms import RoomState


@dataclass(frozen=True)
class ClimateHealth:
    rooms: dict[str, str]
    global_state: str
    climate_state: str


def _severity(problems: list[Problem]) -> str:
    if any(problem.severity == "critical" for problem in problems):
        return "critical"
    if problems:
        return "degraded"
    return "healthy"


def reduce_climate_health(
    *,
    outdoor: OutdoorState,
    rooms: Mapping[str, RoomState],
    problems: tuple[Problem, ...],
) -> ClimateHealth:
    """One deterministic hierarchy: facts → problems → room → climate.

    Unknown is reserved for never-acquired climate truth; cached outdoor data
    are explicitly DEGRADED, never represented as fresh HEALTHY.
    """
    room_status = {
        room_id: _severity([
            p for p in problems if p.room_id == room_id
        ])
        for room_id in rooms
    }
    global_problems = [
        p for p in problems if p.room_id is None
    ]
    if outdoor.current_temperature is None and outdoor.last_valid_at is None:
        global_state = "unknown"
    else:
        global_state = _severity(global_problems)
        if outdoor.stale and global_state == "healthy":
            global_state = "degraded"

    statuses = [global_state, *room_status.values()]
    if "critical" in statuses:
        climate_state = "critical"
    elif "degraded" in statuses:
        climate_state = "degraded"
    elif "unknown" in statuses:
        climate_state = "unknown"
    else:
        climate_state = "healthy"
    return ClimateHealth(
        rooms=room_status,
        global_state=global_state,
        climate_state=climate_state,
    )
