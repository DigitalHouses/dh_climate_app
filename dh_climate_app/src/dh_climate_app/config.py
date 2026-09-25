from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

from .core import DeviceClass, Profile

ROOM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
ENTITY_LIST_SPLIT_RE = re.compile(r"[,\n]+")


class ConfigError(ValueError):
    """Raised when Home Assistant App options are invalid."""


@dataclass(frozen=True)
class GlobalConfig:
    hysteresis: float
    humidity_hysteresis: float
    night_mode: str
    we_at_home: str


@dataclass(frozen=True)
class OutdoorConfig:
    heat_threshold_default: float
    cool_threshold_default: float
    temperature_sources: tuple[str, ...]
    humidity_sources: tuple[str, ...]


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
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{path} must be numeric") from exc


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
    *,
    required: bool = False,
) -> tuple[str, ...]:
    if value is None:
        raw_items: Sequence[Any] = ()
    elif isinstance(value, str):
        raw_items = [
            item.strip()
            for item in ENTITY_LIST_SPLIT_RE.split(value)
            if item.strip()
        ]
    elif isinstance(value, (list, tuple)):
        raw_items = value
    else:
        raise ConfigError(f"{path} must be a comma-separated entity list")

    result: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_items):
        entity_id = _entity(raw, f"{path}[{index}]", domains)
        if entity_id not in seen:
            seen.add(entity_id)
            result.append(entity_id)

    if required and not result:
        raise ConfigError(f"{path} must contain at least one entity")
    return tuple(result)


def _room_targets(room: Mapping[str, Any], path: str) -> RoomTargets:
    heat = {
        Profile.DAY: _float(room.get("heat_day"), f"{path}.heat_day"),
        Profile.NIGHT: _float(room.get("heat_night"), f"{path}.heat_night"),
        Profile.AWAY: _float(room.get("heat_away"), f"{path}.heat_away"),
        Profile.ANTIFREEZE: _float(
            room.get("heat_antifreeze"),
            f"{path}.heat_antifreeze",
        ),
    }
    cool = {
        Profile.DAY: _float(room.get("cool_day"), f"{path}.cool_day"),
        Profile.NIGHT: _float(room.get("cool_night"), f"{path}.cool_night"),
        Profile.AWAY: _float(room.get("cool_away"), f"{path}.cool_away"),
    }
    for profile, target in (*heat.items(), *cool.items()):
        if not 5.0 <= target <= 35.0:
            raise ConfigError(
                f"{path}: target for {profile.value} must be between 5 and 35"
            )
    return RoomTargets(heat=heat, cool=cool)


def _room_devices(
    room: Mapping[str, Any],
    path: str,
    *,
    ac_min_outdoor_temperature: float,
) -> tuple[DeviceConfig, ...]:
    fast_heat = _entity_list(
        room.get("fast_heat"),
        f"{path}.fast_heat",
        ("climate", "switch"),
    )
    fast_cool = _entity_list(
        room.get("fast_cool"),
        f"{path}.fast_cool",
        ("climate", "switch"),
    )
    slow_heat = _entity_list(
        room.get("slow_heat"),
        f"{path}.slow_heat",
        ("climate",),
    )
    window_off = set(
        _entity_list(
            room.get("window_off_devices"),
            f"{path}.window_off_devices",
            ("climate", "switch"),
        )
    )

    fast_heat_set = set(fast_heat)
    fast_cool_set = set(fast_cool)
    slow_set = set(slow_heat)
    overlap = slow_set & (fast_heat_set | fast_cool_set)
    if overlap:
        raise ConfigError(
            f"{path}: devices cannot be both FAST and SLOW: {sorted(overlap)}"
        )

    all_thermal = fast_heat_set | fast_cool_set | slow_set
    unknown_window_devices = window_off - all_thermal
    if unknown_window_devices:
        raise ConfigError(
            f"{path}.window_off_devices contains non-thermal devices: "
            f"{sorted(unknown_window_devices)}"
        )

    devices: list[DeviceConfig] = []
    ordered_fast = list(fast_heat)
    ordered_fast.extend(
        entity_id for entity_id in fast_cool if entity_id not in fast_heat_set
    )
    for entity_id in ordered_fast:
        in_heat = entity_id in fast_heat_set
        in_cool = entity_id in fast_cool_set
        if in_heat and in_cool:
            function = "heat_cool"
        elif in_heat:
            function = "heat"
        else:
            function = "cool"

        if entity_id.startswith("switch.") and function == "heat_cool":
            raise ConfigError(
                f"{path}: switch {entity_id} cannot be both heat and cool"
            )

        # A climate entity configured for both heating and cooling represents
        # the legacy AC/heat-pump class for low-outdoor-temperature protection.
        minimum = (
            ac_min_outdoor_temperature
            if function == "heat_cool" and entity_id.startswith("climate.")
            else None
        )
        devices.append(
            DeviceConfig(
                entity_id=entity_id,
                device_class=DeviceClass.FAST,
                function=function,
                target_temperature=None,
                window_policy=(
                    "turn_off" if entity_id in window_off else "ignore"
                ),
                min_heating_outdoor_temperature=minimum,
            )
        )

    slow_target = _optional_float(
        room.get("slow_target"),
        f"{path}.slow_target",
    )
    if slow_heat and slow_target is None:
        raise ConfigError(
            f"{path}.slow_target is required when slow_heat is configured"
        )
    for entity_id in slow_heat:
        devices.append(
            DeviceConfig(
                entity_id=entity_id,
                device_class=DeviceClass.SLOW,
                function="heat",
                target_temperature=slow_target,
                window_policy=(
                    "turn_off" if entity_id in window_off else "ignore"
                ),
                min_heating_outdoor_temperature=None,
            )
        )
    return tuple(devices)


def _room_humidity(
    room: Mapping[str, Any],
    path: str,
    humidity_sensors: tuple[str, ...],
) -> HumidityConfig:
    mode = str(room.get("humidity_mode", "off")).strip().lower()
    if mode not in {"off", "humidifier", "dehumidifier"}:
        raise ConfigError(
            f"{path}.humidity_mode must be off, humidifier or dehumidifier"
        )
    if mode == "off":
        return HumidityConfig(False, None, None, None)

    if not humidity_sensors:
        raise ConfigError(
            f"{path}.humidity_sensors are required when humidity control is enabled"
        )
    target = _optional_float(
        room.get("humidity_target"),
        f"{path}.humidity_target",
    )
    if target is None:
        raise ConfigError(
            f"{path}.humidity_target is required when humidity control is enabled"
        )
    if not 0.0 <= target <= 100.0:
        raise ConfigError(f"{path}.humidity_target must be between 0 and 100")
    actuator = HumidityActuatorConfig(
        entity_id=_entity(
            room.get("humidity_actuator"),
            f"{path}.humidity_actuator",
            ("switch", "humidifier"),
        )
    )
    return HumidityConfig(True, mode, target, actuator)


def parse_options(raw: Any) -> AppConfig:
    root = _as_mapping(raw, "options")

    hysteresis = _float(root.get("hysteresis", 0.5), "hysteresis")
    if not 0.0 <= hysteresis <= 5.0:
        raise ConfigError("hysteresis must be between 0 and 5")

    humidity_hysteresis = _float(
        root.get("humidity_hysteresis", 3.0),
        "humidity_hysteresis",
    )
    if not 0.0 <= humidity_hysteresis <= 25.0:
        raise ConfigError("humidity_hysteresis must be between 0 and 25")

    global_config = GlobalConfig(
        hysteresis=hysteresis,
        humidity_hysteresis=humidity_hysteresis,
        night_mode=_entity(
            root.get("night_mode"),
            "night_mode",
            ("input_boolean", "binary_sensor"),
            required=False,
        ),
        we_at_home=_entity(
            root.get("we_at_home"),
            "we_at_home",
            ("input_boolean", "binary_sensor"),
            required=False,
        ),
    )

    heat_default = _float(
        root.get("heat_threshold_default", 12.0),
        "heat_threshold_default",
    )
    cool_default = _float(
        root.get("cool_threshold_default", 20.0),
        "cool_threshold_default",
    )
    if heat_default >= cool_default:
        raise ConfigError(
            "heat_threshold_default must be lower than cool_threshold_default"
        )

    ac_min_outdoor_temperature = _float(
        root.get("ac_min_outdoor_temperature", -10.0),
        "ac_min_outdoor_temperature",
    )
    if not -50.0 <= ac_min_outdoor_temperature <= 20.0:
        raise ConfigError(
            "ac_min_outdoor_temperature must be between -50 and 20"
        )

    outdoor = OutdoorConfig(
        heat_threshold_default=heat_default,
        cool_threshold_default=cool_default,
        temperature_sources=_entity_list(
            root.get("outdoor_temperature_sources", ""),
            "outdoor_temperature_sources",
            ("sensor", "weather"),
        ),
        humidity_sources=_entity_list(
            root.get("outdoor_humidity_sources", ""),
            "outdoor_humidity_sources",
            ("sensor", "weather"),
        ),
    )

    rooms: list[RoomConfig] = []
    room_ids: set[str] = set()
    for index, item in enumerate(_as_list(root.get("rooms", []), "rooms")):
        path = f"rooms[{index}]"
        room = _as_mapping(item, path)

        room_id = str(room.get("id", "")).strip().lower()
        if not ROOM_ID_RE.fullmatch(room_id):
            raise ConfigError(f"{path}.id must match {ROOM_ID_RE.pattern}")
        if room_id in room_ids:
            raise ConfigError(f"{path}.id duplicates {room_id}")
        room_ids.add(room_id)

        name = str(room.get("name", "")).strip()
        if not name:
            raise ConfigError(f"{path}.name is required")

        temperature_sensors = _entity_list(
            room.get("temperature_sensors"),
            f"{path}.temperature_sensors",
            ("sensor",),
            required=True,
        )
        humidity_sensors = _entity_list(
            room.get("humidity_sensors", ""),
            f"{path}.humidity_sensors",
            ("sensor",),
        )
        window_sensors = _entity_list(
            room.get("window_sensors", ""),
            f"{path}.window_sensors",
            ("binary_sensor",),
        )

        rooms.append(
            RoomConfig(
                room_id=room_id,
                name=name,
                temperature_sensors=temperature_sensors,
                humidity_sensors=humidity_sensors,
                window_sensors=window_sensors,
                targets=_room_targets(room, path),
                devices=_room_devices(
                    room,
                    path,
                    ac_min_outdoor_temperature=ac_min_outdoor_temperature,
                ),
                humidity=_room_humidity(room, path, humidity_sensors),
            )
        )

    actuator_owners: dict[str, str] = {}
    for room in rooms:
        for device in room.devices:
            owner = f"room:{room.room_id}:thermal"
            previous = actuator_owners.get(device.entity_id)
            if previous is not None:
                raise ConfigError(
                    f"actuator {device.entity_id} is configured twice: "
                    f"{previous}, {owner}"
                )
            actuator_owners[device.entity_id] = owner

        if room.humidity.actuator is not None:
            entity_id = room.humidity.actuator.entity_id
            owner = f"room:{room.room_id}:humidity"
            previous = actuator_owners.get(entity_id)
            if previous is not None:
                raise ConfigError(
                    f"actuator {entity_id} is configured twice: "
                    f"{previous}, {owner}"
                )
            actuator_owners[entity_id] = owner

    log_level = str(root.get("log_level", "info")).strip().lower()
    if log_level not in {"debug", "info", "warning", "error"}:
        raise ConfigError("log_level must be debug, info, warning or error")

    return AppConfig(
        global_config=global_config,
        outdoor=outdoor,
        rooms=tuple(rooms),
        telemetry_enabled=bool(root.get("telemetry_enabled", False)),
        log_level=log_level,
    )


def configured_entity_ids(config: AppConfig) -> frozenset[str]:
    """Return every Home Assistant entity referenced by App configuration."""
    result: set[str] = set()

    if config.global_config.night_mode:
        result.add(config.global_config.night_mode)
    if config.global_config.we_at_home:
        result.add(config.global_config.we_at_home)

    result.update(config.outdoor.temperature_sources)
    result.update(config.outdoor.humidity_sources)

    for room in config.rooms:
        result.update(room.temperature_sensors)
        result.update(room.humidity_sensors)
        result.update(room.window_sensors)
        for device in room.devices:
            result.add(device.entity_id)
        if room.humidity.actuator is not None:
            result.add(room.humidity.actuator.entity_id)

    return frozenset(result)
