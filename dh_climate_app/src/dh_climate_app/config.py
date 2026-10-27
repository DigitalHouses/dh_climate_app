from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

from .core import DeviceClass, Profile

# Начальные значения применяются только при отсутствии записей в SQLite.
SEASON_MIN_TEMP = 5.0
SEASON_MAX_TEMP = 25.0
DEFAULT_HEAT_THRESHOLD = 10.0
DEFAULT_COOL_THRESHOLD = 25.0
DEFAULT_AC_MIN_OUTDOOR_TEMPERATURE = -10.0
DEFAULT_OUTDOOR_EMA_MINUTES = 20.0
DEFAULT_HUMIDITY_TARGET = 50.0
ROOM_TARGET_INITIAL = {
    "heat_day": 23.0,
    "heat_night": 23.0,
    "heat_away": 18.0,
    "heat_antifreeze": 10.0,
    "cool_day": 25.0,
    "cool_night": 24.0,
    "cool_away": 30.0,
}

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
    temperature_ema_minutes: float
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
    control: str = "app"
    actuator: str | None = None
    temperature_sensor: str | None = None


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
    # Старые значения из YAML служат только для начального заполнения SQLite.
    heat = {
        Profile.DAY: _float(room.get("heat_day", ROOM_TARGET_INITIAL["heat_day"]), f"{path}.heat_day"),
        Profile.NIGHT: _float(room.get("heat_night", ROOM_TARGET_INITIAL["heat_night"]), f"{path}.heat_night"),
        Profile.AWAY: _float(room.get("heat_away", ROOM_TARGET_INITIAL["heat_away"]), f"{path}.heat_away"),
        Profile.ANTIFREEZE: _float(
            room.get("heat_antifreeze", ROOM_TARGET_INITIAL["heat_antifreeze"]),
            f"{path}.heat_antifreeze",
        ),
    }
    cool = {
        Profile.DAY: _float(room.get("cool_day", ROOM_TARGET_INITIAL["cool_day"]), f"{path}.cool_day"),
        Profile.NIGHT: _float(room.get("cool_night", ROOM_TARGET_INITIAL["cool_night"]), f"{path}.cool_night"),
        Profile.AWAY: _float(room.get("cool_away", ROOM_TARGET_INITIAL["cool_away"]), f"{path}.cool_away"),
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
    """Strict room-local topology. One entry is one physical owner.

    Reversible climate uses a single entry with role=fast_heat and
    reversible=true, avoiding two conflicting commands to the same entity.
    """
    entries = _as_list(room.get("devices", []), f"{path}.devices")
    devices: list[DeviceConfig] = []
    seen: set[str] = set()
    for index, raw in enumerate(entries):
        device_path = f"{path}.devices[{index}]"
        entry = _as_mapping(raw, device_path)
        unknown = set(entry) - {
            "entity", "role", "control", "actuator", "temperature_sensor",
            "window_off", "reversible",
        }
        if unknown:
            raise ConfigError(f"{device_path}: unknown keys: {sorted(unknown)}")
        entity_id = _entity(
            entry.get("entity"), f"{device_path}.entity", ("switch", "climate")
        )
        if entity_id in seen:
            raise ConfigError(f"{device_path}: duplicate physical actuator {entity_id}")
        seen.add(entity_id)
        domain = entity_id.split(".", 1)[0]
        role = str(entry.get("role", "")).strip()
        control = str(entry.get("control", "")).strip()
        if role not in {"slow_heat", "fast_heat", "fast_cool"}:
            raise ConfigError(f"{device_path}.role must be slow_heat, fast_heat or fast_cool")
        if control not in {"app", "device"}:
            raise ConfigError(f"{device_path}.control must be app or device")
        if control == "device" and domain != "climate":
            raise ConfigError(f"{device_path}: device control requires climate.*")
        if role == "slow_heat" and domain == "climate" and control != "device":
            raise ConfigError(
                f"{device_path}: slow_heat climate requires control=device"
            )

        actuator = entry.get("actuator") or None
        if actuator is not None:
            if actuator not in {"normal_open", "normal_closed"}:
                raise ConfigError(f"{device_path}.actuator must be normal_open or normal_closed")
            if domain != "switch" or control != "app":
                raise ConfigError(f"{device_path}: actuator polarity requires app-controlled switch")
        if role == "slow_heat" and domain == "switch" and actuator is None:
            raise ConfigError(
                f"{device_path}: slow_heat switch requires explicit actuator polarity"
            )

        temperature_sensor = _entity(
            entry.get("temperature_sensor"),
            f"{device_path}.temperature_sensor",
            ("sensor",),
            required=False,
        ) or None
        if temperature_sensor and not (
            role == "slow_heat" and domain == "switch" and control == "app"
        ):
            raise ConfigError(
                f"{device_path}: external screed sensor is only for slow_heat switch/app"
            )
        reversible = entry.get("reversible", False)
        if type(reversible) is not bool:
            raise ConfigError(f"{device_path}.reversible must be boolean")
        if reversible and not (role == "fast_heat" and domain == "climate"):
            raise ConfigError(
                f"{device_path}: reversible requires fast_heat climate"
            )
        window_off = entry.get("window_off", False)
        if type(window_off) is not bool:
            raise ConfigError(f"{device_path}.window_off must be boolean")
        device_class = (
            DeviceClass.SLOW if role == "slow_heat" else DeviceClass.FAST
        )
        function = (
            "heat_cool" if reversible else
            "cool" if role == "fast_cool" else "heat"
        )
        devices.append(
            DeviceConfig(
                entity_id=entity_id,
                device_class=device_class,
                function=function,
                target_temperature=None,
                window_policy="turn_off" if window_off else "ignore",
                min_heating_outdoor_temperature=(
                    ac_min_outdoor_temperature if reversible else None
                ),
                control=control,
                actuator=actuator,
                temperature_sensor=temperature_sensor,
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
        target = DEFAULT_HUMIDITY_TARGET
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
    """Only the target Supervisor contract; legacy options are not migrated."""
    root = _as_mapping(raw, "options")
    allowed = {
        "night_mode", "we_at_home", "outdoor", "rooms",
        "telemetry_enabled", "log_level",
    }
    unknown = set(root) - allowed
    if unknown:
        raise ConfigError(f"options: obsolete or unknown keys: {sorted(unknown)}")

    global_config = GlobalConfig(
        hysteresis=0.5,  # Persisted global tuning supersedes this initial seed.
        humidity_hysteresis=3.0,
        night_mode=_entity(
            root.get("night_mode"), "night_mode",
            ("input_boolean", "binary_sensor"), required=False,
        ),
        we_at_home=_entity(
            root.get("we_at_home"), "we_at_home",
            ("input_boolean", "binary_sensor"), required=False,
        ),
    )

    outdoor_raw = _as_mapping(root.get("outdoor", {}), "outdoor")
    if set(outdoor_raw) - {"temperature_sources", "humidity_sources"}:
        raise ConfigError("outdoor: unknown keys")
    outdoor = OutdoorConfig(
        heat_threshold_default=DEFAULT_HEAT_THRESHOLD,
        cool_threshold_default=DEFAULT_COOL_THRESHOLD,
        temperature_ema_minutes=DEFAULT_OUTDOOR_EMA_MINUTES,
        temperature_sources=_entity_list(
            _as_list(outdoor_raw.get("temperature_sources", []), "outdoor.temperature_sources"),
            "outdoor.temperature_sources", ("sensor", "weather"),
        ),
        humidity_sources=_entity_list(
            _as_list(outdoor_raw.get("humidity_sources", []), "outdoor.humidity_sources"),
            "outdoor.humidity_sources", ("sensor", "weather"),
        ),
    )
    rooms: list[RoomConfig] = []
    room_ids: set[str] = set()
    for index, item in enumerate(_as_list(root.get("rooms", []), "rooms")):
        path = f"rooms[{index}]"
        room = _as_mapping(item, path)
        allowed_room = {
            "id", "name", "temperature_sensors", "humidity_sensors",
            "window_sensors", "humidity_mode", "humidity_actuator", "devices",
        }
        unknown_room = set(room) - allowed_room
        if unknown_room:
            raise ConfigError(f"{path}: obsolete or unknown keys: {sorted(unknown_room)}")
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
            _as_list(room.get("temperature_sensors"), f"{path}.temperature_sensors"),
            f"{path}.temperature_sensors", ("sensor",), required=True,
        )
        humidity_sensors = _entity_list(
            _as_list(room.get("humidity_sensors", []), f"{path}.humidity_sensors"),
            f"{path}.humidity_sensors", ("sensor",),
        )
        window_sensors = _entity_list(
            _as_list(room.get("window_sensors", []), f"{path}.window_sensors"),
            f"{path}.window_sensors", ("binary_sensor",),
        )
        rooms.append(
            RoomConfig(
                room_id=room_id,
                name=name,
                temperature_sensors=temperature_sensors,
                humidity_sensors=humidity_sensors,
                window_sensors=window_sensors,
                targets=_room_targets({}, path),
                devices=_room_devices(
                    room, path,
                    ac_min_outdoor_temperature=DEFAULT_AC_MIN_OUTDOOR_TEMPERATURE,
                ),
                humidity=_room_humidity(room, path, humidity_sensors),
            )
        )

    owners: dict[str, str] = {}
    for room in rooms:
        for device in room.devices:
            entities = (device.entity_id,)
            if device.temperature_sensor in entities:
                raise ConfigError("sensor cannot be its own actuator")
            for entity_id in entities:
                if entity_id in owners:
                    raise ConfigError(
                        f"actuator {entity_id} owned by both {owners[entity_id]} "
                        f"and room:{room.room_id}"
                    )
                owners[entity_id] = f"room:{room.room_id}"
        if room.humidity.actuator is not None:
            entity_id = room.humidity.actuator.entity_id
            if entity_id in owners:
                raise ConfigError(
                    f"actuator {entity_id} owned by both {owners[entity_id]} "
                    f"and room:{room.room_id}:humidity"
                )
            owners[entity_id] = f"room:{room.room_id}:humidity"

    log_level = str(root.get("log_level", "info")).strip().lower()
    if log_level not in {"debug", "info", "warning", "error"}:
        raise ConfigError("log_level must be debug, info, warning or error")
    telemetry_enabled = root.get("telemetry_enabled", False)
    if type(telemetry_enabled) is not bool:
        raise ConfigError("telemetry_enabled must be boolean")
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

    result.update(config.outdoor.temperature_sources)
    result.update(config.outdoor.humidity_sources)

    for room in config.rooms:
        result.update(room.temperature_sensors)
        result.update(room.humidity_sensors)
        result.update(room.window_sensors)
        for device in room.devices:
            result.add(device.entity_id)
            if device.temperature_sensor:
                result.add(device.temperature_sensor)
        if room.humidity.actuator is not None:
            result.add(room.humidity.actuator.entity_id)

    return frozenset(result)
