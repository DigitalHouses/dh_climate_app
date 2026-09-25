from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone

from dh_climate_app.config import parse_options
from dh_climate_app.discovery import SYSTEM_AVAILABILITY_TOPIC
from dh_climate_app.mqtt import ClimateMqttFacade, MqttBridge
from test_config import options


class FakeBridge:
    def __init__(self) -> None:
        self.handler = None

    def set_message_handler(self, handler) -> None:
        self.handler = handler


class FakePublishInfo:
    def wait_for_publish(self, timeout=None) -> None:
        return None


class FakeMqttClient:
    def __init__(self) -> None:
        self.subscriptions = []
        self.publications = []

    def subscribe(self, topic, qos=0):
        self.subscriptions.append((topic, qos))
        return (0, len(self.subscriptions))

    def publish(self, topic, payload=None, qos=0, retain=False):
        self.publications.append((topic, payload, qos, retain))
        return FakePublishInfo()


class MqttReconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconnect_restores_retained_topics_and_online_availability(self) -> None:
        bridge = object.__new__(MqttBridge)
        bridge.loop = asyncio.get_running_loop()
        bridge.client = FakeMqttClient()
        bridge._subscriptions = {"DigitalHouses/test/set"}
        bridge._last_payloads = {
            SYSTEM_AVAILABILITY_TOPIC: "online",
            "DigitalHouses/test/state": "42",
        }
        bridge._retained_payloads = dict(bridge._last_payloads)
        bridge._connected_once = False

        bridge._on_connect(bridge.client, None, None, 0)
        await asyncio.sleep(0)
        self.assertEqual([], bridge.client.publications)

        bridge._on_connect(bridge.client, None, None, 0)
        await asyncio.sleep(0)

        published = {
            topic: (payload, qos, retain)
            for topic, payload, qos, retain in bridge.client.publications
        }
        self.assertEqual(
            ("online", 1, True),
            published[SYSTEM_AVAILABILITY_TOPIC],
        )
        self.assertEqual(
            ("42", 1, True),
            published["DigitalHouses/test/state"],
        )
        self.assertEqual(
            [
                ("DigitalHouses/test/set", 1),
                ("DigitalHouses/test/set", 1),
            ],
            bridge.client.subscriptions,
        )


class MqttRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self.facade = ClimateMqttFacade(
            bridge=FakeBridge(),
            app_version="0.1.0",
            started_at=datetime.now(timezone.utc),
            rooms=parse_options(options()).rooms,
            command_queue=self.queue,
        )

    def test_system_delete_telemetry_command(self) -> None:
        self.facade._on_message(
            "DigitalHouses/Global/dh_climate_app/system/set/delete_telemetry",
            "DELETE",
            False,
        )
        command = self.queue.get_nowait()
        self.assertEqual("system", command.scope)
        self.assertEqual("delete_telemetry", command.command)
        self.assertEqual("DELETE", command.payload)

    def test_room_target_command(self) -> None:
        self.facade._on_message(
            "DigitalHouses/Global/dh_climate_app/rooms/living_room/climate/set/target_temperature",
            "23.5",
            False,
        )
        command = self.queue.get_nowait()
        self.assertEqual("room", command.scope)
        self.assertEqual("living_room", command.room_id)
        self.assertEqual("target_temperature", command.command)

    def test_retained_command_is_ignored(self) -> None:
        self.facade._on_message(
            "DigitalHouses/Global/dh_climate_app/season/set/target_temp_low",
            "10",
            True,
        )
        self.assertTrue(self.queue.empty())


if __name__ == "__main__":
    unittest.main()
