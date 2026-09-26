from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Mapping

from .climate_log import ClimateLog
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
    room_id: str | None = None


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
        climate_log: ClimateLog | None = None,
        retry_seconds: float = 5.0,
        max_attempts: int = 3,
        cooldown_seconds: float = 300.0,
    ) -> None:
        self.ha = ha
        self.climate_log = climate_log
        self.retry_seconds = float(retry_seconds)
        self.max_attempts = int(max_attempts)
        self.cooldown_seconds = float(cooldown_seconds)
        self._attempts: dict[str, _Attempt] = {}
        self._blocked_signatures: dict[str, tuple[str, str]] = {}

    @staticmethod
    def _room_id(desired: DesiredDeviceState) -> str | None:
        parts = desired.source.split(":")
        if len(parts) >= 3 and parts[0] == "room":
            return parts[1]
        return None

    @classmethod
    def _title(cls, desired: DesiredDeviceState) -> str:
        parts = desired.source.split(":")
        if len(parts) >= 3 and parts[0] == "room":
            return f"{parts[2].upper()} · {parts[1]}"
        return "EXECUTOR"

    def _trace(
        self,
        desired: DesiredDeviceState,
        message: str,
        *,
        level: int = logging.INFO,
    ) -> None:
        title = self._title(desired)
        if self.climate_log is not None:
            self.climate_log.write2climate_log(
                title,
                f"{desired.entity_id} | {message}",
                level=level,
            )
        else:
            LOGGER.log(level, "[%s] %s | %s", title, desired.entity_id, message)

    @staticmethod
    def _desired_text(desired: DesiredDeviceState) -> str:
        if desired.domain == "switch":
            return "on" if desired.power else "off"
        if desired.domain == "climate":
            return (
                f"mode={desired.hvac_mode}"
                f" target={desired.target_temperature}"
            )
        if desired.domain == "humidifier":
            return (
                f"power={'on' if desired.power else 'off'}"
                f" target={desired.target_humidity}"
            )
        return desired.domain

    @classmethod
    def _actual_text(cls, actual: HaState) -> str:
        target = cls._float_attr(
            actual,
            "temperature",
            "humidity",
            "target_humidity",
        )
        if target is None:
            return actual.state
        return f"{actual.state} target={target}"

    def _record_block(
        self,
        desired: DesiredDeviceState,
        problem: ExecutionProblem,
    ) -> None:
        signature = (problem.reason, problem.details)
        if self._blocked_signatures.get(desired.entity_id) == signature:
            return
        self._blocked_signatures[desired.entity_id] = signature
        self._trace(
            desired,
            f"SKIP {problem.reason} | {problem.details}",
            level=logging.WARNING,
        )

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
                problem = ExecutionProblem(
                    desired.entity_id,
                    "unavailable",
                    "Home Assistant entity is unavailable",
                    room_id=self._room_id(desired),
                )
                problems.append(problem)
                self._record_block(desired, problem)
                continue

            capability_problem = self._capability_problem(desired, actual)
            if capability_problem is not None:
                problems.append(capability_problem)
                self._record_block(desired, capability_problem)
                continue

            if desired.entity_id in self._blocked_signatures:
                self._blocked_signatures.pop(desired.entity_id, None)
                self._trace(desired, "UNBLOCKED")

            mismatches = self._mismatches(desired, actual)
            if not mismatches:
                previous_attempt = self._attempts.pop(desired.entity_id, None)
                if previous_attempt is not None:
                    self._trace(
                        desired,
                        f"CONFIRMED | actual={self._actual_text(actual)}",
                    )
                continue

            attempt = self._attempts.get(desired.entity_id)
            if attempt is None or attempt.signature != desired.signature:
                attempt = _Attempt(desired.signature, 0, 0.0)
                self._attempts[desired.entity_id] = attempt
                self._trace(
                    desired,
                    (
                        f"desired={self._desired_text(desired)}"
                        f" | actual={self._actual_text(actual)}"
                        f" | mismatch={','.join(mismatches)}"
                    ),
                )

            if now < attempt.next_allowed_at:
                if attempt.attempts >= self.max_attempts:
                    problems.append(
                        ExecutionProblem(
                            desired.entity_id,
                            "no_confirmation",
                            ",".join(mismatches),
                            room_id=self._room_id(desired),
                        )
                    )
                continue

            if attempt.attempts >= self.max_attempts:
                attempt.attempts = 0

            if attempt.attempts > 0:
                self._trace(
                    desired,
                    f"RETRY {attempt.attempts + 1}/{self.max_attempts}"
                    f" | mismatch={','.join(mismatches)}",
                    level=logging.WARNING,
                )

            try:
                commands += await self._apply(desired, actual)
            except Exception as exc:
                LOGGER.exception("Device command failed: %s", desired.entity_id)
                problems.append(
                    ExecutionProblem(
                        desired.entity_id,
                        "service_error",
                        str(exc),
                        room_id=self._room_id(desired),
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
                        room_id=self._room_id(desired),
                    )
                )
                self._trace(
                    desired,
                    f"COOLDOWN {self.cooldown_seconds:g}s"
                    f" | no_confirmation={','.join(mismatches)}",
                    level=logging.WARNING,
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

    def _capability_problem(
        self,
        desired: DesiredDeviceState,
        actual: HaState,
    ) -> ExecutionProblem | None:
        if desired.domain == "climate":
            modes = actual.attributes.get("hvac_modes")
            if (
                desired.hvac_mode is not None
                and isinstance(modes, (list, tuple))
                and desired.hvac_mode not in modes
            ):
                return ExecutionProblem(
                    desired.entity_id,
                    "unsupported_mode",
                    f"requested={desired.hvac_mode}; supported={list(modes)}",
                    room_id=self._room_id(desired),
                )
            if desired.target_temperature is not None:
                minimum = self._float_attr(actual, "min_temp")
                maximum = self._float_attr(actual, "max_temp")
                if minimum is not None and desired.target_temperature < minimum:
                    return ExecutionProblem(
                        desired.entity_id,
                        "target_out_of_range",
                        f"target={desired.target_temperature}; min={minimum}",
                        room_id=self._room_id(desired),
                    )
                if maximum is not None and desired.target_temperature > maximum:
                    return ExecutionProblem(
                        desired.entity_id,
                        "target_out_of_range",
                        f"target={desired.target_temperature}; max={maximum}",
                        room_id=self._room_id(desired),
                    )

        if desired.domain == "humidifier" and desired.target_humidity is not None:
            minimum = self._float_attr(actual, "min_humidity")
            maximum = self._float_attr(actual, "max_humidity")
            if minimum is not None and desired.target_humidity < minimum:
                return ExecutionProblem(
                    desired.entity_id,
                    "target_out_of_range",
                    f"target={desired.target_humidity}; min={minimum}",
                    room_id=self._room_id(desired),
                )
            if maximum is not None and desired.target_humidity > maximum:
                return ExecutionProblem(
                    desired.entity_id,
                    "target_out_of_range",
                    f"target={desired.target_humidity}; max={maximum}",
                    room_id=self._room_id(desired),
                )

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
                self._trace(
                    desired,
                    f"CALL switch.{'turn_on' if desired.power else 'turn_off'}",
                )
                await self.ha.call_service(
                    "switch",
                    "turn_on" if desired.power else "turn_off",
                    {"entity_id": desired.entity_id},
                )
                commands += 1
            return commands

        if desired.domain == "climate":
            if desired.hvac_mode is not None and actual.state != desired.hvac_mode:
                self._trace(
                    desired,
                    f"CALL climate.set_hvac_mode -> {desired.hvac_mode}",
                )
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
                    self._trace(
                        desired,
                        (
                            "CALL climate.set_temperature -> "
                            f"{desired.target_temperature}"
                        ),
                    )
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
                self._trace(
                    desired,
                    (
                        "CALL humidifier."
                        f"{'turn_on' if desired.power else 'turn_off'}"
                    ),
                )
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
                    self._trace(
                        desired,
                        f"CALL humidifier.set_humidity -> {desired.target_humidity}",
                    )
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
