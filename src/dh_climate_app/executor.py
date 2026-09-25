from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Mapping

from .devices import DesiredDeviceState
from .ha_client import HaState, HomeAssistantClient


LOGGER = logging.getLogger(__name__)


@dataclass
class _Attempt:
    signature: tuple[object, ...]
    attempts: int
    next_allowed_at: float


@dataclass(frozen=True)
class ExecutionProblem:
    entity_id: str
    reason: str
    details: str


@dataclass(frozen=True)
class ReconcileSummary:
    commands: int
    problems: tuple[ExecutionProblem, ...]


class DeviceExecutor:
    """Idempotent HA service executor with bounded retry pressure."""

    def __init__(
        self,
        ha: HomeAssistantClient,
        *,
        retry_seconds: float = 5.0,
        max_attempts: int = 3,
        cooldown_seconds: float = 300.0,
    ) -> None:
        self.ha = ha
        self.retry_seconds = float(retry_seconds)
        self.max_attempts = int(max_attempts)
        self.cooldown_seconds = float(cooldown_seconds)
        self._attempts: dict[str, _Attempt] = {}

    async def reconcile(
        self,
        desired_states: list[DesiredDeviceState],
        actual_states: Mapping[str, HaState],
        *,
        now_monotonic: float | None = None,
    ) -> ReconcileSummary:
        now = time.monotonic() if now_monotonic is None else now_monotonic
        commands = 0
        problems: list[ExecutionProblem] = []

        for desired in desired_states:
            actual = actual_states.get(desired.entity_id)
            if actual is None or actual.state in {"unknown", "unavailable"}:
                problems.append(
                    ExecutionProblem(
                        desired.entity_id,
                        "unavailable",
                        "Home Assistant entity is unavailable",
                    )
                )
                continue

            mismatches = self._mismatches(desired, actual)
            if not mismatches:
                self._attempts.pop(desired.entity_id, None)
                continue

            attempt = self._attempts.get(desired.entity_id)
            if attempt is None or attempt.signature != desired.signature:
                attempt = _Attempt(desired.signature, 0, 0.0)
                self._attempts[desired.entity_id] = attempt

            if now < attempt.next_allowed_at:
                if attempt.attempts >= self.max_attempts:
                    problems.append(
                        ExecutionProblem(
                            desired.entity_id,
                            "no_confirmation",
                            ",".join(mismatches),
                        )
                    )
                continue

            if attempt.attempts >= self.max_attempts:
                attempt.attempts = 0

            try:
                commands += await self._apply(desired, actual)
            except Exception as exc:
                LOGGER.exception("Device command failed: %s", desired.entity_id)
                problems.append(
                    ExecutionProblem(
                        desired.entity_id,
                        "service_error",
                        str(exc),
                    )
                )

            attempt.attempts += 1
            if attempt.attempts >= self.max_attempts:
                attempt.next_allowed_at = now + self.cooldown_seconds
                problems.append(
                    ExecutionProblem(
                        desired.entity_id,
                        "no_confirmation",
                        ",".join(mismatches),
                    )
                )
            else:
                attempt.next_allowed_at = now + self.retry_seconds

        return ReconcileSummary(commands=commands, problems=tuple(problems))

    @staticmethod
    def _float_attr(actual: HaState, *names: str) -> float | None:
        for name in names:
            value = actual.attributes.get(name)
            try:
                if value is not None:
                    return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def _mismatches(
        self,
        desired: DesiredDeviceState,
        actual: HaState,
    ) -> list[str]:
        mismatches: list[str] = []

        if desired.domain == "switch":
            expected = "on" if desired.power else "off"
            if actual.state != expected:
                mismatches.append("power")
            return mismatches

        if desired.domain == "climate":
            if desired.hvac_mode is not None and actual.state != desired.hvac_mode:
                mismatches.append("hvac_mode")
            if (
                desired.hvac_mode != "off"
                and desired.target_temperature is not None
            ):
                actual_target = self._float_attr(actual, "temperature")
                if (
                    actual_target is None
                    or abs(actual_target - desired.target_temperature) > 0.05
                ):
                    mismatches.append("target_temperature")
            return mismatches

        if desired.domain == "humidifier":
            expected = "on" if desired.power else "off"
            if actual.state.lower() != expected:
                mismatches.append("power")
            if desired.target_humidity is not None:
                actual_target = self._float_attr(
                    actual,
                    "humidity",
                    "target_humidity",
                )
                if (
                    actual_target is None
                    or abs(actual_target - desired.target_humidity) > 0.05
                ):
                    mismatches.append("target_humidity")
            return mismatches

        mismatches.append("unsupported_domain")
        return mismatches

    async def _apply(
        self,
        desired: DesiredDeviceState,
        actual: HaState,
    ) -> int:
        commands = 0

        if desired.domain == "switch":
            expected = "on" if desired.power else "off"
            if actual.state != expected:
                await self.ha.call_service(
                    "switch",
                    "turn_on" if desired.power else "turn_off",
                    {"entity_id": desired.entity_id},
                )
                commands += 1
            return commands

        if desired.domain == "climate":
            if desired.hvac_mode is not None and actual.state != desired.hvac_mode:
                await self.ha.call_service(
                    "climate",
                    "set_hvac_mode",
                    {
                        "entity_id": desired.entity_id,
                        "hvac_mode": desired.hvac_mode,
                    },
                )
                commands += 1
            if (
                desired.hvac_mode != "off"
                and desired.target_temperature is not None
            ):
                actual_target = self._float_attr(actual, "temperature")
                if (
                    actual_target is None
                    or abs(actual_target - desired.target_temperature) > 0.05
                ):
                    await self.ha.call_service(
                        "climate",
                        "set_temperature",
                        {
                            "entity_id": desired.entity_id,
                            "temperature": desired.target_temperature,
                        },
                    )
                    commands += 1
            return commands

        if desired.domain == "humidifier":
            expected = "on" if desired.power else "off"
            if actual.state.lower() != expected:
                await self.ha.call_service(
                    "humidifier",
                    "turn_on" if desired.power else "turn_off",
                    {"entity_id": desired.entity_id},
                )
                commands += 1
            if desired.target_humidity is not None:
                actual_target = self._float_attr(
                    actual,
                    "humidity",
                    "target_humidity",
                )
                if (
                    actual_target is None
                    or abs(actual_target - desired.target_humidity) > 0.05
                ):
                    await self.ha.call_service(
                        "humidifier",
                        "set_humidity",
                        {
                            "entity_id": desired.entity_id,
                            "humidity": desired.target_humidity,
                        },
                    )
                    commands += 1
            return commands

        raise ValueError(f"unsupported HA actuator domain={desired.domain}")
