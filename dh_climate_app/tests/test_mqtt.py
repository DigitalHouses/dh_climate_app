from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone

from dh_climate_app.config import parse_options
from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.discovery import SYSTEM_AVAILABILITY_TOPIC
from dh_climate_app.mqtt import ClimateMqttFacade, MqttBridge
from dh_climate_app.rooms import RoomState
from test_config import options


class FakeBridge:
    def __init__(self) -> None:
        self.handler = None
        self.publications = []

    def set_message_handler(self, handler) -> None:
        self.handler = handler

    def publish(self, topic, payload, *, retain, force=False):
        self.publications.append((topic, payload, retain, force))
        return True


class DedupeFakeBridge(FakeBridge):
    def __init__(self) -> None:
        super().__init__()
        self.last_payloads = {}
        self.scheduled = []

    def publish(self, topic, payload, *, retain, force=False):
        changed = force or self.last_payloads.get(topic) != payload
        if changed:
            self.publications.append((topic, payload, retain, force))
            self.last_payloads[topic] = payload
        return changed

    def schedule_retained_republish(
        self,
        payloads,
        *,
        delay_seconds=0.5,
    ) -> None:
        self.scheduled.append((dict(payloads), delay_seconds))
        for topic, payload in payloads.items():
            self.publish(topic, payload, retain=True, force=True)


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


class MutatingSubscriptionClient(FakeMqttClient):
    def __init__(self, bridge) -> None:
        super().__init__()
        self.bridge = bridge
        self.mutated = False

    def subscribe(self, topic, qos=0):
        result = super().subscribe(topic, qos=qos)
        if not self.mutated:
            self.mutated = True
            self.bridge._subscriptions.add("DigitalHouses/test/late")
        return result


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

    async def test_connect_tolerates_subscription_set_mutation(self) -> None:
        bridge = object.__new__(MqttBridge)
        bridge.loop = asyncio.get_running_loop()
        bridge._subscriptions = {"DigitalHouses/test/set"}
        bridge._last_payloads = {}
        bridge._retained_payloads = {}
        bridge._connected_once = False
        bridge.client = MutatingSubscriptionClient(bridge)

        bridge._on_connect(bridge.client, None, None, 0)

        self.assertIn("DigitalHouses/test/late", bridge._subscriptions)
        self.assertEqual(
            [("DigitalHouses/test/set", 1)],
            bridge.client.subscriptions,
        )


class MqttRoomDiscoveryRehydrateTests(unittest.TestCase):
    def test_discovery_change_forces_delayed_room_state_rehydrate(self) -> None:
        bridge = DedupeFakeBridge()
        queue: asyncio.Queue = asyncio.Queue()
        config = parse_options(options())
        facade = ClimateMqttFacade(
            bridge=bridge,
            app_version="0.1.16",
            started_at=datetime.now(timezone.utc),
            rooms=config.rooms,
            command_queue=queue,
        )
        room = config.rooms[0]
        state = RoomState(
            room_id=room.room_id,
            name=room.name,
            current_temperature=21.0,
            current_humidity=45.0,
            season=Season.HEAT,
            effective_profile=Profile.DAY,
            target_temperature=23.0,
            climate_control_enabled=True,
            control_action=HvacAction.HEATING,
            hvac_mode="heat",
            hvac_action=HvacAction.HEATING,
        )

        facade.publish_room(
            state,
            published_profile="day",
            published_target=23.0,
            profile_targets={},
        )

        self.assertEqual(1, len(bridge.scheduled))
        payloads, delay = bridge.scheduled[0]
        self.assertEqual(0.5, delay)
        profile_topic = (
            "DigitalHouses/Global/dh_climate_app/rooms/"
            f"{room.room_id}/climate/profile"
        )
        self.assertEqual("day", payloads[profile_topic])

        forced_profile = [
            item
            for item in bridge.publications
            if item[0] == profile_topic and item[3] is True
        ]
        self.assertTrue(forced_profile)

    def test_unchanged_discovery_does_not_schedule_rehydrate(self) -> None:
        bridge = DedupeFakeBridge()
        queue: asyncio.Queue = asyncio.Queue()
        config = parse_options(options())
        facade = ClimateMqttFacade(
            bridge=bridge,
            app_version="0.1.16",
            started_at=datetime.now(timezone.utc),
            rooms=config.rooms,
            command_queue=queue,
        )
        room = config.rooms[0]
        state = RoomState(
            room_id=room.room_id,
            name=room.name,
            current_temperature=21.0,
            current_humidity=45.0,
            season=Season.HEAT,
            effective_profile=Profile.DAY,
            target_temperature=23.0,
            climate_control_enabled=True,
            control_action=HvacAction.HEATING,
            hvac_mode="heat",
            hvac_action=HvacAction.HEATING,
        )

        facade.publish_room(
            state,
            published_profile="day",
            published_target=23.0,
            profile_targets={},
        )
        bridge.scheduled.clear()

        facade.publish_room(
            state,
            published_profile="day",
            published_target=23.0,
            profile_targets={},
        )

        self.assertEqual([], bridge.scheduled)


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

    def test_machine_event_is_transient_qos_transport(self) -> None:
        self.facade.publish_event(
            {
                "schema_version": 2,
                "event_type": "season_changed",
                "observed_at": "2026-09-26T16:00:00+05:00",
            }
        )
        topic, payload, retain, force = self.facade.bridge.publications[-1]
        self.assertTrue(topic.endswith("/event"))
        self.assertIn('"event_type":"season_changed"', payload)
        self.assertFalse(retain)
        self.assertTrue(force)

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

    def test_room_preset_command(self) -> None:
        self.facade._on_message(
            "DigitalHouses/Global/dh_climate_app/rooms/living_room/climate/set/profile",
            "night",
            False,
        )
        command = self.queue.get_nowait()
        self.assertEqual("room", command.scope)
        self.assertEqual("living_room", command.room_id)
        self.assertEqual("profile", command.command)
        self.assertEqual("night", command.payload)

    def test_room_profile_target_command(self) -> None:
        self.facade._on_message(
            "DigitalHouses/Global/dh_climate_app/rooms/living_room/targets/set/heat_night",
            "20.0",
            False,
        )
        command = self.queue.get_nowait()
        self.assertEqual("target", command.scope)
        self.assertEqual("living_room", command.room_id)
        self.assertEqual("heat_night", command.command)
        self.assertEqual("20.0", command.payload)

    def test_retained_command_is_ignored(self) -> None:
        self.facade._on_message(
            "DigitalHouses/Global/dh_climate_app/season/set/target_temp_low",
            "10",
            True,
        )
        self.assertTrue(self.queue.empty())


if __name__ == "__main__":
    unittest.main()
