from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Mapping

from .config import AppConfig, RoomConfig
from .core import (
    HvacAction,
    Profile,
    Season,
    average_available,
    effective_profile,
    next_hvac_action,
)
from .persistence import StateStore


@dataclass(frozen=True)
class RoomState:
    room_id: str
    name: str
    current_temperature: float | None
    current_humidity: float | None
    season: Season
    effective_profile: Profile
    target_temperature: float | None
    climate_control_enabled: bool
    control_action: HvacAction
    hvac_mode: str
    hvac_action: HvacAction
    window_state: str = "not_configured"

    @property
    def available(self) -> bool:
        if self.current_temperature is None:
            return False
        if self.season is Season.OFF:
            return True
        return self.target_temperature is not None


def _binary_fact(
    entity_id: str,
    states: Mapping[str, object],
    *,
    default: bool,
) -> bool:
    if not entity_id:
        return default
    value = str(states.get(entity_id, "unavailable")).strip().lower()
    if value in {"on", "true", "1", "yes", "home"}:
        return True
    if value in {"off", "false", "0", "no", "not_home"}:
        return False
    return default


def aggregate_window_state(
    entity_ids: tuple[str, ...],
    states: Mapping[str, object],
) -> str:
    """Legacy room window aggregation without a separate SQL contour.

    Any open contact wins. If none are open but at least one configured
    contact is unavailable/unknown, room window truth is unknown. Otherwise
    all contacts are closed.
    """
    if not entity_ids:
        return "not_configured"

    saw_unknown = False
    for entity_id in entity_ids:
        value = str(states.get(entity_id, "unavailable")).strip().lower()
        if value in {"on", "open", "opened", "true", "1"}:
            return "open"
        if value in {"off", "closed", "close", "false", "0"}:
            continue
        saw_unknown = True
    return "unknown" if saw_unknown else "closed"


class RoomEngine:
    def __init__(
        self,
        *,
        config: AppConfig,
        store: StateStore,
    ) -> None:
        self.config = config
        self.store = store
        self._rooms = {room.room_id: room for room in config.rooms}

    def room_config(self, room_id: str) -> RoomConfig:
        try:
            return self._rooms[room_id]
        except KeyError as exc:
            raise KeyError(f"unknown room_id={room_id}") from exc

    def evaluate_all(
        self,
        states: Mapping[str, object],
        *,
        season: Season,
    ) -> dict[str, RoomState]:
        we_at_home = (
            True
            if not self.config.global_config.we_at_home
            else _binary_fact(
                self.config.global_config.we_at_home,
                states,
                default=False,
            )
        )
        night_mode = _binary_fact(
            self.config.global_config.night_mode,
            states,
            default=False,
        )
        return {
            room.room_id: self._evaluate_room(
                room,
                states,
                season=season,
                we_at_home=we_at_home,
                night_mode=night_mode,
            )
            for room in self.config.rooms
        }

    def _evaluate_room(
        self,
        room: RoomConfig,
        states: Mapping[str, object],
        *,
        season: Season,
        we_at_home: bool,
        night_mode: bool,
    ) -> RoomState:
        current_temperature = average_available(
            states.get(entity_id)
            for entity_id in room.temperature_sensors
        )
        current_humidity = average_available(
            states.get(entity_id)
            for entity_id in room.humidity_sensors
        )
        window_state = aggregate_window_state(
            room.window_sensors,
            states,
        )

        climate_enabled = self.store.get_climate_control_enabled(room.room_id)
        profile = effective_profile(
            season=season,
            climate_control_enabled=climate_enabled,
            we_at_home=we_at_home,
            night_mode=night_mode,
        )
        target = self.store.get_room_target(room.room_id, season, profile)

        previous = self.store.get_previous_action(room.room_id)
        if season is Season.HEAT:
            # HEAT + room OFF keeps antifreeze protection internally.
            control_action = next_hvac_action(
                season=season,
                current_temperature=current_temperature,
                target_temperature=target,
                hysteresis=self.config.global_config.hysteresis,
                previous_action=previous,
            )
        elif not climate_enabled:
            control_action = HvacAction.OFF
        else:
            control_action = next_hvac_action(
                season=season,
                current_temperature=current_temperature,
                target_temperature=target,
                hysteresis=self.config.global_config.hysteresis,
                previous_action=previous,
            )

        if control_action is not previous:
            self.store.set_previous_action(room.room_id, control_action)

        if not climate_enabled:
            hvac_mode = "off"
            hvac_action = HvacAction.OFF
        elif season is Season.HEAT:
            hvac_mode = "heat"
            hvac_action = control_action
        elif season is Season.COOL:
            hvac_mode = "cool"
            hvac_action = control_action
        else:
            hvac_mode = "off"
            hvac_action = HvacAction.OFF

        return RoomState(
            room_id=room.room_id,
            name=room.name,
            current_temperature=current_temperature,
            current_humidity=current_humidity,
            season=season,
            effective_profile=profile,
            target_temperature=target,
            climate_control_enabled=climate_enabled,
            control_action=control_action,
            hvac_mode=hvac_mode,
            hvac_action=hvac_action,
            window_state=window_state,
        )


class ProfileEditOverlay:
    """Short-lived facade-only profile selection, matching Climate 5 behavior."""

    def __init__(self, idle_timeout_seconds: float = 10.0) -> None:
        self.idle_timeout_seconds = float(idle_timeout_seconds)
        self._selected: dict[str, tuple[Profile, float]] = {}

    def select(
        self,
        room_id: str,
        profile: Profile,
        *,
        effective_profile: Profile,
        now_monotonic: float | None = None,
    ) -> None:
        now = time.monotonic() if now_monotonic is None else now_monotonic
        if profile is effective_profile:
            self._selected.pop(room_id, None)
            return
        self._selected[room_id] = (
            profile,
            now + self.idle_timeout_seconds,
        )

    def touch(
        self,
        room_id: str,
        *,
        now_monotonic: float | None = None,
    ) -> None:
        current = self._selected.get(room_id)
        if current is None:
            return
        now = time.monotonic() if now_monotonic is None else now_monotonic
        self._selected[room_id] = (
            current[0],
            now + self.idle_timeout_seconds,
        )

    def selected(
        self,
        room_id: str,
        *,
        effective_profile: Profile,
        now_monotonic: float | None = None,
    ) -> Profile:
        current = self._selected.get(room_id)
        if current is None:
            return effective_profile
        now = time.monotonic() if now_monotonic is None else now_monotonic
        profile, expires_at = current
        if now >= expires_at:
            self._selected.pop(room_id, None)
            return effective_profile
        return profile

    def clear(self, room_id: str) -> None:
        self._selected.pop(room_id, None)
