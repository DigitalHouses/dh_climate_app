from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .outdoor import OutdoorState
from .problems import Problem
from .rooms import RoomState
from .weather import WeatherState


EVENT_SCHEMA_VERSION = 2
EVENT_TYPES = (
    "season_changed",
    "precipitation_started",
    "precipitation_stopped",
    "precipitation_type_changed",
    "window_opened",
    "window_closed",
    "window_state_unknown",
    "window_state_restored",
    "problem_started",
    "problem_recovered",
)


def _base(event_type: str, observed_at: datetime) -> dict[str, object]:
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_type": event_type,
        "observed_at": observed_at.isoformat(),
    }


def _problem_key(problem: Problem) -> tuple[object, ...]:
    return (
        problem.code,
        problem.scope,
        problem.room_id,
        problem.entity_id,
    )


def _problem_payload(
    event_type: str,
    problem: Problem,
    observed_at: datetime,
) -> dict[str, object]:
    payload = _base(event_type, observed_at)
    payload.update(problem.payload())
    return payload


class ClimateEventEngine:
    """Transition-only machine events.

    The first complete observation establishes a baseline and emits nothing.
    Events are not persisted or replayed after restart; retained entities remain
    the authoritative current-state contract.
    """

    def __init__(self) -> None:
        self._initialized = False
        self._season: str | None = None
        self._weather: WeatherState | None = None
        self._windows: dict[str, str] = {}
        self._problems: dict[tuple[object, ...], Problem] = {}

    def observe(
        self,
        *,
        outdoor: OutdoorState,
        weather: WeatherState | None,
        rooms: dict[str, RoomState],
        problems: Iterable[Problem],
        observed_at: datetime,
    ) -> tuple[dict[str, object], ...]:
        current_problems = {
            _problem_key(problem): problem
            for problem in problems
        }
        current_windows = {
            room_id: state.window_state
            for room_id, state in rooms.items()
            if state.window_state != "not_configured"
        }

        if not self._initialized:
            self._initialized = True
            self._season = outdoor.season.value
            self._weather = weather
            self._windows = current_windows
            self._problems = current_problems
            return ()

        events: list[dict[str, object]] = []

        current_season = outdoor.season.value
        if self._season is not None and current_season != self._season:
            payload = _base("season_changed", observed_at)
            payload.update(
                {
                    "previous_season": self._season,
                    "current_season": current_season,
                    "avg_24h_temperature": outdoor.avg_24h_temperature,
                    "current_temperature": outdoor.current_temperature,
                    "heat_threshold": outdoor.heat_threshold,
                    "cool_threshold": outdoor.cool_threshold,
                    "hysteresis": outdoor.hysteresis,
                }
            )
            events.append(payload)

        previous_weather = self._weather
        if weather is not None and weather.precipitation_type != "unknown":
            if (
                previous_weather is not None
                and previous_weather.precipitation_type != "unknown"
            ):
                previous_active = previous_weather.precipitation_active
                current_active = weather.precipitation_active
                event_type: str | None = None
                if not previous_active and current_active:
                    event_type = "precipitation_started"
                elif previous_active and not current_active:
                    event_type = "precipitation_stopped"
                elif (
                    previous_active
                    and current_active
                    and previous_weather.precipitation_type
                    != weather.precipitation_type
                ):
                    event_type = "precipitation_type_changed"

                if event_type is not None:
                    payload = _base(event_type, observed_at)
                    payload.update(
                        {
                            "previous_type": previous_weather.precipitation_type,
                            "current_type": weather.precipitation_type,
                            "condition": weather.condition,
                            "precipitation_mm": weather.precipitation_mm,
                            "forecast_at": (
                                weather.forecast_at.isoformat()
                                if weather.forecast_at is not None
                                else None
                            ),
                            "source_entity": weather.source_entity,
                        }
                    )
                    events.append(payload)

        for room_id, current in current_windows.items():
            previous = self._windows.get(room_id)
            if previous is None or previous == current:
                continue
            room = rooms[room_id]
            if current == "open":
                event_type = "window_opened"
            elif current == "closed" and previous == "open":
                event_type = "window_closed"
            elif current == "unknown":
                event_type = "window_state_unknown"
            elif previous == "unknown":
                event_type = "window_state_restored"
            else:
                continue
            payload = _base(event_type, observed_at)
            payload.update(
                {
                    "room_id": room_id,
                    "room_name": room.name,
                    "previous_state": previous,
                    "current_state": current,
                    "season": room.season.value,
                }
            )
            events.append(payload)

        previous_keys = set(self._problems)
        current_keys = set(current_problems)
        for key in sorted(current_keys - previous_keys, key=str):
            events.append(
                _problem_payload(
                    "problem_started",
                    current_problems[key],
                    observed_at,
                )
            )
        for key in sorted(previous_keys - current_keys, key=str):
            events.append(
                _problem_payload(
                    "problem_recovered",
                    self._problems[key],
                    observed_at,
                )
            )

        self._season = current_season
        if weather is not None and weather.precipitation_type != "unknown":
            self._weather = weather
        self._windows = current_windows
        self._problems = current_problems
        return tuple(events)
