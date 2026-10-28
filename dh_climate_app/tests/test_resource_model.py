"""Integrated contract for a complete 0.2.x resource/read-model install."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace as NS
import unittest

from dh_climate_app.config import ConfigError, configured_entity_ids, parse_options
from dh_climate_app.core import DeviceClass, Profile, Season
from dh_climate_app.demand import Demand, resource_request
from dh_climate_app.devices import compile_room_devices
from dh_climate_app.ha_client import HaState
from dh_climate_app.rooms import RoomState
from dh_climate_app.topology import build_topology


T = datetime(2026, 10, 28, tzinfo=timezone.utc)


def ha(entity, value, **attrs):
    return HaState(entity, str(value), attrs, T, T)


def opts(*, heating="boiler", vrf="off", devices=None, resources=None):
    return {
        "heating_source": heating,
        "vrf": vrf,
        "outdoor": {"temperature_sources": [], "humidity_sources": []},
        "rooms": [{
            "id": "livingroom", "name": "Гостиная",
            "temperature_sensors": ["sensor.room_air"],
            "humidity_sensors": [], "window_sensors": [],
            "devices": devices or [],
        }],
        "resources": resources or [],
        "pumps": [], "circuits": [],
    }


def room_state(season=Season.HEAT):
    return RoomState(
        room_id="livingroom", name="Гостиная",
        current_temperature=21.0, current_humidity=None, season=season,
        effective_profile=Profile.DAY, target_temperature=23.0,
        climate_control_enabled=True,
        control_action=NS(value="heating" if season == Season.HEAT else "cooling"),
        hvac_mode=season.value,
        hvac_action=NS(value="heating" if season == Season.HEAT else "cooling"),
        control_target_temperature=23.0,
    )


def tree(config, snapshot=None, demands=None, slices=None):
    snapshot = snapshot or {}
    result = build_topology(
        config=config,
        outdoor=NS(current_temperature=6, last_valid_at=T,
                   avg_24h_temperature=7, stale=False, season=NS(value="heat")),
        weather=None,
        room_states={"livingroom": room_state()},
        humidity_states={},
        health=NS(climate_state="healthy", global_state="healthy",
                  rooms={"livingroom": "healthy"}),
        snapshot=snapshot,
        app_version="0.2.0", started_at=T, observed_at=T,
        ha_connected=True,
        room_targets={"livingroom": {"heat_day": 23, "heat_night": 20,
                                    "heat_away": 18, "heat_antifreeze": 10}},
        demands=demands or {}, resource_slices=slices or {},
    )
    return "\n".join(row["prefix"] + "".join(p["text"] for p in row["parts"])
                     for row in result["lines"]), result


class ResourceModelTests(unittest.TestCase):
    def test_full_seven_room_supervisor_yaml_parses_unchanged(self):
        from pathlib import Path
        import yaml
        root = Path(__file__).resolve().parents[1]
        path = root / "examples/dh_climate_app_0.2.0_options.yaml"
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        config = parse_options(raw)
        self.assertEqual(7, len(config.rooms))
        self.assertEqual("boiler", config.heating_source)
        self.assertIs(config.vrf_enabled, False)
        self.assertEqual("hardware", config.rooms[0].devices[0].device_type)
        self.assertEqual("heat_cool", config.rooms[1].devices[0].function)
        self.assertFalse(any(d.resource == "home_heating"
                             for r in config.rooms for d in r.devices))
        self.assertEqual([], raw["resources"])

    def test_generic_documented_supervisor_example_is_valid(self):
        from pathlib import Path
        import yaml
        root = Path(__file__).resolve().parents[1]
        raw = yaml.safe_load(
            (root / "docs/CONFIG_EXAMPLE.yaml").read_text(encoding="utf-8")
        )
        config = parse_options(raw)
        self.assertEqual("central_heating", config.heating_source)
        self.assertIs(config.vrf_enabled, True)
        self.assertIn("vrf", config.resources)
        self.assertEqual("open", config.rooms[0].devices[1].screed_sensor_unavailable)
    def test_boiler_inside_home_with_live_telemetry(self):
        raw = opts(devices=[{
            "entity": "climate.wall", "role": "fast_heat",
            "device_type": "hardware", "resource": "home_heating",
        }], resources=[{"id": "boiler", "status": "sensor.boiler_state",
                       "dhw": "binary_sensor.boiler_dhw",
                       "aggregator": "binary_sensor.salus_output"}])
        raw["pumps"] = [{"id": "main", "name": "Main pump",
                         "state": "switch.pump", "power": "sensor.pump_w", "rpm": "sensor.pump_rpm"}]
        raw["circuits"] = [{"id": "flow", "name": "Supply",
                            "temperature": "sensor.flow_temp", "pressure": "sensor.flow_pressure"}]
        config = parse_options(raw)
        self.assertIn("sensor.pump_w", configured_entity_ids(config))
        states = {
            "sensor.boiler_state": ha("sensor.boiler_state", "heating"),
            "binary_sensor.boiler_dhw": ha("binary_sensor.boiler_dhw", "off"),
            "binary_sensor.salus_output": ha("binary_sensor.salus_output", "on"),
            "switch.pump": ha("switch.pump", "on"),
            "sensor.pump_w": ha("sensor.pump_w", "48", unit_of_measurement="W"),
            "sensor.pump_rpm": ha("sensor.pump_rpm", "1450", unit_of_measurement="rpm"),
            "sensor.flow_temp": ha("sensor.flow_temp", "61.5", unit_of_measurement="°C"),
            "sensor.flow_pressure": ha("sensor.flow_pressure", "1.8", unit_of_measurement="bar"),
        }
        data, obj = tree(config, states,
                         demands={("boiler", "heat"): Demand(True, 1)},
                         slices={"room": Demand(True, 1),
                                 "hardware": Demand(True, 1),
                                 "virtual": Demand(False, 0)})
        self.assertIn("🏡 HOME", data)
        self.assertLess(data.index("🏡 HOME"), data.index("🔥 BOILER"))
        self.assertLess(data.index("🔥 BOILER"), data.index("🏘️ ROOMS"))
        self.assertIn("BOILER HEAT REQUEST: ON", data)
        self.assertIn("48 W", data)
        self.assertIn("1450 rpm", data)
        self.assertIn("1.8 bar", data)
        self.assertIn("DHW: OFF", data)
        self.assertNotIn("CENTRAL_HEATING", data)
        self.assertTrue(any(
            part.get("entity_id") == "sensor.flow_pressure"
            for line in obj["lines"] for part in line["parts"]
        ))

    def test_central_hides_all_boiler_and_vrf_optional_monitor(self):
        config = parse_options(opts(heating="central_heating", vrf="on", resources=[
            {"id": "vrf", "compressor": "binary_sensor.vrf_compressor",
             "restriction": "sensor.vrf_restriction"},
        ]))
        data, _ = tree(config, {
            "binary_sensor.vrf_compressor": ha("binary_sensor.vrf_compressor", "on"),
            "sensor.vrf_restriction": ha("sensor.vrf_restriction", "frost"),
        })
        self.assertIn("CENTRAL_HEATING", data)
        self.assertIn("VRF", data)
        self.assertIn("Compressor: ON", data)
        self.assertIn("Restriction: FROST", data)
        self.assertNotIn("BOILER", data)
        self.assertNotIn("DHW", data)
        config_off = parse_options(opts(heating="central_heating", vrf="off"))
        off, _ = tree(config_off)
        self.assertNotIn("VRF", off)
        self.assertNotIn("BOILER", off)

    def test_unconfigured_resources_are_omitted(self):
        raw = {"outdoor": {"temperature_sources": [], "humidity_sources": []}, "rooms": []}
        config = parse_options(raw)
        out = build_topology(
            config=config,
            outdoor=NS(current_temperature=None, last_valid_at=None, stale=False,
                       avg_24h_temperature=None, season=NS(value="off")),
            weather=None, room_states={}, humidity_states={},
            health=NS(climate_state="unknown", global_state="unknown", rooms={}),
            snapshot={}, app_version="0.2.0", started_at=T, observed_at=T,
            ha_connected=False, room_targets={},
        )
        data = "\n".join(line["prefix"] + "".join(x["text"] for x in line["parts"]) for line in out["lines"])
        self.assertNotIn("BOILER", data)
        self.assertNotIn("CENTRAL", data)
        self.assertNotIn("VRF", data)

    def test_resource_request_without_explicit_devices_is_unknown(self):
        config = parse_options(opts())
        demand = resource_request(
            config, {}, "heat", resource="home_heating",
            room_states={"livingroom": room_state()},
        )
        self.assertIsNone(demand.active)
        self.assertIsNone(demand.count)

    def test_vrf_only_enabled_with_global_switch_and_correct_resource(self):
        with self.assertRaises(ConfigError):
            parse_options(opts(vrf="off", resources=[{"id": "vrf", "fault": "binary_sensor.fault"}]))
        with self.assertRaises(ConfigError):
            parse_options(opts(heating="central_heating", resources=[{"id": "boiler", "status": "sensor.boiler"}]))
        with self.assertRaises(ConfigError):
            parse_options(opts(devices=[{"entity": "climate.ac", "role": "fast_cool",
                                        "device_type": "virtual", "resource": "vrf"}]))
        with self.assertRaises(ConfigError):
            parse_options({**opts(), "resources": [{"id": "boiler"}, {"id": "boiler"}]})

    def test_slow_virtual_requires_explicit_action_and_respects_closed_fallback(self):
        entry = {"entity": "switch.floor", "role": "slow_heat", "device_type": "virtual",
                 "actuator": "normal_closed", "temperature_sensor": "sensor.screed"}
        with self.assertRaisesRegex(ConfigError, "explicit"):
            parse_options(opts(devices=[entry]))
        config = parse_options(opts(devices=[{**entry, "screed_sensor_unavailable": "closed"}]))
        desired = compile_room_devices(
            config=config, room_states={"livingroom": room_state()},
            humidity_states={}, outdoor_temperature=8,
            screed_values={"sensor.screed": "unavailable"},
        )
        self.assertFalse(desired[0].power)
        opened = parse_options(opts(devices=[{**entry, "screed_sensor_unavailable": "open"}]))
        desired = compile_room_devices(
            config=opened, room_states={"livingroom": room_state()},
            humidity_states={}, outdoor_temperature=8,
            screed_values={"sensor.screed": "unavailable"},
        )
        self.assertTrue(desired[0].power)

    def test_virtual_slow_sensorless_explicit_open(self):
        device = {"entity": "switch.floor", "role": "slow_heat", "device_type": "virtual",
                  "actuator": "normal_closed", "screed_sensor_unavailable": "open"}
        config = parse_options(opts(devices=[device]))
        result = compile_room_devices(
            config=config, room_states={"livingroom": room_state()},
            humidity_states={}, outdoor_temperature=8,
        )
        self.assertTrue(result[0].power)
        self.assertFalse(compile_room_devices(
            config=config, room_states={"livingroom": room_state(Season.COOL)},
            humidity_states={}, outdoor_temperature=8,
        )[0].power)
