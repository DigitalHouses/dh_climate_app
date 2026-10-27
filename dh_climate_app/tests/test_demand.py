from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import json
import unittest

from dh_climate_app.config import ConfigError, configured_entity_ids, parse_options
from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.demand import actual_demand, device_demand, room_demand
from dh_climate_app.discovery import demand_discovery_payloads, demand_object_id
from dh_climate_app.ha_client import HaState
from dh_climate_app.mqtt import ClimateMqttFacade
from dh_climate_app.rooms import RoomState


def config():
    return parse_options({
        "rooms": [
            {
                "id": "bedroom", "name": "Спальня",
                "temperature_sensors": ["sensor.bedroom"],
                "devices": [
                    {"entity": "climate.floor", "role": "slow_heat", "control": "device"},
                    {"entity": "climate.ac", "role": "fast_heat", "control": "app", "reversible": True},
                ],
            },
            {
                "id": "office", "name": "Кабинет",
                "temperature_sensors": ["sensor.office"],
                "devices": [
                    {"entity": "climate.water", "role": "slow_heat", "control": "device"},
                    {"entity": "climate.fan", "role": "fast_cool", "control": "device"},
                ],
            },
        ],
        "actual_demand": {"heat": "binary_sensor.salus_heat"},
    })


def room(room_id: str, *, mode="heat", action=HvacAction.IDLE, temp=23.0):
    return RoomState(
        room_id=room_id, name=room_id, current_temperature=temp,
        current_humidity=None, season=Season.HEAT,
        effective_profile=Profile.DAY, target_temperature=24.0,
        climate_control_enabled=True, control_action=action,
        hvac_mode=mode, hvac_action=action,
    )


def ha(entity_id: str, mode: str, action=None):
    now = datetime(2026, 10, 28, tzinfo=timezone.utc)
    attrs = {} if action is None else {"hvac_action": action}
    return HaState(entity_id, mode, attrs, now, now)


class FakeBridge:
    def __init__(self):
        self.messages = {}

    def set_message_handler(self, callback):
        self.message_handler = callback

    def publish(self, topic, payload, *, retain, force=False):
        assert retain
        self.messages[topic] = payload
        return True

    def start(self):
        pass

    def subscribe(self, topic):
        pass


class DemandReductionTests(unittest.TestCase):
    def test_room_based_on_hvac_action_only_not_devices(self):
        c = config()
        r = {
            "bedroom": room("bedroom", action=HvacAction.HEATING),
            "office": room("office", action=HvacAction.IDLE),
        }
        heat = room_demand(c, r, "heat")
        self.assertEqual((True, 1), (heat.active, heat.count))
        self.assertEqual([{"id": "bedroom", "name": "Спальня"}], list(heat.members))
        self.assertEqual((False, 0), (
            room_demand(c, r, "cool").active,
            room_demand(c, r, "cool").count,
        ))

    def test_room_missing_unknown_but_confirmed_on_wins(self):
        c = config()
        partial = {"bedroom": room("bedroom", action=HvacAction.IDLE)}
        state = room_demand(c, partial, "heat")
        self.assertIsNone(state.active)
        self.assertIsNone(state.count)
        partial["bedroom"] = room("bedroom", action=HvacAction.HEATING)
        state = room_demand(c, partial, "heat")
        self.assertTrue(state.active)
        self.assertIsNone(state.count)

    def test_room_temp_unavailable_not_counted_as_definite_off(self):
        c = config()
        state = room_demand(c, {
            "bedroom": room("bedroom", temp=None),
            "office": room("office"),
        }, "heat")
        self.assertIsNone(state.active)
        self.assertIsNone(state.count)

    def test_device_only_control_device_and_mode_plus_action(self):
        c = config()
        states = {
            "climate.floor": ha("climate.floor", "heat", "heating"),
            "climate.water": ha("climate.water", "heat", "heating"),
            "climate.fan": ha("climate.fan", "cool", "cooling"),
            "climate.ac": ha("climate.ac", "heat", "heating"),
        }
        heat = device_demand(c, states, "heat")
        self.assertEqual((True, 2), (heat.active, heat.count))
        self.assertEqual(
            {"climate.floor", "climate.water"},
            {d["entity_id"] for d in heat.members},
        )
        cool = device_demand(c, states, "cool")
        self.assertEqual((True, 1), (cool.active, cool.count))
        self.assertEqual("climate.fan", cool.members[0]["entity_id"])

    def test_device_idle_heat_mode_not_demand(self):
        c = config()
        states = {
            "climate.floor": ha("climate.floor", "heat", "idle"),
            "climate.water": ha("climate.water", "heat", "idle"),
            "climate.fan": ha("climate.fan", "off"),
        }
        self.assertEqual((False, 0), (
            device_demand(c, states, "heat").active,
            device_demand(c, states, "heat").count,
        ))
        self.assertFalse(device_demand(c, states, "cool").active)

    def test_device_missing_action_unknown_and_on_wins(self):
        c = config()
        states = {
            "climate.floor": ha("climate.floor", "heat"),  # No hvac_action.
            "climate.water": ha("climate.water", "heat", "idle"),
            "climate.fan": ha("climate.fan", "cool", "idle"),
        }
        self.assertIsNone(device_demand(c, states, "heat").active)
        states["climate.water"] = ha("climate.water", "heat", "heating")
        result = device_demand(c, states, "heat")
        self.assertTrue(result.active)
        self.assertIsNone(result.count)

    def test_missing_devices_do_not_make_false_cool_demand(self):
        c = config()
        self.assertIsNone(device_demand(c, {}, "cool").active)

    def test_actual_explicit_binary_only(self):
        c = config()
        self.assertIn("binary_sensor.salus_heat", configured_entity_ids(c))
        self.assertTrue(actual_demand("binary_sensor.salus_heat", {
            "binary_sensor.salus_heat": ha("binary_sensor.salus_heat", "on")
        }))
        self.assertFalse(actual_demand("binary_sensor.salus_heat", {
            "binary_sensor.salus_heat": ha("binary_sensor.salus_heat", "off")
        }))
        self.assertIsNone(actual_demand("binary_sensor.salus_heat", {}))
        self.assertIsNone(actual_demand("binary_sensor.salus_heat", {
            "binary_sensor.salus_heat": ha("binary_sensor.salus_heat", "unavailable")
        }))

    def test_actual_requires_binary_sensor_and_known_keys(self):
        with self.assertRaises(ConfigError):
            parse_options({"rooms": [], "actual_demand": {"heat": "sensor.not_binary"}})
        with self.assertRaises(ConfigError):
            parse_options({"rooms": [], "actual_demand": {"fan": "binary_sensor.x"}})


class DemandDiscoveryTests(unittest.TestCase):
    def test_exact_entities_and_binary_without_custom_attributes(self):
        payloads = demand_discovery_payloads("0.1.33", actual_sources={"heat": "binary_sensor.salus"})
        self.assertEqual(9, len(payloads))
        binary = payloads[("room", "heat", "binary")][1]
        self.assertEqual("binary_sensor.dh_climate_app_heat_demand", binary["default_entity_id"])
        self.assertNotIn("json_attributes_topic", binary)
        self.assertEqual(
            "sensor.dh_climate_app_heat_device_demand_count",
            payloads[("device", "heat", "count")][1]["default_entity_id"],
        )
        self.assertIn(("actual", "heat", "binary"), payloads)
        self.assertNotIn(("actual", "cool", "binary"), payloads)
        self.assertEqual(
            "dh_climate_app_actual_heat_demand",
            demand_object_id("actual", "heat"),
        )

    def test_state_publications_and_unknown_availability(self):
        c = config()
        b = FakeBridge()
        f = ClimateMqttFacade(
            bridge=b, app_version="0.1.33",
            started_at=datetime.now(timezone.utc),
            rooms=c.rooms, command_queue=asyncio.Queue(),
            actual_demand_sources=dict(c.actual_demand),
        )
        f.publish_demand_discovery()
        f.publish_demand("room", "heat", room_demand(c, {
            "bedroom": room("bedroom", action=HvacAction.HEATING),
            "office": room("office"),
        }, "heat"))
        base = "DigitalHouses/Global/dh_climate_app/demand/room/heat"
        self.assertEqual("ON", b.messages[f"{base}/state"])
        self.assertEqual("1", b.messages[f"{base}/count"])
        self.assertEqual(
            [{"id": "bedroom", "name": "Спальня"}],
            json.loads(b.messages[f"{base}/attributes"])["rooms"],
        )
        f.publish_demand("room", "heat", room_demand(c, {
            "bedroom": room("bedroom", action=HvacAction.HEATING),
        }, "heat"))
        self.assertEqual("online", b.messages[f"{base}/availability"])
        self.assertEqual("offline", b.messages[f"{base}/count_availability"])
        f.publish_demand("actual", "heat", None)
        actual_base = "DigitalHouses/Global/dh_climate_app/demand/actual/heat"
        self.assertEqual("offline", b.messages[f"{actual_base}/availability"])
        f.set_demand_available(False)
        self.assertEqual("offline", b.messages[f"{base}/availability"])
        self.assertEqual("offline", b.messages[f"{base}/count_availability"])

    def test_unconfigured_actual_removed_from_discovery(self):
        b = FakeBridge()
        f = ClimateMqttFacade(
            bridge=b, app_version="0.1.33",
            started_at=datetime.now(timezone.utc),
            rooms=(), command_queue=asyncio.Queue(),
        )
        f.publish_demand_discovery()
        self.assertEqual(
            "",
            b.messages["homeassistant/binary_sensor/dh_climate_app_actual_heat_demand/config"],
        )
        self.assertEqual(
            "",
            b.messages["homeassistant/binary_sensor/dh_climate_app_actual_cool_demand/config"],
        )
