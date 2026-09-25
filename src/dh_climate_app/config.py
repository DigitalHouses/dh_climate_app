from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from .core import DeviceClass, Profile

ROOM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")


class ConfigError(ValueError):
    """Raised when Home Assistant App options are invalid."""


@dataclass(frozen=True)
class GlobalConfig:
    hysteresis: float
    humidity_hysteresis: float
    night_mode: str
    we_at_home: str


@dataclass(frozen=True)
class OutdoorSourceConfig:
    name: str
    temperature: str
    humidity: str


@dataclass(frozen=True)
class OutdoorConfig:
    heat_threshold_default: float
    cool_threshold_default: float
    sources: tuple[OutdoorSourceConfig, ...]


@dataclass(frozen=True)
class DeviceConfig:
    entity_id: str
    device_class: DeviceClass
    function: str
    target_temperature: float | None


@dataclass(frozen=True)
class HumidityActuatorConfig:
    entity_id: str


@dataclass(frozen=True)
class HumidityConfig:
    enabled: bool
    controller_type: str | None
    target_default: float | None
    actuator: HumidityActuatorConfig | None


@dataclass(frozen=True)
class RoomTargets:
    heat: Mapping[Profile, float]
    cool: Mapping[Profile, float]


@dataclass(frozen=True)
class RoomConfig:
    room_id: str
    name: str
    temperature_sensors: tuple[str, ...]
    humidity_sensors: tuple[str, ...]
    targets: RoomTargets
    devices: tuple[DeviceConfig, ...]
    humidity: HumidityConfig


@dataclass(frozen=True)
class AppConfig:
    global_config: GlobalConfig
    outdoor: OutdoorConfig
    rooms: tuple[RoomConfig, ...]
    telemetry_enabled: bool
    log_level: str


def _as_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{path} must be an object")
    return value


def _as_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigError(f"{path} must be a list")
    return value


def _float(value: Any, path: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{path} must be numeric") from exc
    return parsed


def _entity(value: Any, path: str, domains: tuple[str, ...], *, required: bool = True) -> str:
    text = str(value or "").strip()
    if not text:
        if required:
            raise ConfigError(f"{path} is required")
        return ""
    if "." not in text:
        raise ConfigError(f"{path} must be a Home Assistant entity_id")
    domain = text.split(".", 1)[0]
    if domain not in domains:
        allowed = ", ".join(f"{item}.*" for item in domains)
        raise ConfigError(f"{path} must be one of: {allowed}")
    return text


def _parse_profile_targets(raw: Mapping[str, Any], path: str, *, heat: bool) -> dict[Profile, float]:
    required = (Profile.DAY, Profile.NIGHT, Profile.AWAY)
    if heat:
        required = required + (Profile.ANTIFREEZE,)
    result: dict[Profile, float] = {}
    for profile in required:
        if profile.value not in raw:
            raise ConfigError(f"{path}.{profile.value} is required")
        result[profile] = _float(raw[profile.value], f"{path}.{profile.value}")
    return result


def _parse_devices(raw: Any, path: str) -> tuple[DeviceConfig, ...]:
    result: list[DeviceConfig] = []
    seen: set[str] = set()
    for index, item in enumerate(_as_list(raw, path)):
        current = _as_mapping(item, f"{path}[{index}]")
        entity_id = _entity(
            current.get("entity_id"),
            f"{path}[{index}].entity_id",
            ("climate", "switch"),
        )
        if entity_id in seen:
            raise ConfigError(f"{path}[{index}].entity_id duplicates {entity_id}")
        seen.add(entity_id)

        class_text = str(current.get("class", "")).strip().lower()
        try:
            device_class = DeviceClass(class_text)
        except ValueError as exc:
            raise ConfigError(f"{path}[{index}].class must be fast or slow") from exc

        function = str(current.get("function", "")).strip().lower()
        if function not in {"heat", "cool", "heat_cool"}:
            raise ConfigError(
                f"{path}[{index}].function must be heat, cool or heat_cool"
            )
        domain = entity_id.split(".", 1)[0]
        if domain == "switch" and function == "heat_cool":
            raise ConfigError(
                f"{path}[{index}]: switch devices must have one explicit function"
            )
        if device_class is DeviceClass.SLOW and function != "heat":
            raise ConfigError(
                f"{path}[{index}]: slow devices support heat only in v0.1"
            )
        if device_class is DeviceClass.SLOW and domain != "climate":
            raise ConfigError(
                f"{path}[{index}]: slow devices require a local climate thermostat in v0.1"
            )

        target: float | None = None
        if current.get("target_temperature") is not None:
            target = _float(
                current.get("target_temperature"),
                f"{path}[{index}].target_temperature",
            )
        if device_class is DeviceClass.SLOW and domain == "climate" and target is None:
            raise ConfigError(
                f"{path}[{index}].target_temperature is required for slow climate"
            )

        result.append(
            DeviceConfig(
                entity_id=entity_id,
                device_class=device_class,
                function=function,
                target_temperature=target,
            )
        )
    return tuple(result)


def _parse_humidity(raw: Any, path: str) -> HumidityConfig:
    if raw is None:
        return HumidityConfig(False, None, None, None)
    data = _as_mapping(raw, path)
    enabled = bool(data.get("enabled", False))
    if not enabled:
        return HumidityConfig(False, None, None, None)

    controller_type = str(data.get("type", "")).strip().lower()
    if controller_type not in {"humidifier", "dehumidifier"}:
        raise ConfigError(f"{path}.type must be humidifier or dehumidifier")

    target = _float(data.get("target_default"), f"{path}.target_default")
    if not 0.0 <= target <= 100.0:
        raise ConfigError(f"{path}.target_default must be between 0 and 100")

    actuator_raw = _as_mapping(data.get("actuator"), f"{path}.actuator")
    actuator = HumidityActuatorConfig(
        entity_id=_entity(
            actuator_raw.get("entity_id"),
            f"{path}.actuator.entity_id",
            ("switch", "humidifier"),
        )
    )
    return HumidityConfig(True, controller_type, target, actuator)


def parse_options(raw: Any) -> AppConfig:
    root = _as_mapping(raw, "options")

    global_raw = _as_mapping(root.get("global", {}), "global")
    hysteresis = _float(global_raw.get("hysteresis", 0.5), "global.hysteresis")
    if not 0.0 <= hysteresis <= 5.0:
        raise ConfigError("global.hysteresis must be between 0 and 5")
    humidity_hysteresis = _float(
        global_raw.get("humidity_hysteresis", 3.0),
        "global.humidity_hysteresis",
    )
    if not 0.0 <= humidity_hysteresis <= 25.0:
        raise ConfigError("global.humidity_hysteresis must be between 0 and 25")

    global_config = GlobalConfig(
        hysteresis=hysteresis,
        humidity_hysteresis=humidity_hysteresis,
        night_mode=_entity(
            global_raw.get("night_mode"),
            "global.night_mode",
            ("input_boolean", "binary_sensor"),
            required=False,
        ),
        we_at_home=_entity(
            global_raw.get("we_at_home"),
            "global.we_at_home",
            ("input_boolean", "binary_sensor"),
            required=False,
        ),
    )

    outdoor_raw = _as_mapping(root.get("outdoor"), "outdoor")
    heat_default = _float(
        outdoor_raw.get("heat_threshold_default", 12.0),
        "outdoor.heat_threshold_default",
    )
    cool_default = _float(
        outdoor_raw.get("cool_threshold_default", 20.0),
        "outdoor.cool_threshold_default",
    )
    if heat_default >= cool_default:
        raise ConfigError(
            "outdoor.heat_threshold_default must be lower than cool_threshold_default"
        )

    sources: list[OutdoorSourceConfig] = []
    source_names: set[str] = set()
    for index, item in enumerate(_as_list(outdoor_raw.get("sources", []), "outdoor.sources")):
        source = _as_mapping(item, f"outdoor.sources[{index}]")
        name = str(source.get("name") or f"source_{index + 1}").strip()
        if not name:
            raise ConfigError(f"outdoor.sources[{index}].name must not be empty")
        if name in source_names:
            raise ConfigError(f"outdoor source name duplicates {name}")
        source_names.add(name)
        sources.append(
            OutdoorSourceConfig(
                name=name,
                temperature=_entity(
                    source.get("temperature"),
                    f"outdoor.sources[{index}].temperature",
                    ("sensor",),
                ),
                humidity=_entity(
                    source.get("humidity"),
                    f"outdoor.sources[{index}].humidity",
                    ("sensor",),
                    required=False,
                ),
            )
        )
    if not sources:
        raise ConfigError("outdoor.sources must contain at least one source")

    outdoor = OutdoorConfig(heat_default, cool_default, tuple(sources))

    rooms: list[RoomConfig] = []
    room_ids: set[str] = set()
    for index, item in enumerate(_as_list(root.get("rooms", []), "rooms")):
        room_raw = _as_mapping(item, f"rooms[{index}]")
        room_id = str(room_raw.get("id", "")).strip().lower()
        if not ROOM_ID_RE.fullmatch(room_id):
            raise ConfigError(
                f"rooms[{index}].id must match {ROOM_ID_RE.pattern}"
            )
        if room_id in room_ids:
            raise ConfigError(f"rooms[{index}].id duplicates {room_id}")
        room_ids.add(room_id)
        name = str(room_raw.get("name", "")).strip()
        if not name:
            raise ConfigError(f"rooms[{index}].name is required")

        temperature_sensors = tuple(
            _entity(
                entity_id,
                f"rooms[{index}].temperature_sensors[{sensor_index}]",
                ("sensor",),
            )
            for sensor_index, entity_id in enumerate(
                _as_list(
                    room_raw.get("temperature_sensors", []),
                    f"rooms[{index}].temperature_sensors",
                )
            )
        )
        if not temperature_sensors:
            raise ConfigError(
                f"rooms[{index}].temperature_sensors must contain at least one sensor"
            )
        humidity_sensors = tuple(
            _entity(
                entity_id,
                f"rooms[{index}].humidity_sensors[{sensor_index}]",
                ("sensor",),
            )
            for sensor_index, entity_id in enumerate(
                _as_list(
                    room_raw.get("humidity_sensors", []),
                    f"rooms[{index}].humidity_sensors",
                )
            )
        )

        targets_raw = _as_mapping(room_raw.get("targets"), f"rooms[{index}].targets")
        heat_raw = _as_mapping(targets_raw.get("heat"), f"rooms[{index}].targets.heat")
        cool_raw = _as_mapping(targets_raw.get("cool"), f"rooms[{index}].targets.cool")
        targets = RoomTargets(
            heat=_parse_profile_targets(
                heat_raw, f"rooms[{index}].targets.heat", heat=True
            ),
            cool=_parse_profile_targets(
                cool_raw, f"rooms[{index}].targets.cool", heat=False
            ),
        )

        humidity = _parse_humidity(room_raw.get("humidity"), f"rooms[{index}].humidity")
        if humidity.enabled and not humidity_sensors:
            raise ConfigError(
                f"rooms[{index}].humidity_sensors are required when humidity control is enabled"
            )

        rooms.append(
            RoomConfig(
                room_id=room_id,
                name=name,
                temperature_sensors=temperature_sensors,
                humidity_sensors=humidity_sensors,
                targets=targets,
                devices=_parse_devices(
                    room_raw.get("devices", []),
                    f"rooms[{index}].devices",
                ),
                humidity=humidity,
            )
        )

    actuator_owners: dict[str, str] = {}
    for room in rooms:
        for device in room.devices:
            owner = f"room:{room.room_id}:thermal"
            previous = actuator_owners.get(device.entity_id)
            if previous is not None:
                raise ConfigError(
                    f"actuator {device.entity_id} is configured twice: {previous}, {owner}"
                )
            actuator_owners[device.entity_id] = owner
        if room.humidity.actuator is not None:
            entity_id = room.humidity.actuator.entity_id
            owner = f"room:{room.room_id}:humidity"
            previous = actuator_owners.get(entity_id)
            if previous is not None:
                raise ConfigError(
                    f"actuator {entity_id} is configured twice: {previous}, {owner}"
                )
            actuator_owners[entity_id] = owner

    telemetry_enabled = bool(root.get("telemetry_enabled", False))
    log_level = str(root.get("log_level", "info")).strip().lower()
    if log_level not in {"debug", "info", "warning", "error"}:
        raise ConfigError("log_level must be debug, info, warning or error")

    return AppConfig(
        global_config=global_config,
        outdoor=outdoor,
        rooms=tuple(rooms),
        telemetry_enabled=telemetry_enabled,
        log_level=log_level,
    )


def configured_entity_ids(config: AppConfig) -> frozenset[str]:
    """Return every Home Assistant entity referenced by App configuration."""
    result: set[str] = set()

    if config.global_config.night_mode:
        result.add(config.global_config.night_mode)
    if config.global_config.we_at_home:
        result.add(config.global_config.we_at_home)

    for source in config.outdoor.sources:
        result.add(source.temperature)
        if source.humidity:
            result.add(source.humidity)

    for room in config.rooms:
        result.update(room.temperature_sensors)
        result.update(room.humidity_sensors)
        for device in room.devices:
            result.add(device.entity_id)
        if room.humidity.actuator is not None:
            result.add(room.humidity.actuator.entity_id)

    return frozenset(result)
