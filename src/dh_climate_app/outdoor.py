from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping

from .config import OutdoorConfig
from .core import PrioritizedSource, Season, decide_season, select_prioritized_value, time_weighted_average
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
        self._last_temperature_selection: tuple[str, float] | None = None
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
                PrioritizedSource(source.name, source.temperature)
                for source in self.config.sources
            ],
            states,
        )
        humidity = select_prioritized_value(
            [
                PrioritizedSource(source.name, source.humidity)
                for source in self.config.sources
                if source.humidity
            ],
            states,
        )

        if record_sample:
            self._record_if_changed("temperature", temperature, observed_at)
            self._record_if_changed("humidity", humidity, observed_at)

        self.store.prune_outdoor_samples(now=observed_at)
        since = observed_at - timedelta(hours=24)
        temperature_samples = self.store.load_outdoor_samples(
            kind="temperature",
            since=since,
            include_previous=True,
        )
        humidity_samples = self.store.load_outdoor_samples(
            kind="humidity",
            since=since,
            include_previous=True,
        )

        avg_temperature = time_weighted_average(
            temperature_samples,
            window_end=observed_at,
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
            current_temperature=temperature[1] if temperature else None,
            current_humidity=humidity[1] if humidity else None,
            avg_24h_temperature=avg_temperature,
            avg_24h_humidity=avg_humidity,
            temperature_source=temperature[0] if temperature else None,
            humidity_source=humidity[0] if humidity else None,
            heat_threshold=thresholds.heat,
            cool_threshold=thresholds.cool,
            hysteresis=self.hysteresis,
            season=season,
        )

    def set_thresholds(self, *, heat: float, cool: float) -> None:
        self.store.set_season_thresholds(heat, cool)

    def _record_if_changed(
        self,
        kind: str,
        selection: tuple[str, float] | None,
        observed_at: datetime,
    ) -> None:
        if selection is None:
            return
        previous = (
            self._last_temperature_selection
            if kind == "temperature"
            else self._last_humidity_selection
        )
        if previous == selection:
            return
        source_name, value = selection
        self.store.add_outdoor_sample(
            kind=kind,
            observed_at=observed_at,
            value=value,
            source_name=source_name,
        )
        if kind == "temperature":
            self._last_temperature_selection = selection
        else:
            self._last_humidity_selection = selection
