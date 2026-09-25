from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

import paho.mqtt.client as mqtt

from .discovery import (
    SYSTEM_AVAILABILITY_TOPIC,
    diagnostic_discovery_payloads,
    season_discovery_payload,
    season_discovery_topic,
    season_state_topics,
    system_state_payload,
)
from .outdoor import OutdoorState


LOGGER = logging.getLogger(__name__)


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
        self._subscriptions: set[str] = set()
        self._message_handler: Callable[[str, str, bool], None] | None = None

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
        return True

    def _on_connect(self, client: mqtt.Client, userdata: object, flags: object, reason_code: object, properties: object = None) -> None:
        LOGGER.info("MQTT connected: %s", reason_code)
        for topic in self._subscriptions:
            client.subscribe(topic, qos=1)

    def _on_message(self, client: mqtt.Client, userdata: object, message: mqtt.MQTTMessage) -> None:
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


class SeasonMqttFacade:
    def __init__(
        self,
        *,
        bridge: MqttBridge,
        app_version: str,
        started_at,
        command_queue: asyncio.Queue[tuple[str, str]],
    ) -> None:
        self.bridge = bridge
        self.app_version = app_version
        self.started_at = started_at
        self.command_queue = command_queue
        self.bridge.set_message_handler(self._on_message)

    def start(self) -> None:
        self.bridge.start()
        self.bridge.subscribe("DigitalHouses/Global/dh_climate_app/season/set/+")
        self.publish_discovery()
        self.bridge.publish(
            SYSTEM_AVAILABILITY_TOPIC,
            "online",
            retain=True,
            force=True,
        )

    def stop(self) -> None:
        self.bridge.stop()

    def publish_discovery(self) -> None:
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

    def publish_state(self, state: OutdoorState) -> int:
        count = 0
        for topic, payload in season_state_topics(state).items():
            count += int(self.bridge.publish(topic, payload, retain=True))
        return count

    def set_available(self, available: bool) -> None:
        self.bridge.publish(
            SYSTEM_AVAILABILITY_TOPIC,
            "online" if available else "offline",
            retain=True,
        )

    def _on_message(self, topic: str, payload: str, retained: bool) -> None:
        # Retained commands are ignored so an old command cannot modify
        # runtime truth after restart/reconnect.
        if retained:
            return
        if topic.endswith("/target_temp_low"):
            command = "target_temp_low"
        elif topic.endswith("/target_temp_high"):
            command = "target_temp_high"
        elif topic.endswith("/hvac_mode"):
            command = "hvac_mode"
        else:
            return
        self.command_queue.put_nowait((command, payload.strip()))
