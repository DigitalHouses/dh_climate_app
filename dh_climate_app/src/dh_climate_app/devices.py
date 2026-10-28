from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Mapping
import time

from .config import AppConfig, DeviceConfig
from .core import DeviceClass, HvacAction, Season, _numeric_state
from .humidity import HumidityState
from .rooms import RoomState
from .persistence import StateStore


@dataclass(frozen=True)
class DesiredDeviceState:
    entity_id: str
    domain: str
    power: bool | None = None
    hvac_mode: str | None = None
    target_temperature: float | None = None
    target_humidity: float | None = None
    source: str = ""
    # Runtime-only metadata for the automatic reversible FAST climate target.
    automatic_temperature: bool = False
    room_temperature: float | None = None

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


class StartupActuatorGate:
    """Bound initial sensor warm-up; preserve the existing live-loss fail-safe."""

    def __init__(self, *, grace_seconds: float = 60.0) -> None:
        if grace_seconds < 0:
            raise ValueError("grace_seconds must not be negative")
        self.grace_seconds = grace_seconds
        self.reset()

    def reset(self) -> None:
        self._started_at: float | None = None
        self._outdoor_seen = False
        self._room_temperature_seen: set[str] = set()
        self._room_humidity_seen: set[str] = set()
        self.deferred_entities: tuple[str, ...] = ()
        self.timed_out = False

    def filter(
        self,
        desired_states: list[DesiredDeviceState],
        *,
        room_states: dict[str, RoomState],
        humidity_states: dict[str, HumidityState],
        outdoor_available: bool,
        now_monotonic: float | None = None,
    ) -> list[DesiredDeviceState]:
        now = time.monotonic() if now_monotonic is None else now_monotonic
        if self._started_at is None:
            self._started_at = now
        if outdoor_available:
            self._outdoor_seen = True
        self._room_temperature_seen.update(
            room_id for room_id, room in room_states.items()
            if room.current_temperature is not None
        )
        self._room_humidity_seen.update(
            room_id for room_id, humidity in humidity_states.items()
            if humidity.current_humidity is not None
        )

        self.timed_out = now - self._started_at >= self.grace_seconds
        if self.timed_out:
            self.deferred_entities = ()
            return desired_states

        permitted: list[DesiredDeviceState] = []
        deferred: list[str] = []
        for desired in desired_states:
            parts = desired.source.split(":")
            if len(parts) != 3 or parts[0] != "room":
                permitted.append(desired)
                continue

            _, room_id, kind = parts
            # SLOW has a local floor thermostat: only the global season matters.
            if kind == "slow":
                ready = self._outdoor_seen
            elif kind == "fast-device":
                ready = self._outdoor_seen
            elif kind == "fast":
                ready = (
                    self._outdoor_seen
                    and room_id in self._room_temperature_seen
                )
            elif kind == "humidity":
                ready = room_id in self._room_humidity_seen
            else:
                ready = True

            if ready:
                permitted.append(desired)
            else:
                deferred.append(desired.entity_id)

        self.deferred_entities = tuple(deferred)
        return permitted


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
    cooling: bool = False,
) -> bool:
    if cooling and room_state.window_cooling_blocked:
        return True

    minimum = device.min_heating_outdoor_temperature
    if (
        heating
        and minimum is not None
        and (outdoor_temperature is None or outdoor_temperature < minimum)
    ):
        return True

    return False


def compile_room_devices(
    *,
    config: AppConfig,
    room_states: dict[str, RoomState],
    humidity_states: dict[str, HumidityState],
    outdoor_temperature: float | None = None,
    screed_values: dict[str, object] | None = None,
    slow_targets: dict[str, float] | None = None,
    slow_hysteresis: float = 0.5,
    slow_previous_open: dict[str, bool] | None = None,
) -> list[DesiredDeviceState]:
    """Compile one desired state per physical device, including NO/NC polarity.

    Missing configured screed sensor in HEAT is an explicit fail-open policy.
    Missing SLOW target is a configuration fault: do not heat blindly.
    Min ON/OFF interval enforcement belongs to the stateful valve controller,
    not to this pure desired-state compiler.
    """
    desired: list[DesiredDeviceState] = []
    screed_values = screed_values or {}
    slow_targets = slow_targets or {}
    slow_previous_open = slow_previous_open or {}
    for room in config.rooms:
        state = room_states[room.room_id]
        for device in room.devices:
            domain = device.entity_id.split(".", 1)[0]
            if device.device_class is DeviceClass.SLOW:
                heating = state.season is Season.HEAT
                if heating and _thermal_inhibited(
                    device, room_state=state,
                    outdoor_temperature=outdoor_temperature, heating=True,
                ):
                    heating = False
                target = slow_targets.get(room.room_id)
                valve_open = heating and (
                    device.temperature_sensor is not None or
                    device.screed_sensor_unavailable == "open"
                )
                if device.device_type == "hardware":
                    # The local floor thermostat owns PWM and its screed sensor.
                    # Without persisted slab target, inhibit rather than guess.
                    active = heating and target is not None
                    desired.append(
                        DesiredDeviceState(
                            entity_id=device.entity_id, domain=domain,
                            hvac_mode="heat" if active else "off",
                            target_temperature=target if active else None,
                            source=f"room:{room.room_id}:slow",
                        )
                    )
                    continue
                if device.temperature_sensor is not None and heating:
                    slab = _numeric_state(
                        screed_values.get(device.temperature_sensor)
                    )
                    if slab is None:
                        valve_open = device.screed_sensor_unavailable == "open"
                    elif target is None:
                        valve_open = False  # missing seed: no invented setpoint
                    elif slab <= target - slow_hysteresis:
                        valve_open = True
                    elif slab >= target + slow_hysteresis:
                        valve_open = False
                    else:
                        valve_open = slow_previous_open.get(device.entity_id, False)
                # switch.on means energized, not necessarily physically OPEN.
                power = (
                    valve_open if device.actuator == "normal_closed"
                    else not valve_open
                )
                desired.append(
                    DesiredDeviceState(
                        entity_id=device.entity_id, domain=domain, power=power,
                        source=f"room:{room.room_id}:slow",
                    )
                )
                continue

            if device.device_type == "hardware":
                # Independent local air thermostat; room hysteresis must never
                # pulse its heat/off or cool/off mode.
                requested = (
                    "heat" if state.season is Season.HEAT
                    and device.function in {"heat", "heat_cool"}
                    else "cool" if state.season is Season.COOL
                    and device.function in {"cool", "heat_cool"}
                    and state.climate_control_enabled
                    else "off"
                )
                if requested != "off" and _thermal_inhibited(
                    device, room_state=state,
                    outdoor_temperature=outdoor_temperature,
                    heating=requested == "heat",
                    cooling=requested == "cool",
                ):
                    requested = "off"
                desired.append(
                    DesiredDeviceState(
                        entity_id=device.entity_id, domain=domain,
                        hvac_mode=requested,
                        target_temperature=(
                            state.control_target_temperature
                            if requested != "off" else None
                        ),
                        source=f"room:{room.room_id}:fast-device",
                    )
                )
                continue

            active = _function_matches(device.function, state.control_action)
            heating = active and state.control_action is HvacAction.HEATING
            if active and _thermal_inhibited(
                device, room_state=state,
                outdoor_temperature=outdoor_temperature, heating=heating,
                cooling=state.control_action is HvacAction.COOLING,
            ):
                active = False
            if domain == "switch":
                # Optional physical valve: logical ON -> energized NO/NC mapping.
                power = (
                    not active if device.actuator == "normal_open" else active
                )
                desired.append(
                    DesiredDeviceState(
                        entity_id=device.entity_id, domain=domain, power=power,
                        source=f"room:{room.room_id}:fast",
                    )
                )
            else:
                mode = (
                    "heat" if active and state.control_action is HvacAction.HEATING
                    else "cool" if active and state.control_action is HvacAction.COOLING
                    else "off"
                )
                desired.append(
                    DesiredDeviceState(
                        entity_id=device.entity_id, domain=domain, hvac_mode=mode,
                        target_temperature=(
                            state.control_target_temperature if active else None
                        ),
                        source=f"room:{room.room_id}:fast",
                        automatic_temperature=(device.function == "heat_cool"),
                        room_temperature=state.current_temperature,
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
                        entity_id=entity_id, domain=domain,
                        power=humidity_state.active,
                        source=f"room:{room.room_id}:humidity",
                    )
                )
            else:
                desired.append(
                    DesiredDeviceState(
                        entity_id=entity_id, domain=domain,
                        power=humidity_state.active,
                        target_humidity=(
                            humidity_state.target_humidity
                            if humidity_state.active else None
                        ),
                        source=f"room:{room.room_id}:humidity",
                    )
                )
    return desired


class SlowValveIntervalGuard:
    """Apply min ON/OFF to observed SLOW valve transitions only.

    Normal heating cycles respect minimum durations. Seasonal shutdown
    and configured screed sensor outage bypass timers.
    The first observed state has UNKNOWN transition time; it is never
    assigned a fabricated startup timestamp.
    """

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def filter(
        self,
        desired: list[DesiredDeviceState],
        *,
        config: AppConfig,
        room_states: dict[str, RoomState],
        observed: Mapping[str, object],
        sensor_values: Mapping[str, object],
        now: datetime | None = None,
    ) -> list[DesiredDeviceState]:
        now = now or datetime.now(timezone.utc)
        devices = {
            device.entity_id: (room.room_id, device)
            for room in config.rooms for device in room.devices
            if device.device_class is DeviceClass.SLOW
            and device.device_type == "virtual"
            and device.temperature_sensor is not None
        }
        output: list[DesiredDeviceState] = []
        for requested in desired:
            pair = devices.get(requested.entity_id)
            if pair is None:
                output.append(requested)
                continue
            room_id, device = pair
            actual = observed.get(device.entity_id)
            state = getattr(actual, "state", None)
            if state not in {"on", "off"}:
                # No trustworthy observed relay: executor handles unknown.
                output.append(requested)
                continue
            powered = state == "on"
            observed_open = (
                powered if device.actuator == "normal_closed"
                else not powered
            )
            last_change = self.store.observe_slow_valve(
                device.entity_id, observed_open, now,
            )
            if requested.power == powered:
                output.append(requested)
                continue
            room = room_states[room_id]
            sensor_lost = _numeric_state(
                sensor_values.get(device.temperature_sensor)
            ) is None
            safety = (
                room.season is not Season.HEAT
                or sensor_lost
            )
            if safety or last_change is None:
                output.append(requested)
                continue
            key = (
                "slow_heat_min_on_time" if observed_open
                else "slow_heat_min_off_time"
            )
            minimum_seconds = 60 * self.store.get_global_tuning(key)
            elapsed = (now - last_change).total_seconds()
            if elapsed < minimum_seconds:
                # Keep the actual physical relay state through a normal cycle.
                output.append(replace(requested, power=powered))
            else:
                output.append(requested)
        return output
