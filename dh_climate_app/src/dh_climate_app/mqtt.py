from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
from typing import Callable, Iterable

import paho.mqtt.client as mqtt

from .config import RoomConfig
from .discovery import (
    SEASON_AVAILABILITY_TOPIC,
    SYSTEM_AVAILABILITY_TOPIC,
    SYSTEM_PROBLEM_ATTRIBUTES_TOPIC,
    SYSTEM_PROBLEM_TOPIC,
    diagnostic_discovery_payloads,
    room_climate_discovery_payload,
    room_climate_discovery_topic,
    room_climate_state_topics,
    room_humidity_discovery_payload,
    room_humidity_discovery_topic,
    room_profile_discovery_payload,
    room_profile_discovery_topic,
    room_humidity_state_topics,
    problem_state_payload,
    season_discovery_payload,
    season_discovery_topic,
    season_state_topics,
    system_state_payload,
)
from .humidity import HumidityState
from .outdoor import OutdoorState
from .rooms import RoomState


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
    ) -> None:
        self.bridge = bridge
        self.app_version = app_version
        self.started_at = started_at
        self.rooms = {room.room_id: room for room in rooms}
        self.command_queue = command_queue
        self.bridge.set_message_handler(self._on_message)

    def start(self) -> None:
        self.bridge.start()
        self.bridge.subscribe("DigitalHouses/Global/dh_climate_app/season/set/+")
        self.bridge.subscribe("DigitalHouses/Global/dh_climate_app/system/set/+")
        self.bridge.subscribe(
            "DigitalHouses/Global/dh_climate_app/rooms/+/climate/set/+"
        )
        self.bridge.subscribe(
            "DigitalHouses/Global/dh_climate_app/rooms/+/humidity/set/+"
        )
        self.publish_system_discovery()
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
        self.bridge.publish(
            "DigitalHouses/Global/dh_climate_app/state",
            system_state_payload(
                app_version=self.app_version,
                started_at=self.started_at,
            ),
            retain=True,
            force=True,
        )

    def publish_season(self, state: OutdoorState) -> int:
        count = 0
        for topic, payload in season_state_topics(state).items():
            count += int(self.bridge.publish(topic, payload, retain=True))
        return count

    def publish_room(
        self,
        state: RoomState,
        *,
        published_profile: str,
        published_target: float | None,
    ) -> int:
        room = self.rooms[state.room_id]
        count = int(
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
        count += int(
            self.bridge.publish(
                room_profile_discovery_topic(room.room_id),
                json.dumps(
                    room_profile_discovery_payload(
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
        for topic, payload in room_climate_state_topics(
            state,
            published_profile=published_profile,
            published_target=published_target,
        ).items():
            count += int(self.bridge.publish(topic, payload, retain=True))
        return count

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
