"""Автоматическая уставка реверсивного FAST climate без пользовательских offset.

SmartIR сообщает предполагаемое состояние, а не температуру собственного
внутреннего датчика. Поэтому алгоритм регулирует по комнатному датчику,
не пытаясь выдавать вычисленное смещение за аппаратную калибровку.

Внутри одного цикла HEAT/COOL заданная физическая температура стабильна:
изменения комнатной температуры не генерируют новые ИК-пакеты. Если комната
не продвигается к цели, повышение/понижение задания ограничено по частоте.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import time
from typing import Mapping

from .devices import DesiredDeviceState
from .ha_client import HaState


INITIAL_BIAS_C = 3.0
MAX_EXTRA_BIAS_C = 2.0
STALL_WINDOW_SECONDS = 20.0 * 60.0
MIN_PROGRESS_C = 0.2


@dataclass
class _Cycle:
    mode: str
    room_target: float
    device_target: float
    reference_temperature: float
    observed_at: float


def _capability_number(state: HaState, key: str) -> float | None:
    try:
        value = float(state.attributes[key])
    except (KeyError, ValueError, TypeError):
        return None
    return value if math.isfinite(value) else None


def _normalize(value: float, *, minimum: float, maximum: float, step: float) -> float:
    """Snap to a device step aligned with min_temp, then clamp to its limits."""
    value = max(minimum, min(maximum, value))
    steps = math.floor((value - minimum) / step + 0.5)
    snapped = minimum + steps * step
    if snapped > maximum:
        snapped = minimum + math.floor((maximum - minimum) / step) * step
    return round(snapped, 3)


class AutoFastClimateTargets:
    """Maintain a stable actuator target for each active room FAST cycle."""

    def __init__(self) -> None:
        self._cycles: dict[str, _Cycle] = {}

    def reset(self) -> None:
        self._cycles.clear()

    def apply(
        self,
        desired_states: list[DesiredDeviceState],
        actual_states: Mapping[str, HaState],
        *,
        now_monotonic: float | None = None,
    ) -> list[DesiredDeviceState]:
        now = time.monotonic() if now_monotonic is None else now_monotonic
        adjusted: list[DesiredDeviceState] = []

        for desired in desired_states:
            entity = desired.entity_id
            if not desired.automatic_temperature:
                adjusted.append(desired)
                continue

            mode = desired.hvac_mode
            target = desired.target_temperature
            room_temperature = desired.room_temperature
            if (
                mode not in {"heat", "cool"}
                or target is None
                or room_temperature is None
                or not math.isfinite(target)
                or not math.isfinite(room_temperature)
            ):
                self._cycles.pop(entity, None)
                adjusted.append(desired)
                continue

            actual = actual_states.get(entity)
            if actual is None:
                adjusted.append(desired)
                continue
            minimum = _capability_number(actual, "min_temp")
            maximum = _capability_number(actual, "max_temp")
            step = _capability_number(actual, "target_temp_step")
            if (
                minimum is None
                or maximum is None
                or step is None
                or step <= 0
                or maximum < minimum
            ):
                # Невозможно доказать корректный target и шаг устройства:
                # не подменяем неизвестные capabilities догадками.
                self._cycles.pop(entity, None)
                adjusted.append(desired)
                continue

            cycle = self._cycles.get(entity)
            if (
                cycle is None
                or cycle.mode != mode
                or cycle.room_target != target
            ):
                error = (
                    target - room_temperature
                    if mode == "heat"
                    else room_temperature - target
                )
                bias = INITIAL_BIAS_C + min(MAX_EXTRA_BIAS_C, max(0.0, error))
                physical_target = _normalize(
                    target + (bias if mode == "heat" else -bias),
                    minimum=minimum,
                    maximum=maximum,
                    step=step,
                )
                cycle = _Cycle(
                    mode=mode,
                    room_target=target,
                    device_target=physical_target,
                    reference_temperature=room_temperature,
                    observed_at=now,
                )
                self._cycles[entity] = cycle
            elif now - cycle.observed_at >= STALL_WINDOW_SECONDS:
                progress = (
                    room_temperature - cycle.reference_temperature
                    if mode == "heat"
                    else cycle.reference_temperature - room_temperature
                )
                if progress < MIN_PROGRESS_C:
                    # Следующая ступень только при отсутствии прогресса за
                    # целое контрольное окно, не при каждом sensor update.
                    candidate = cycle.device_target + (
                        max(1.0, step) if mode == "heat" else -max(1.0, step)
                    )
                    cycle.device_target = _normalize(
                        candidate,
                        minimum=minimum,
                        maximum=maximum,
                        step=step,
                    )
                cycle.reference_temperature = room_temperature
                cycle.observed_at = now

            # Если capabilities изменились во время цикла, нормализуем повторно.
            physical_target = _normalize(
                cycle.device_target,
                minimum=minimum,
                maximum=maximum,
                step=step,
            )
            cycle.device_target = physical_target
            adjusted.append(
                replace(desired, target_temperature=physical_target)
            )

        return adjusted
