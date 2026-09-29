from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import exp
from typing import Mapping, Sequence

from .config import OutdoorConfig
from .core import (
    PrioritizedSource,
    Sample,
    Season,
    average_available,
    decide_season,
    select_prioritized_value,
    time_weighted_average,
)
from .persistence import StateStore


TEMPERATURE_SAMPLE_INTERVAL = timedelta(minutes=1)
TEMPERATURE_HISTORY_MODE_KEY = "outdoor_temperature_history_mode"
TEMPERATURE_HISTORY_MODE_EMA_MINUTE_V1 = "ema_minute_v1"


@dataclass(frozen=True)
class OutdoorState:
    observed_at: datetime
    current_temperature: float | None
    current_humidity: float | None
    avg_24h_temperature: float | None
    avg_24h_humidity: float | None
    temperature_source: str | None
    humidity_source: str | None
    heat_threshold: float
    cool_threshold: float
    hysteresis: float
    season: Season
    raw_temperature: float | None = None

    @property
    def available(self) -> bool:
        return (
            self.current_temperature is not None
            and self.avg_24h_temperature is not None
        )


class OutdoorEngine:
    """Outdoor source selection, EMA filtering, rolling averages and season."""

    def __init__(
        self,
        *,
        config: OutdoorConfig,
        store: StateStore,
        hysteresis: float,
    ) -> None:
        self.config = config
        self.store = store
        self.hysteresis = float(hysteresis)
        self._last_humidity_selection: tuple[str, float] | None = None
        self._temperature_history_ready = False
        self._filtered_temperature: float | None = None
        self._last_temperature_filter_at: datetime | None = None

    def evaluate(
        self,
        states: Mapping[str, object],
        *,
        observed_at: datetime,
        record_sample: bool = True,
    ) -> OutdoorState:
        temperature = select_prioritized_value(
            [
                PrioritizedSource(
                    entity_id,
                    entity_id,
                    "temperature" if entity_id.startswith("weather.") else None,
                )
                for entity_id in self.config.temperature_sources
            ],
            states,
        )
        humidity = select_prioritized_value(
            [
                PrioritizedSource(
                    entity_id,
                    entity_id,
                    "humidity" if entity_id.startswith("weather.") else None,
                )
                for entity_id in self.config.humidity_sources
            ],
            states,
        )

        self._ensure_temperature_history(observed_at)
        filtered_temperature = self._advance_temperature_filter(
            temperature,
            observed_at=observed_at,
        )

        if record_sample:
            self._record_humidity_if_changed(humidity, observed_at)

        self.store.prune_outdoor_samples(now=observed_at)
        since = observed_at - timedelta(hours=24)
        temperature_samples = self.store.load_outdoor_samples(
            kind="temperature",
            since=since,
            include_previous=False,
        )
        if (
            temperature is not None
            and filtered_temperature is not None
            and not temperature_samples
        ):
            self.store.add_outdoor_sample(
                kind="temperature",
                observed_at=observed_at,
                value=filtered_temperature,
                source_name=temperature[0],
            )
            temperature_samples = self.store.load_outdoor_samples(
                kind="temperature",
                since=since,
                include_previous=False,
            )

        humidity_samples = self.store.load_outdoor_samples(
            kind="humidity",
            since=since,
            include_previous=True,
        )

        avg_temperature = average_available(
            sample.value for sample in temperature_samples
        )
        avg_humidity = time_weighted_average(
            humidity_samples,
            window_end=observed_at,
        )

        thresholds = self.store.get_season_thresholds()
        season = (
            decide_season(
                avg_temperature,
                heat_threshold=thresholds.heat,
                cool_threshold=thresholds.cool,
                hysteresis=self.hysteresis,
            )
            if temperature is not None
            else Season.OFF
        )

        return OutdoorState(
            observed_at=observed_at,
            current_temperature=(
                filtered_temperature if temperature is not None else None
            ),
            current_humidity=humidity[1] if humidity else None,
            avg_24h_temperature=avg_temperature,
            avg_24h_humidity=avg_humidity,
            temperature_source=temperature[0] if temperature else None,
            humidity_source=humidity[0] if humidity else None,
            heat_threshold=thresholds.heat,
            cool_threshold=thresholds.cool,
            hysteresis=self.hysteresis,
            season=season,
            raw_temperature=temperature[1] if temperature else None,
        )

    def set_thresholds(self, *, heat: float, cool: float) -> None:
        self.store.set_season_thresholds(heat, cool)

    def _ensure_temperature_history(self, observed_at: datetime) -> None:
        if self._temperature_history_ready:
            return

        mode = self.store.get_metadata(TEMPERATURE_HISTORY_MODE_KEY)
        if mode == TEMPERATURE_HISTORY_MODE_EMA_MINUTE_V1:
            existing = self.store.load_outdoor_samples(
                kind="temperature",
                since=observed_at - timedelta(hours=25),
                include_previous=True,
            )
            if existing:
                self._filtered_temperature = float(existing[-1].value)
            self._last_temperature_filter_at = (
                observed_at if self._filtered_temperature is not None else None
            )
            self._temperature_history_ready = True
            return

        legacy = self.store.load_outdoor_samples(
            kind="temperature",
            since=observed_at - timedelta(hours=24),
            include_previous=True,
        )
        migrated = self._replay_legacy_temperature_history(
            legacy,
            observed_at=observed_at,
        )
        self.store.replace_outdoor_samples(
            kind="temperature",
            samples=migrated,
            source_name="ema_migration",
        )
        self.store.set_metadata(
            TEMPERATURE_HISTORY_MODE_KEY,
            TEMPERATURE_HISTORY_MODE_EMA_MINUTE_V1,
        )
        if migrated:
            self._filtered_temperature = float(migrated[-1].value)
            self._last_temperature_filter_at = observed_at
        self._temperature_history_ready = True

    def _replay_legacy_temperature_history(
        self,
        samples: Sequence[Sample],
        *,
        observed_at: datetime,
    ) -> list[Sample]:
        ordered = sorted(
            (sample for sample in samples if sample.observed_at <= observed_at),
            key=lambda sample: sample.observed_at,
        )
        if not ordered:
            return []

        window_start = observed_at - timedelta(hours=24)
        baseline: Sample | None = None
        transitions: list[Sample] = []
        for sample in ordered:
            if sample.observed_at <= window_start:
                baseline = sample
            else:
                transitions.append(sample)

        if baseline is not None:
            cursor = window_start
            target = float(baseline.value)
        elif transitions:
            first = transitions.pop(0)
            cursor = first.observed_at
            target = float(first.value)
        else:
            return []

        filtered = target
        result = [Sample(cursor, filtered)]
        transition_index = 0
        tick = cursor + TEMPERATURE_SAMPLE_INTERVAL
        alpha = self._ema_alpha(TEMPERATURE_SAMPLE_INTERVAL.total_seconds())

        while tick <= observed_at:
            while (
                transition_index < len(transitions)
                and transitions[transition_index].observed_at <= tick
            ):
                target = float(transitions[transition_index].value)
                transition_index += 1
            filtered += alpha * (target - filtered)
            result.append(Sample(tick, filtered))
            tick += TEMPERATURE_SAMPLE_INTERVAL

        return result

    def _advance_temperature_filter(
        self,
        selection: tuple[str, float] | None,
        *,
        observed_at: datetime,
    ) -> float | None:
        if selection is None:
            self._last_temperature_filter_at = None
            return None

        source_name, raw_value = selection
        raw_value = float(raw_value)

        if self._filtered_temperature is None:
            self._filtered_temperature = raw_value
            self._last_temperature_filter_at = observed_at
            self.store.add_outdoor_sample(
                kind="temperature",
                observed_at=observed_at,
                value=self._filtered_temperature,
                source_name=source_name,
            )
            return self._filtered_temperature

        if self._last_temperature_filter_at is None:
            self._last_temperature_filter_at = observed_at
            return self._filtered_temperature

        next_tick = self._last_temperature_filter_at + TEMPERATURE_SAMPLE_INTERVAL
        alpha = self._ema_alpha(TEMPERATURE_SAMPLE_INTERVAL.total_seconds())
        while next_tick <= observed_at:
            self._filtered_temperature += alpha * (
                raw_value - self._filtered_temperature
            )
            self.store.add_outdoor_sample(
                kind="temperature",
                observed_at=next_tick,
                value=self._filtered_temperature,
                source_name=source_name,
            )
            self._last_temperature_filter_at = next_tick
            next_tick += TEMPERATURE_SAMPLE_INTERVAL

        return self._filtered_temperature

    def _ema_alpha(self, elapsed_seconds: float) -> float:
        tau_seconds = self.config.temperature_ema_minutes * 60.0
        return 1.0 - exp(-float(elapsed_seconds) / tau_seconds)

    def _record_humidity_if_changed(
        self,
        selection: tuple[str, float] | None,
        observed_at: datetime,
    ) -> None:
        if selection is None:
            return
        if self._last_humidity_selection == selection:
            return
        self._last_humidity_selection = selection
        source_name, value = selection
        self.store.add_outdoor_sample(
            kind="humidity",
            observed_at=observed_at,
            value=value,
            source_name=source_name,
        )
