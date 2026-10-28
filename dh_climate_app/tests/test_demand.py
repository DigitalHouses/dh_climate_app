from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import unittest

from dh_climate_app.config import ConfigError, configured_entity_ids, parse_options
from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.demand import Demand, device_demand, room_demand, resource_request
from dh_climate_app.discovery import demand_discovery_payloads, demand_object_id
from dh_climate_app.ha_client import HaState
from dh_climate_app.mqtt import ClimateMqttFacade
from dh_climate_app.rooms import RoomState


def config():
    return parse_options({
        "heating_source": "boiler",
        "vrf": "on",
        "rooms": [
            {
                "id": "bedroom", "name": "Спальня",
                "temperature_sensors": ["sensor.bedroom"],
                "devices": [
                    {"entity": "climate.floor", "role": "slow_heat", "device_type": "hardware", "resource": "home_heating"},
                    {"entity": "climate.ac", "role": "fast_heat", "device_type": "virtual", "reversible": True, "resource": "vrf"},
                ],
            },
            {
                "id": "office", "name": "Кабинет",
                "temperature_sensors": ["sensor.office"],
                "devices": [
                    {"entity": "climate.water", "role": "fast_heat", "device_type": "hardware", "resource": "home_heating"},
                    {"entity": "switch.floor_valve", "role": "slow_heat", "device_type": "virtual", "resource": "home_heating",
                     "actuator": "normal_closed", "temperature_sensor": "sensor.screed",
                     "screed_sensor_unavailable": "open"},
                    {"entity": "climate.fan", "role": "fast_cool", "device_type": "hardware", "resource": "vrf"},
                ],
            },
        ],
        "resources": {"boiler": {"aggregator": "binary_sensor.salus_heat"}},
    })


def room(room_id: str, *, season=Season.HEAT, mode="heat",
         action=HvacAction.IDLE, temp=23.0):
    return RoomState(
        room_id=room_id, name=room_id, current_temperature=temp,
        current_humidity=None, season=season,
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
    def start(self): pass
    def subscribe(self, topic): pass


class DemandReductionTests(unittest.TestCase):
    def test_room_based_on_room_action_not_device_action(self):
        c = config()
        rs = {"bedroom": room("bedroom", action=HvacAction.HEATING),
              "office": room("office", action=HvacAction.IDLE)}
        result = room_demand(c, rs, "heat")
        self.assertEqual((True, 1), (result.active, result.count))
        self.assertEqual([{"id": "bedroom", "name": "Спальня"}], list(result.members))
        self.assertEqual((False, 0), (room_demand(c, rs, "cool").active, room_demand(c, rs, "cool").count))

    def test_room_unknown_and_resource_scoped_diagnostic(self):
        c = config()
        partial = {"bedroom": room("bedroom", action=HvacAction.HEATING)}
        demand = room_demand(c, partial, "heat")
        self.assertTrue(demand.active)
        self.assertIsNone(demand.count)
        self.assertTrue(room_demand(c, partial, "heat", resource="home_heating").active)
        self.assertIsNone(room_demand(c, {}, "heat", resource="home_heating").active)

    def test_hardware_thermostat_action_not_merely_mode(self):
        c = config()
        states = {
            "climate.floor": ha("climate.floor", "heat", "idle"),
            "climate.water": ha("climate.water", "heat", "heating"),
            "climate.fan": ha("climate.fan", "off"),
        }
        demand = device_demand(c, states, "heat", device_type="hardware")
        self.assertEqual((True, 1), (demand.active, demand.count))
        self.assertEqual("climate.water", demand.members[0]["entity_id"])
        self.assertFalse(device_demand(c, states, "cool", device_type="hardware").active)
        states["climate.floor"] = ha("climate.floor", "heat")
        demand = device_demand(c, states, "heat", device_type="hardware")
        self.assertTrue(demand.active)
        self.assertIsNone(demand.count)

    def test_virtual_switch_observed_with_explicit_polarity(self):
        c = config()
        snap = {"switch.floor_valve": ha("switch.floor_valve", "on"),
                "sensor.screed": ha("sensor.screed", "26.3"),
                "climate.ac": ha("climate.ac", "off")}
        result = device_demand(c, snap, "heat", device_type="virtual")
        self.assertEqual((True, 1), (result.active, result.count))
        self.assertEqual("switch.floor_valve", result.members[0]["entity_id"])
        snap["sensor.screed"] = ha("sensor.screed", "unavailable")
        result = device_demand(c, snap, "heat", device_type="virtual")
        self.assertIsNone(result.active)
        self.assertIsNone(result.count)

    def test_resource_request_excludes_unrelated_ac_and_room_demand(self):
        c = config()
        rs = {"bedroom": room("bedroom", action=HvacAction.HEATING),
              "office": room("office", action=HvacAction.HEATING)}
        snap = {
            "climate.floor": ha("climate.floor", "heat", "idle"),
            "climate.water": ha("climate.water", "heat", "idle"),
            "switch.floor_valve": ha("switch.floor_valve", "off"),
            "sensor.screed": ha("sensor.screed", "27"),
            "climate.ac": ha("climate.ac", "heat", "heating"),
        }
        heat = resource_request(c, snap, "heat", resource="home_heating", room_states=rs)
        self.assertEqual((False, 0), (heat.active, heat.count))
        snap["climate.water"] = ha("climate.water", "heat", "heating")
        heat = resource_request(c, snap, "heat", resource="home_heating", room_states=rs)
        self.assertEqual((True, 1), (heat.active, heat.count))
        self.assertNotIn("climate.ac", [x["entity_id"] for x in heat.members])

    def test_cool_resource_and_unknown(self):
        c = config()
        rs = {"bedroom": room("bedroom", season=Season.COOL, mode="cool", action=HvacAction.COOLING),
              "office": room("office", season=Season.COOL, mode="cool", action=HvacAction.IDLE)}
        snap = {
            "climate.ac": ha("climate.ac", "cool", "cooling"),
            "climate.fan": ha("climate.fan", "cool", "idle"),
        }
        cool = resource_request(c, snap, "cool", resource="vrf", room_states=rs)
        self.assertEqual((True, 1), (cool.active, cool.count))
        snap.pop("climate.fan")
        cool = resource_request(c, snap, "cool", resource="vrf", room_states=rs)
        self.assertTrue(cool.active)
        self.assertIsNone(cool.count)

    def test_no_legacy_actual_demand_config_and_resources_are_explicit(self):
        c = config()
        self.assertIn("binary_sensor.salus_heat", configured_entity_ids(c))
        with self.assertRaisesRegex(ConfigError, "obsolete"):
            parse_options({"actual_demand": {"heat": "binary_sensor.salus"}})
        with self.assertRaises(ConfigError):
            parse_options({"heating_source": "central_heating", "resources": {"boiler": {}}})


class DemandDiscoveryTests(unittest.TestCase):
    def test_entities_and_counts_for_all_demand_slices(self):
        payloads = demand_discovery_payloads("0.2.0", heating_source="boiler", vrf_enabled=True)
        self.assertEqual(16, len(payloads))
        binary = payloads[("room", "heat", "binary")][1]
        self.assertEqual("binary_sensor.dh_climate_app_heat_demand", binary["default_entity_id"])
        self.assertNotIn("json_attributes_topic", binary)
        self.assertEqual("sensor.dh_climate_app_heat_hardware_demand_count",
                         payloads[("hardware", "heat", "count")][1]["default_entity_id"])
        self.assertIn(("boiler", "heat", "binary"), payloads)
        self.assertIn(("vrf", "cool", "binary"), payloads)
        self.assertNotIn(("boiler", "cool", "binary"), payloads)
        self.assertEqual("dh_climate_app_boiler_heat_request", demand_object_id("boiler", "heat"))
        self.assertEqual(12, len(demand_discovery_payloads("0.2.0")))

    def test_state_publications_and_unknown_availability(self):
        bridge = FakeBridge()
        facade = ClimateMqttFacade(
            bridge=bridge, app_version="0.2.0", started_at=datetime.now(timezone.utc),
            rooms=config().rooms, command_queue=asyncio.Queue(),
            heating_source="boiler", vrf_enabled=True,
        )
        facade.publish_demand("boiler", "heat", Demand(True, 2, (
            {"room_id": "bedroom", "entity_id": "climate.floor"},
            {"room_id": "office", "entity_id": "climate.water"},
        )))
        base = "DigitalHouses/Global/dh_climate_app/demand/boiler/heat"
        self.assertEqual("ON", bridge.messages[base + "/state"])
        self.assertEqual("2", bridge.messages[base + "/count"])
        facade.publish_demand("boiler", "heat", Demand(None, None))
        self.assertEqual("offline", bridge.messages[base + "/availability"])
        self.assertEqual("offline", bridge.messages[base + "/count_availability"])
        facade.set_demand_available(False)
        self.assertEqual("offline", bridge.messages[base + "/availability"])
