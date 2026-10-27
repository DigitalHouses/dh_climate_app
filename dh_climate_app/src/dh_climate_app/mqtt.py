from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import json
import logging
from typing import Callable, Iterable

import paho.mqtt.client as mqtt

from .config import RoomConfig
from .core import DeviceClass
from .demand import Demand
from .health import ClimateHealth
from .persistence import GLOBAL_TUNING_SEEDS
from .discovery import (
    LEGACY_OUTDOOR_ATTRIBUTES_TOPIC,
    LEGACY_WEATHER_ATTRIBUTES_TOPIC,
    OUTDOOR_RAW_TEMPERATURE_TOPIC,
    OUTDOOR_TEMPERATURE_ATTRIBUTES_TOPIC,
    SEASON_AVAILABILITY_TOPIC,
    SYSTEM_AVAILABILITY_TOPIC,
    SYSTEM_PROBLEM_ATTRIBUTES_TOPIC,
    SYSTEM_PROBLEM_TOPIC,
    SYSTEM_EVENT_TOPIC,
    diagnostic_discovery_payloads,
    demand_base,
    demand_discovery_payloads,
    demand_object_id,
    global_climate_health_discovery_payloads,
    global_tuning_discovery_payloads,
    room_health_discovery_payload,
    slow_target_discovery_payload,
    outdoor_discovery_payloads,
    outdoor_state_topics,
    room_climate_discovery_payload,
    room_climate_discovery_topic,
    room_climate_state_topics,
    ROOM_TARGET_KEYS,
    room_humidity_discovery_payload,
    room_humidity_discovery_topic,
    room_profile_discovery_topic,
    room_profile_state_topic,
    room_target_discovery_payload,
    room_target_discovery_topic,
    room_target_state_topics,
    room_humidity_state_topics,
    problem_state_payload,
    season_discovery_payload,
    season_discovery_topic,
    season_state_topics,
    system_state_payload,
    weather_discovery_payloads,
    weather_state_topics,
)
from .humidity import HumidityState
from .outdoor import OutdoorState
from .rooms import RoomState
from .weather import WeatherState


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MqttCommand:
    scope: str
    command: str
    payload: str
    room_id: str | None = None


class MqttBridge:
    """Small MQTT adapter with retained-state deduplication."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.loop = loop
        self._last_payloads: dict[str, str] = {}
        self._retained_payloads: dict[str, str] = {}
        self._subscriptions: set[str] = set()
        self._message_handler: Callable[[str, str, bool], None] | None = None
        self._connected_once = False

        try:
            self.client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id="dh_climate_app",
            )
        except (AttributeError, TypeError):
            self.client = mqtt.Client(client_id="dh_climate_app")

        if username:
            self.client.username_pw_set(username, password)
        self.client.will_set(
            SYSTEM_AVAILABILITY_TOPIC,
            payload="offline",
            qos=1,
            retain=True,
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def set_message_handler(
        self,
        handler: Callable[[str, str, bool], None],
    ) -> None:
        self._message_handler = handler

    def start(self) -> None:
        self.client.connect(self.host, self.port, keepalive=60)
        self.client.loop_start()

    def stop(self) -> None:
        try:
            self.publish(SYSTEM_AVAILABILITY_TOPIC, "offline", retain=True, force=True)
        finally:
            self.client.loop_stop()
            self.client.disconnect()

    def subscribe(self, topic: str) -> None:
        self._subscriptions.add(topic)
        self.client.subscribe(topic, qos=1)

    def publish(
        self,
        topic: str,
        payload: str,
        *,
        retain: bool,
        force: bool = False,
    ) -> bool:
        if not force and self._last_payloads.get(topic) == payload:
            return False
        info = self.client.publish(topic, payload=payload, qos=1, retain=retain)
        info.wait_for_publish(timeout=5.0)
        self._last_payloads[topic] = payload
        if retain:
            self._retained_payloads[topic] = payload
        return True

    def _restore_retained_after_reconnect(self) -> None:
        payloads = dict(self._retained_payloads)
        payloads[SYSTEM_AVAILABILITY_TOPIC] = "online"
        LOGGER.info(
            "MQTT reconnected; restoring %s retained topics",
            len(payloads),
        )
        for topic, payload in payloads.items():
            self.publish(topic, payload, retain=True, force=True)

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: object,
        reason_code: object,
        properties: object = None,
    ) -> None:
        LOGGER.info("MQTT connected: %s", reason_code)
        for topic in tuple(self._subscriptions):
            client.subscribe(topic, qos=1)

        if self._connected_once:
            self.loop.call_soon_threadsafe(
                self._restore_retained_after_reconnect
            )
        else:
            self._connected_once = True

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        if self._message_handler is None:
            return
        try:
            payload = message.payload.decode("utf-8")
        except UnicodeDecodeError:
            LOGGER.warning("Ignored non-UTF8 MQTT command on %s", message.topic)
            return
        retained = bool(getattr(message, "retain", False))
        self.loop.call_soon_threadsafe(
            self._message_handler,
            str(message.topic),
            payload,
            retained,
        )


class ClimateMqttFacade:
    def __init__(
        self,
        *,
        bridge: MqttBridge,
        app_version: str,
        started_at,
        rooms: Iterable[RoomConfig],
        command_queue: asyncio.Queue[MqttCommand],
        weather_enabled: bool = False,
        actual_demand_sources: dict[str, str] | None = None,
    ) -> None:
        self.bridge = bridge
        self.app_version = app_version
        self.started_at = started_at
        self.rooms = {room.room_id: room for room in rooms}
        self.command_queue = command_queue
        self.weather_enabled = bool(weather_enabled)
        self.actual_demand_sources = dict(actual_demand_sources or {})
        self._last_raw_temperature_publish_at = None
        self.bridge.set_message_handler(self._on_message)

    def start(self) -> None:
        self.bridge.start()
        self.bridge.subscribe("DigitalHouses/Global/dh_climate_app/season/set/+")
        self.bridge.subscribe("DigitalHouses/Global/dh_climate_app/system/set/+")
        self.bridge.subscribe("DigitalHouses/Global/dh_climate_app/settings/set/+")
        self.bridge.subscribe("DigitalHouses/Global/dh_climate_app/rooms/+/slow_targets/set/+")
        self.bridge.subscribe(
            "DigitalHouses/Global/dh_climate_app/rooms/+/climate/set/+"
        )
        self.bridge.subscribe(
            "DigitalHouses/Global/dh_climate_app/rooms/+/humidity/set/+"
        )
        self.bridge.subscribe(
            "DigitalHouses/Global/dh_climate_app/rooms/+/targets/set/+"
        )
        self.publish_system_discovery()
        self.publish_demand_discovery()
        self.bridge.publish(
            SYSTEM_AVAILABILITY_TOPIC,
            "online",
            retain=True,
            force=True,
        )

    def stop(self) -> None:
        self.bridge.stop()

    def publish_system_discovery(self) -> None:
        self.bridge.publish(
            season_discovery_topic(),
            json.dumps(
                season_discovery_payload(self.app_version),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            retain=True,
            force=True,
        )
        for _, (topic, payload) in diagnostic_discovery_payloads(
            self.app_version
        ).items():
            self.bridge.publish(
                topic,
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                retain=True,
                force=True,
            )

        for payload_group in (
            global_climate_health_discovery_payloads(self.app_version),
            global_tuning_discovery_payloads(self.app_version),
        ):
            for topic, payload in payload_group.values():
                self.bridge.publish(
                    topic,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    retain=True, force=True,
                )

        for _, (topic, payload) in outdoor_discovery_payloads(
            self.app_version
        ).items():
            self.bridge.publish(
                topic,
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                retain=True,
                force=True,
            )

        for _, (topic, payload) in weather_discovery_payloads(
            self.app_version
        ).items():
            self.bridge.publish(
                topic,
                (
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    if self.weather_enabled
                    else ""
                ),
                retain=True,
                force=True,
            )

        # 0.1.20 and earlier attached multiple entities to shared dynamic
        # attribute topics containing observed_at. Clear those retained payloads
        # after publishing the new split Discovery contract.
        self.bridge.publish(
            LEGACY_OUTDOOR_ATTRIBUTES_TOPIC,
            "",
            retain=True,
            force=True,
        )
        self.bridge.publish(
            OUTDOOR_TEMPERATURE_ATTRIBUTES_TOPIC,
            "",
            retain=True,
            force=True,
        )
        self.bridge.publish(
            LEGACY_WEATHER_ATTRIBUTES_TOPIC,
            "",
            retain=True,
            force=True,
        )

        self.bridge.publish(
            "DigitalHouses/Global/dh_climate_app/state",
            system_state_payload(
                app_version=self.app_version,
                started_at=self.started_at,
            ),
            retain=True,
            force=True,
        )

    def publish_demand_discovery(self) -> None:
        for (layer, direction, kind), (topic, payload) in demand_discovery_payloads(
            self.app_version,
            actual_sources=self.actual_demand_sources,
        ).items():
            self.bridge.publish(
                topic, json.dumps(payload, ensure_ascii=False, sort_keys=True),
                retain=True, force=True,
            )
        # An ACTUAL source removed from YAML must not leave an orphan entity.
        for direction in ("heat", "cool"):
            if not self.actual_demand_sources.get(direction):
                object_id = demand_object_id("actual", direction)
                self.bridge.publish(
                    f"homeassistant/binary_sensor/{object_id}/config",
                    "", retain=True, force=True,
                )

    def set_demand_available(self, available: bool) -> None:
        # HA disconnected: retained ON/OFF must not be mistaken for truth.
        for layer in ("room", "device", "actual"):
            for direction in ("heat", "cool"):
                if layer == "actual" and not self.actual_demand_sources.get(direction):
                    continue
                base = demand_base(layer, direction)
                self.bridge.publish(
                    f"{base}/availability",
                    "online" if available else "offline", retain=True,
                )
                if layer != "actual":
                    self.bridge.publish(
                        f"{base}/count_availability",
                        "online" if available else "offline", retain=True,
                    )

    def publish_demand(
        self, layer: str, direction: str, demand: Demand | bool | None,
    ) -> None:
        base = demand_base(layer, direction)
        if layer == "actual" and not self.actual_demand_sources.get(direction):
            return
        if layer == "actual":
            active = demand
            count = None
            members = ()
        else:
            if not isinstance(demand, Demand):
                raise TypeError("room/device demand must be Demand")
            active = demand.active
            count = demand.count
            members = demand.members
        if active is not None:
            self.bridge.publish(
                f"{base}/state", "ON" if active else "OFF", retain=True,
            )
        self.bridge.publish(
            f"{base}/availability",
            "online" if active is not None else "offline", retain=True,
        )
        if layer == "actual":
            return
        if count is not None:
            self.bridge.publish(
                f"{base}/attributes",
                json.dumps(
                    {"rooms" if layer == "room" else "devices": list(members)},
                    ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                ), retain=True,
            )
            self.bridge.publish(f"{base}/count", str(count), retain=True)
        self.bridge.publish(
            f"{base}/count_availability",
            "online" if count is not None else "offline", retain=True,
        )

    def publish_season(self, state: OutdoorState) -> int:
        count = 0
        for topic, payload in season_state_topics(state).items():
            count += int(self.bridge.publish(topic, payload, retain=True))

        for topic, payload in outdoor_state_topics(state).items():
            if topic == OUTDOOR_RAW_TEMPERATURE_TOPIC:
                last = self._last_raw_temperature_publish_at
                if (
                    last is not None
                    and state.observed_at < last + timedelta(minutes=1)
                ):
                    continue
                self._last_raw_temperature_publish_at = state.observed_at
            count += int(self.bridge.publish(topic, payload, retain=True))
        return count

    def publish_weather(self, state: WeatherState) -> int:
        count = 0
        for topic, payload in weather_state_topics(state).items():
            count += int(self.bridge.publish(topic, payload, retain=True))
        return count

    def publish_event(self, payload: dict[str, object]) -> bool:
        return self.bridge.publish(
            SYSTEM_EVENT_TOPIC,
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            retain=False,
            force=True,
        )

    def publish_room(
        self,
        state: RoomState,
        *,
        published_profile: str,
        published_target: float | None,
        profile_targets: dict[str, float | None],
    ) -> int:
        room = self.rooms[state.room_id]
        health_topic, health_payload = room_health_discovery_payload(
            room, self.app_version,
        )
        self.bridge.publish(
            health_topic, json.dumps(health_payload, ensure_ascii=False, sort_keys=True),
            retain=True,
        )
        climate_state = room_climate_state_topics(
            state,
            published_profile=published_profile,
            published_target=published_target,
        )

        # Home Assistant resets MQTT Climate preset_mode to "none" whenever
        # Discovery changes. Prime the new season-scoped preset topic before
        # publishing the season-specific Discovery payload. Because the topic
        # changes across HEAT/COOL/OFF, HA must resubscribe and immediately
        # receives this retained authoritative preset.
        profile_topic = room_profile_state_topic(
            room.room_id,
            state.season.value,
        )
        count = int(
            self.bridge.publish(
                profile_topic,
                climate_state[profile_topic],
                retain=True,
            )
        )

        count += int(
            self.bridge.publish(
                room_climate_discovery_topic(room.room_id),
                json.dumps(
                    room_climate_discovery_payload(
                        room,
                        state,
                        self.app_version,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                retain=True,
            )
        )

        # 0.1.17 used one shared preset state topic. It is no longer referenced
        # after the seasonal-topic migration, so clear the retained value.
        count += int(
            self.bridge.publish(
                f"DigitalHouses/Global/dh_climate_app/rooms/{room.room_id}/climate/profile",
                "",
                retain=True,
            )
        )

        # 0.1.4 exposed a temporary Profile select. Delete its retained
        # Discovery payload so upgrades remove that entity from Home Assistant.
        count += int(
            self.bridge.publish(
                room_profile_discovery_topic(room.room_id),
                "",
                retain=True,
            )
        )

        for target_key, name in ROOM_TARGET_KEYS:
            count += int(
                self.bridge.publish(
                    room_target_discovery_topic(room.room_id, target_key),
                    json.dumps(
                        room_target_discovery_payload(
                            room,
                            self.app_version,
                            target_key=target_key,
                            name=name,
                        ),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    retain=True,
                )
            )

        for topic, payload in climate_state.items():
            count += int(self.bridge.publish(topic, payload, retain=True))
        for topic, payload in room_target_state_topics(
            room.room_id,
            profile_targets,
        ).items():
            count += int(self.bridge.publish(topic, payload, retain=True))
        return count

    def publish_health(self, health: ClimateHealth) -> int:
        count = 0
        base = "DigitalHouses/Global/dh_climate_app"
        for key, status in (
            ("global_health", health.global_state),
            ("climate_health", health.climate_state),
        ):
            count += int(self.bridge.publish(
                f"{base}/{key}", status, retain=True,
            ))
        for room_id, status in health.rooms.items():
            count += int(self.bridge.publish(
                f"{base}/rooms/{room_id}/health", status, retain=True,
            ))
        return count

    def publish_tuning(self, tuning: dict[str, float]) -> None:
        base = "DigitalHouses/Global/dh_climate_app/settings"
        for key, value in tuning.items():
            if key in GLOBAL_TUNING_SEEDS:
                self.bridge.publish(f"{base}/{key}", str(value), retain=True)

    def publish_slow_targets(
        self, room_id: str, targets: dict[str, float | None],
    ) -> None:
        room = self.rooms[room_id]
        needs_target = any(
            d.device_class is DeviceClass.SLOW
            and (d.control == "device" or d.temperature_sensor is not None)
            for d in room.devices
        )
        if not needs_target:
            return
        for profile in ("day", "night", "away"):
            topic, payload = slow_target_discovery_payload(
                room, profile, self.app_version,
            )
            self.bridge.publish(
                topic, json.dumps(payload, ensure_ascii=False, sort_keys=True),
                retain=True,
            )
            value = targets.get(profile)
            if value is not None:
                self.bridge.publish(
                    f"DigitalHouses/Global/dh_climate_app/rooms/"
                    f"{room_id}/slow_targets/{profile}",
                    str(value), retain=True,
                )

    def publish_humidity(self, state: HumidityState) -> int:
        room = self.rooms[state.room_id]
        count = int(
            self.bridge.publish(
                room_humidity_discovery_topic(room.room_id),
                json.dumps(
                    room_humidity_discovery_payload(
                        room,
                        self.app_version,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                retain=True,
            )
        )
        for topic, payload in room_humidity_state_topics(state).items():
            count += int(self.bridge.publish(topic, payload, retain=True))
        return count

    def publish_problems(self, problems: tuple[object, ...]) -> None:
        state, attrs = problem_state_payload(problems)
        self.bridge.publish(SYSTEM_PROBLEM_TOPIC, state, retain=True)
        self.bridge.publish(
            SYSTEM_PROBLEM_ATTRIBUTES_TOPIC,
            attrs,
            retain=True,
        )

    def set_season_available(self, available: bool) -> None:
        self.bridge.publish(
            SEASON_AVAILABILITY_TOPIC,
            "online" if available else "offline",
            retain=True,
        )

    def set_rooms_available(self, available: bool) -> None:
        payload = "online" if available else "offline"
        for room_id, room in self.rooms.items():
            base = f"DigitalHouses/Global/dh_climate_app/rooms/{room_id}"
            self.bridge.publish(
                f"{base}/climate/availability",
                payload,
                retain=True,
            )
            if room.humidity.enabled:
                self.bridge.publish(
                    f"{base}/humidity/availability",
                    payload,
                    retain=True,
                )

    def _on_message(self, topic: str, payload: str, retained: bool) -> None:
        if retained:
            return

        prefix = "DigitalHouses/Global/dh_climate_app/"
        if not topic.startswith(prefix):
            return
        suffix = topic[len(prefix):]
        parts = suffix.split("/")

        if len(parts) == 3 and parts[:2] == ["season", "set"]:
            self.command_queue.put_nowait(
                MqttCommand(
                    scope="season",
                    command=parts[2],
                    payload=payload.strip(),
                )
            )
            return

        if len(parts) == 3 and parts[:2] == ["settings", "set"]:
            self.command_queue.put_nowait(
                MqttCommand(scope="tuning", command=parts[2], payload=payload.strip())
            )
            return

        if len(parts) == 3 and parts[:2] == ["system", "set"]:
            self.command_queue.put_nowait(
                MqttCommand(
                    scope="system",
                    command=parts[2],
                    payload=payload.strip(),
                )
            )
            return

        if len(parts) == 5 and parts[0] == "rooms":
            room_id = parts[1]
            if room_id not in self.rooms or parts[3] != "set":
                return
            if parts[2] == "climate":
                scope = "room"
            elif parts[2] == "humidity":
                scope = "humidity"
            elif parts[2] == "targets":
                scope = "target"
            elif parts[2] == "slow_targets":
                scope = "slow_target"
            else:
                return
            self.command_queue.put_nowait(
                MqttCommand(
                    scope=scope,
                    room_id=room_id,
                    command=parts[4],
                    payload=payload.strip(),
                )
            )
