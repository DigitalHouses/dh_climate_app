from __future__ import annotations

from dataclasses import dataclass
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
    control_profile: Profile = Profile.DAY
    control_target_temperature: float | None = None
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
        # User-facing profile follows schedule/presence even while the room
        # thermostat is OFF. Antifreeze is an internal HEAT control profile.
        profile = effective_profile(
            season=season,
            climate_control_enabled=True,
            we_at_home=we_at_home,
            night_mode=night_mode,
        )
        control_profile = (
            Profile.ANTIFREEZE
            if season is Season.HEAT and not climate_enabled
            else profile
        )
        target = self.store.get_room_target(room.room_id, season, profile)
        control_target = self.store.get_room_target(
            room.room_id,
            season,
            control_profile,
        )

        previous = self.store.get_previous_action(room.room_id)
        if season is Season.HEAT:
            # HEAT + room OFF keeps antifreeze protection internally.
            control_action = next_hvac_action(
                season=season,
                current_temperature=current_temperature,
                target_temperature=control_target,
                hysteresis=self.config.global_config.hysteresis,
                previous_action=previous,
            )
        elif not climate_enabled:
            control_action = HvacAction.OFF
        else:
            control_action = next_hvac_action(
                season=season,
                current_temperature=current_temperature,
                target_temperature=control_target,
                hysteresis=self.config.global_config.hysteresis,
                previous_action=previous,
            )

        if control_action is not previous:
            self.store.set_previous_action(room.room_id, control_action)

        if not climate_enabled:
            hvac_mode = "off"
            hvac_action = HvacAction.OFF
        else:
            hvac_mode = "auto"
            if season in {Season.HEAT, Season.COOL}:
                hvac_action = control_action
            else:
                hvac_action = HvacAction.IDLE

        return RoomState(
            room_id=room.room_id,
            name=room.name,
            current_temperature=current_temperature,
            current_humidity=current_humidity,
            season=season,
            effective_profile=profile,
            target_temperature=target,
            control_profile=control_profile,
            control_target_temperature=control_target,
            climate_control_enabled=climate_enabled,
            control_action=control_action,
            hvac_mode=hvac_mode,
            hvac_action=hvac_action,
            window_state=window_state,
        )

