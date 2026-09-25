from __future__ import annotations

from dataclasses import dataclass, replace
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
    window_policy: str = "ignore"
    min_heating_outdoor_temperature: float | None = None


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
    window_sensors: tuple[str, ...]
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


def _optional_float(value: Any, path: str) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return _float(value, path)


def _entity(
    value: Any,
    path: str,
    domains: tuple[str, ...],
    *,
    required: bool = True,
) -> str:
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


def _entity_list(
    value: Any,
    path: str,
    domains: tuple[str, ...],
) -> tuple[str, ...]:
    """Parse a flat HAOS option field containing comma-separated entity IDs."""
    if value is None:
        return ()
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = [
            item.strip()
            for item in str(value).replace("\n", ",").split(",")
            if item.strip()
        ]
    result: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_items):
        entity_id = _entity(raw, f"{path}[{index}]", domains)
        if entity_id not in seen:
            result.append(entity_id)
            seen.add(entity_id)
    return tuple(result)


def _parse_room_targets(
    room: Mapping[str, Any],
    path: str,
) -> RoomTargets:
    # Accept the pre-release nested shape as a compatibility convenience.
    if isinstance(room.get("targets"), Mapping):
        targets = _as_mapping(room["targets"], f"{path}.targets")
        heat = _as_mapping(targets.get("heat"), f"{path}.targets.heat")
        cool = _as_mapping(targets.get("cool"), f"{path}.targets.cool")
        return RoomTargets(
            heat={
                Profile.DAY: _float(heat.get("day"), f"{path}.targets.heat.day"),
                Profile.NIGHT: _float(
                    heat.get("night"),
                    f"{path}.targets.heat.night",
                ),
                Profile.AWAY: _float(heat.get("away"), f"{path}.targets.heat.away"),
                Profile.ANTIFREEZE: _float(
                    heat.get("antifreeze"),
                    f"{path}.targets.heat.antifreeze",
                ),
            },
            cool={
                Profile.DAY: _float(cool.get("day"), f"{path}.targets.cool.day"),
                Profile.NIGHT: _float(
                    cool.get("night"),
                    f"{path}.targets.cool.night",
                ),
                Profile.AWAY: _float(cool.get("away"), f"{path}.targets.cool.away"),
            },
        )

    return RoomTargets(
        heat={
            Profile.DAY: _float(room.get("heat_day"), f"{path}.heat_day"),
            Profile.NIGHT: _float(room.get("heat_night"), f"{path}.heat_night"),
            Profile.AWAY: _float(room.get("heat_away"), f"{path}.heat_away"),
            Profile.ANTIFREEZE: _float(
                room.get("heat_antifreeze"),
                f"{path}.heat_antifreeze",
            ),
        },
        cool={
            Profile.DAY: _float(room.get("cool_day"), f"{path}.cool_day"),
            Profile.NIGHT: _float(room.get("cool_night"), f"{path}.cool_night"),
            Profile.AWAY: _float(room.get("cool_away"), f"{path}.cool_away"),
        },
    )


def _parse_device(item: Any, path: str) -> tuple[str, DeviceConfig]:
    current = _as_mapping(item, path)
    room_id = str(current.get("room_id", "")).strip().lower()
    entity_id = _entity(
        current.get("entity_id"),
        f"{path}.entity_id",
        ("climate", "switch"),
    )

    class_text = str(current.get("class", "")).strip().lower()
    try:
        device_class = DeviceClass(class_text)
    except ValueError as exc:
        raise ConfigError(f"{path}.class must be fast or slow") from exc

    function = str(current.get("function", "")).strip().lower()
    if function not in {"heat", "cool", "heat_cool"}:
        raise ConfigError(
            f"{path}.function must be heat, cool or heat_cool"
        )

    domain = entity_id.split(".", 1)[0]
    if domain == "switch" and function == "heat_cool":
        raise ConfigError(
            f"{path}: switch devices must have one explicit function"
        )
    if device_class is DeviceClass.SLOW and function != "heat":
        raise ConfigError(f"{path}: slow devices support heat only in v0.1")
    if device_class is DeviceClass.SLOW and domain != "climate":
        raise ConfigError(
            f"{path}: slow devices require a local climate thermostat in v0.1"
        )

    target = _optional_float(
        current.get("target_temperature"),
        f"{path}.target_temperature",
    )
    if device_class is DeviceClass.SLOW and target is None:
        raise ConfigError(
            f"{path}.target_temperature is required for slow climate"
        )

    window_policy = str(
        current.get("window_policy", "ignore")
    ).strip().lower()
    if window_policy not in {"ignore", "turn_off"}:
        raise ConfigError(
            f"{path}.window_policy must be ignore or turn_off"
        )

    min_outdoor = _optional_float(
        current.get("min_heating_outdoor_temperature"),
        f"{path}.min_heating_outdoor_temperature",
    )
    if min_outdoor is not None and function == "cool":
        raise ConfigError(
            f"{path}.min_heating_outdoor_temperature requires a heat-capable device"
        )

    return room_id, DeviceConfig(
        entity_id=entity_id,
        device_class=device_class,
        function=function,
        target_temperature=target,
        window_policy=window_policy,
        min_heating_outdoor_temperature=min_outdoor,
    )


def _disabled_humidity() -> HumidityConfig:
    return HumidityConfig(False, None, None, None)


def _parse_humidity_control(
    item: Any,
    path: str,
) -> tuple[str, HumidityConfig]:
    data = _as_mapping(item, path)
    room_id = str(data.get("room_id", "")).strip().lower()
    controller_type = str(data.get("type", "")).strip().lower()
    if controller_type not in {"humidifier", "dehumidifier"}:
        raise ConfigError(
            f"{path}.type must be humidifier or dehumidifier"
        )

    target = _float(data.get("target_default"), f"{path}.target_default")
    if not 0.0 <= target <= 100.0:
        raise ConfigError(f"{path}.target_default must be between 0 and 100")

    actuator = HumidityActuatorConfig(
        entity_id=_entity(
            data.get("actuator_entity_id"),
            f"{path}.actuator_entity_id",
            ("switch", "humidifier"),
        )
    )
    return room_id, HumidityConfig(
        True,
        controller_type,
        target,
        actuator,
    )


def parse_options(raw: Any) -> AppConfig:
    root = _as_mapping(raw, "options")

    global_raw = _as_mapping(root.get("global", {}), "global")
    hysteresis = _float(
        global_raw.get("hysteresis", 0.5),
        "global.hysteresis",
    )
    if not 0.0 <= hysteresis <= 5.0:
        raise ConfigError("global.hysteresis must be between 0 and 5")
    humidity_hysteresis = _float(
        global_raw.get("humidity_hysteresis", 3.0),
        "global.humidity_hysteresis",
    )
    if not 0.0 <= humidity_hysteresis <= 25.0:
        raise ConfigError(
            "global.humidity_hysteresis must be between 0 and 25"
        )

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

    outdoor_raw = _as_mapping(root.get("outdoor", {}), "outdoor")
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
            "outdoor.heat_threshold_default must be lower than "
            "cool_threshold_default"
        )

    source_rows = root.get("outdoor_sources")
    if source_rows is None:
        # Compatibility with the pre-release nested options shape.
        source_rows = outdoor_raw.get("sources", [])

    sources: list[OutdoorSourceConfig] = []
    source_names: set[str] = set()
    for index, item in enumerate(
        _as_list(source_rows, "outdoor_sources")
    ):
        source = _as_mapping(item, f"outdoor_sources[{index}]")
        name = str(source.get("name") or f"source_{index + 1}").strip()
        if not name:
            raise ConfigError(
                f"outdoor_sources[{index}].name must not be empty"
            )
        if name in source_names:
            raise ConfigError(f"outdoor source name duplicates {name}")
        source_names.add(name)
        sources.append(
            OutdoorSourceConfig(
                name=name,
                temperature=_entity(
                    source.get("temperature"),
                    f"outdoor_sources[{index}].temperature",
                    ("sensor",),
                ),
                humidity=_entity(
                    source.get("humidity"),
                    f"outdoor_sources[{index}].humidity",
                    ("sensor",),
                    required=False,
                ),
            )
        )
    outdoor = OutdoorConfig(
        heat_default,
        cool_default,
        tuple(sources),
    )

    room_rows = _as_list(root.get("rooms", []), "rooms")
    rooms: list[RoomConfig] = []
    room_ids: set[str] = set()
    inline_devices: list[tuple[str, DeviceConfig]] = []
    inline_humidity: dict[str, HumidityConfig] = {}

    for index, item in enumerate(room_rows):
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

        temperature_sensors = _entity_list(
            room_raw.get("temperature_sensors"),
            f"rooms[{index}].temperature_sensors",
            ("sensor",),
        )
        if not temperature_sensors:
            raise ConfigError(
                f"rooms[{index}].temperature_sensors must contain "
                "at least one sensor"
            )

        humidity_sensors = _entity_list(
            room_raw.get("humidity_sensors"),
            f"rooms[{index}].humidity_sensors",
            ("sensor",),
        )
        window_sensors = _entity_list(
            room_raw.get("window_sensors"),
            f"rooms[{index}].window_sensors",
            ("binary_sensor",),
        )

        rooms.append(
            RoomConfig(
                room_id=room_id,
                name=name,
                temperature_sensors=temperature_sensors,
                humidity_sensors=humidity_sensors,
                window_sensors=window_sensors,
                targets=_parse_room_targets(
                    room_raw,
                    f"rooms[{index}]",
                ),
                devices=(),
                humidity=_disabled_humidity(),
            )
        )

        # Compatibility with the pre-release nested shape.
        for device_index, device in enumerate(
            _as_list(room_raw.get("devices", []), f"rooms[{index}].devices")
        ):
            legacy = dict(_as_mapping(
                device,
                f"rooms[{index}].devices[{device_index}]",
            ))
            legacy["room_id"] = room_id
            inline_devices.append(
                _parse_device(
                    legacy,
                    f"rooms[{index}].devices[{device_index}]",
                )
            )

        humidity_raw = room_raw.get("humidity")
        if isinstance(humidity_raw, Mapping) and bool(
            humidity_raw.get("enabled", False)
        ):
            actuator = _as_mapping(
                humidity_raw.get("actuator"),
                f"rooms[{index}].humidity.actuator",
            )
            legacy_humidity = {
                "room_id": room_id,
                "type": humidity_raw.get("type"),
                "target_default": humidity_raw.get("target_default"),
                "actuator_entity_id": actuator.get("entity_id"),
            }
            _, parsed = _parse_humidity_control(
                legacy_humidity,
                f"rooms[{index}].humidity",
            )
            inline_humidity[room_id] = parsed

    devices_by_room: dict[str, list[DeviceConfig]] = {
        room_id: [] for room_id in room_ids
    }
    device_rows = root.get("devices")
    parsed_devices: list[tuple[str, DeviceConfig]]
    if device_rows is None:
        parsed_devices = inline_devices
    else:
        parsed_devices = [
            _parse_device(item, f"devices[{index}]")
            for index, item in enumerate(
                _as_list(device_rows, "devices")
            )
        ]

    actuator_owners: dict[str, str] = {}
    for room_id, device in parsed_devices:
        if room_id not in room_ids:
            raise ConfigError(
                f"device {device.entity_id} references unknown room {room_id}"
            )
        owner = f"room:{room_id}:thermal"
        previous = actuator_owners.get(device.entity_id)
        if previous is not None:
            raise ConfigError(
                f"actuator {device.entity_id} is configured twice: "
                f"{previous}, {owner}"
            )
        actuator_owners[device.entity_id] = owner
        devices_by_room[room_id].append(device)

    humidity_by_room: dict[str, HumidityConfig] = {
        room_id: config
        for room_id, config in inline_humidity.items()
    }
    humidity_rows = root.get("humidity_controls")
    if humidity_rows is not None:
        humidity_by_room = {}
        for index, item in enumerate(
            _as_list(humidity_rows, "humidity_controls")
        ):
            room_id, humidity = _parse_humidity_control(
                item,
                f"humidity_controls[{index}]",
            )
            if room_id not in room_ids:
                raise ConfigError(
                    f"humidity control references unknown room {room_id}"
                )
            if room_id in humidity_by_room:
                raise ConfigError(
                    f"humidity control is configured twice for room {room_id}"
                )
            humidity_by_room[room_id] = humidity

    final_rooms: list[RoomConfig] = []
    for room in rooms:
        humidity = humidity_by_room.get(
            room.room_id,
            _disabled_humidity(),
        )
        if humidity.enabled and not room.humidity_sensors:
            raise ConfigError(
                f"room {room.room_id} requires humidity_sensors when "
                "humidity control is configured"
            )
        if humidity.actuator is not None:
            entity_id = humidity.actuator.entity_id
            owner = f"room:{room.room_id}:humidity"
            previous = actuator_owners.get(entity_id)
            if previous is not None:
                raise ConfigError(
                    f"actuator {entity_id} is configured twice: "
                    f"{previous}, {owner}"
                )
            actuator_owners[entity_id] = owner

        final_rooms.append(
            replace(
                room,
                devices=tuple(devices_by_room[room.room_id]),
                humidity=humidity,
            )
        )

    telemetry_enabled = bool(root.get("telemetry_enabled", False))
    log_level = str(root.get("log_level", "info")).strip().lower()
    if log_level not in {"debug", "info", "warning", "error"}:
        raise ConfigError(
            "log_level must be debug, info, warning or error"
        )

    return AppConfig(
        global_config=global_config,
        outdoor=outdoor,
        rooms=tuple(final_rooms),
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
        result.update(room.window_sensors)
        for device in room.devices:
            result.add(device.entity_id)
        if room.humidity.actuator is not None:
            result.add(room.humidity.actuator.entity_id)

    return frozenset(result)
