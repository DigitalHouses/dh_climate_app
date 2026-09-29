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
    """Outdoor source selection, rolling averages and global season."""

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
        self._temperature_ema_tau_seconds = (
            float(config.temperature_ema_minutes) * 60.0
        )
        self._filtered_temperature: float | None = None
        self._filtered_temperature_updated_at: datetime | None = None
        self._last_public_temperature: float | None = None
        self._last_humidity_selection: tuple[str, float] | None = None

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

        raw_temperature = temperature[1] if temperature else None
        filtered_temperature = self._ema_temperature(
            raw_temperature,
            observed_at=observed_at,
        )

        if filtered_temperature is not None and temperature is not None:
            self._record_temperature_if_changed(
                filtered_temperature,
                source_name=temperature[0],
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
            if temperature is not None and filtered_temperature is not None
            else Season.OFF
        )

        return OutdoorState(
            observed_at=observed_at,
            current_temperature=filtered_temperature,
            current_humidity=humidity[1] if humidity else None,
            avg_24h_temperature=avg_temperature,
            avg_24h_humidity=avg_humidity,
            temperature_source=temperature[0] if temperature else None,
            humidity_source=humidity[0] if humidity else None,
            heat_threshold=thresholds.heat,
            cool_threshold=thresholds.cool,
            hysteresis=self.hysteresis,
            season=season,
            raw_temperature=raw_temperature,
        )

    def bootstrap_temperature_history(
        self,
        samples: Sequence[Sample],
        *,
        source_name: str,
    ) -> None:
        """Replace the temperature mean window with Recorder-backed samples.

        The newest restored public value also becomes the transition baseline,
        so the startup snapshot is not counted twice when it matches the last
        Recorder sample. If the live value differs, evaluate() records it as
        the same new transition Home Assistant will publish.
        """
        restored = sorted(samples, key=lambda sample: sample.observed_at)
        self.store.replace_outdoor_samples(
            kind="temperature",
            samples=restored,
            source_name=source_name,
        )
        if restored:
            latest = float(restored[-1].value)
            self._filtered_temperature = latest
            self._filtered_temperature_updated_at = None
            self._last_public_temperature = round(latest, 1)
        else:
            self._filtered_temperature = None
            self._filtered_temperature_updated_at = None
            self._last_public_temperature = None

    def set_thresholds(self, *, heat: float, cool: float) -> None:
        self.store.set_season_thresholds(heat, cool)

    def _ema_temperature(
        self,
        raw_temperature: float | None,
        *,
        observed_at: datetime,
    ) -> float | None:
        """Apply one time-based EMA to every selected outdoor temperature.

        The same filter handles ordinary source updates and source failover.
        A restored Recorder value anchors the first calculation after restart,
        preventing a startup jump. When all sources are unavailable the public
        filtered value is unavailable, while the internal EMA baseline is kept.
        """
        if raw_temperature is None:
            if (
                self._filtered_temperature_updated_at is not None
                and observed_at > self._filtered_temperature_updated_at
            ):
                self._filtered_temperature_updated_at = observed_at
            return None

        raw = float(raw_temperature)
        if self._filtered_temperature is None:
            self._filtered_temperature = raw
            self._filtered_temperature_updated_at = observed_at
            return raw

        if self._filtered_temperature_updated_at is None:
            self._filtered_temperature_updated_at = observed_at
            return self._filtered_temperature

        elapsed = (
            observed_at - self._filtered_temperature_updated_at
        ).total_seconds()
        if elapsed <= 0.0:
            return self._filtered_temperature

        alpha = 1.0 - exp(
            -elapsed / self._temperature_ema_tau_seconds
        )
        self._filtered_temperature += alpha * (
            raw - self._filtered_temperature
        )
        self._filtered_temperature_updated_at = observed_at
        return self._filtered_temperature

    def _record_temperature_if_changed(
        self,
        filtered_temperature: float,
        *,
        source_name: str,
        observed_at: datetime,
    ) -> None:
        public_value = round(float(filtered_temperature), 1)
        if self._last_public_temperature == public_value:
            return
        self._last_public_temperature = public_value
        self.store.add_outdoor_sample(
            kind="temperature",
            observed_at=observed_at,
            value=public_value,
            source_name=source_name,
        )

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
