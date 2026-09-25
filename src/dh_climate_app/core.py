from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from math import fsum
from typing import Iterable, Mapping, Sequence


class Season(StrEnum):
    HEAT = "heat"
    COOL = "cool"
    OFF = "off"


class Profile(StrEnum):
    DAY = "day"
    NIGHT = "night"
    AWAY = "away"
    ANTIFREEZE = "antifreeze"


class HvacAction(StrEnum):
    HEATING = "heating"
    COOLING = "cooling"
    IDLE = "idle"
    OFF = "off"


class DeviceClass(StrEnum):
    FAST = "fast"
    SLOW = "slow"


@dataclass(frozen=True)
class PrioritizedSource:
    name: str
    entity_id: str


@dataclass(frozen=True)
class Sample:
    observed_at: datetime
    value: float


def _numeric_state(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    if not text or text in {"unknown", "unavailable", "none", "null", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def select_prioritized_value(
    sources: Sequence[PrioritizedSource],
    states: Mapping[str, object],
) -> tuple[str, float] | None:
    """Return the first valid configured source in declared priority order."""
    for source in sources:
        value = _numeric_state(states.get(source.entity_id))
        if value is not None:
            return source.name, value
    return None


def average_available(values: Iterable[object]) -> float | None:
    """Average valid numeric values, ignoring unavailable/unknown entries."""
    parsed = [value for raw in values if (value := _numeric_state(raw)) is not None]
    if not parsed:
        return None
    return fsum(parsed) / len(parsed)


def time_weighted_average(
    samples: Sequence[Sample],
    *,
    window_end: datetime,
    window: timedelta = timedelta(hours=24),
) -> float | None:
    """Calculate a time-weighted average over a rolling window.

    The newest sample at or before each interval start owns that interval.
    If there is no sample at/before the window start, integration begins at
    the first sample inside the window instead of fabricating data.
    """
    if window.total_seconds() <= 0:
        raise ValueError("window must be positive")

    window_start = window_end - window
    ordered = sorted(
        (s for s in samples if s.observed_at <= window_end),
        key=lambda s: s.observed_at,
    )
    if not ordered:
        return None

    active_value: float | None = None
    active_at = window_start

    for sample in ordered:
        if sample.observed_at <= window_start:
            active_value = float(sample.value)
            continue
        if active_value is None:
            active_value = float(sample.value)
            active_at = sample.observed_at
            continue
        break

    if active_value is None:
        return None

    weighted_sum = 0.0
    covered_seconds = 0.0
    cursor = active_at
    current_value = active_value

    for sample in ordered:
        if sample.observed_at <= cursor:
            current_value = float(sample.value)
            continue
        if sample.observed_at > window_end:
            break
        seconds = (sample.observed_at - cursor).total_seconds()
        if seconds > 0:
            weighted_sum += current_value * seconds
            covered_seconds += seconds
        cursor = sample.observed_at
        current_value = float(sample.value)

    tail_seconds = (window_end - cursor).total_seconds()
    if tail_seconds > 0:
        weighted_sum += current_value * tail_seconds
        covered_seconds += tail_seconds

    if covered_seconds <= 0:
        return current_value
    return weighted_sum / covered_seconds


def decide_season(
    avg_outdoor_24: float | None,
    *,
    heat_threshold: float,
    cool_threshold: float,
    hysteresis: float,
) -> Season:
    """Legacy Climate 5 season semantics with one house-wide hysteresis value."""
    if heat_threshold >= cool_threshold:
        raise ValueError("heat_threshold must be lower than cool_threshold")
    if hysteresis < 0:
        raise ValueError("hysteresis must be non-negative")
    if avg_outdoor_24 is None:
        return Season.OFF
    if avg_outdoor_24 < heat_threshold - hysteresis:
        return Season.HEAT
    if avg_outdoor_24 > cool_threshold + hysteresis:
        return Season.COOL
    return Season.OFF


def effective_profile(
    *,
    season: Season,
    climate_control_enabled: bool,
    we_at_home: bool,
    night_mode: bool,
) -> Profile:
    """Legacy profile precedence."""
    if season is Season.HEAT and not climate_control_enabled:
        return Profile.ANTIFREEZE
    if not we_at_home:
        return Profile.AWAY
    if night_mode:
        return Profile.NIGHT
    return Profile.DAY


def next_hvac_action(
    *,
    season: Season,
    current_temperature: float | None,
    target_temperature: float | None,
    hysteresis: float,
    previous_action: HvacAction | None,
) -> HvacAction:
    """Stateful symmetric thermostat used by the new compact App.

    Inside the hysteresis band the previous active/idle state is retained.
    Missing input or interseason is a hard inhibit.
    """
    if hysteresis < 0:
        raise ValueError("hysteresis must be non-negative")
    if current_temperature is None or target_temperature is None:
        return HvacAction.OFF
    if season is Season.OFF:
        return HvacAction.OFF

    if season is Season.HEAT:
        if current_temperature <= target_temperature - hysteresis:
            return HvacAction.HEATING
        if current_temperature >= target_temperature + hysteresis:
            return HvacAction.IDLE
        if previous_action in {HvacAction.HEATING, HvacAction.IDLE}:
            return previous_action
        return HvacAction.IDLE

    if current_temperature >= target_temperature + hysteresis:
        return HvacAction.COOLING
    if current_temperature <= target_temperature - hysteresis:
        return HvacAction.IDLE
    if previous_action in {HvacAction.COOLING, HvacAction.IDLE}:
        return previous_action
    return HvacAction.IDLE


def fast_device_should_run(
    *,
    function: Season,
    room_action: HvacAction,
) -> bool:
    """FAST devices follow room demand."""
    if function is Season.HEAT:
        return room_action is HvacAction.HEATING
    if function is Season.COOL:
        return room_action is HvacAction.COOLING
    return False


def slow_device_should_run(*, season: Season) -> bool:
    """SLOW comfort devices are enabled for the whole heating season."""
    return season is Season.HEAT
