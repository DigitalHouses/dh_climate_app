"""Contract tests for read-only hydraulic graph (no new control outputs)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace as NS
import unittest

from dh_climate_app.config import ConfigError, configured_entity_ids, parse_options
from dh_climate_app.operations import build_operations_snapshot


def base():
    return {
        "heating_source": "boiler",
        "outdoor": {"temperature_sources": [], "humidity_sources": []},
        "rooms": [{
            "id": "hall", "name": "Зал",
            "temperature_sensors": ["sensor.hall_air"],
            "humidity_sensors": [], "window_sensors": [], "devices": [],
        }],
    }


def graph():
    return {
        "aggregators": [
            {"id": "logo", "name": "Siemens LOGO!", "device_type": "hardware",
             "signals": {"heat_request": "binary_sensor.logo_heat_request"}},
        ],
        "separators": [{
            "id": "header", "name": "Гидрострелка",
            "signals": {"supply_temperature": "sensor.header_supply"},
        }],
        "groups": [
            {"id": "fast", "name": "Высокотемпературная", "separator_id": "header",
             "temperature_class": "high", "aggregator_id": "logo",
             "pump_ids": ["shared"],
             "signals": {"return_temperature": "sensor.fast_return"}},
            {"id": "slow", "name": "Низкотемпературная", "separator_id": "header",
             "temperature_class": "low", "pump_ids": ["shared"],
             "signals": {"supply_temperature": "sensor.slow_supply",
                         "supply_pressure": "sensor.slow_pressure"}},
        ],
        "pumps": [{"id": "shared", "name": "Общий насос",
                   "signals": {"state": "binary_sensor.pump_on",
                               "rpm": "sensor.pump_rpm"}}],
        "actuators": [{"id": "valve_a", "name": "Термоэлектрический привод",
                       "signals": {"powered": "binary_sensor.valve_a_power"}}],
        "circuits": [
            {"id": "floor_hall", "name": "Петля пола, зал",
             "group_id": "slow", "room_id": "hall", "actuator_ids": ["valve_a"],
             "signals": {"return_temperature": "sensor.floor_hall_return"},
             "terminals": [{"id": "floor", "name": "Тёплый пол",
                            "room_id": "hall", "entity_id": "climate.hall_floor"}]},
        ],
    }


def observed(state, unit=None):
    return NS(state=state, last_updated=datetime(2026, 11, 2, tzinfo=timezone.utc),
              attributes={
                  "friendly_name": "Подача" if unit else "Статус",
                  **({"unit_of_measurement": unit} if unit else {}),
              })


def operations(config, states, online=True):
    return build_operations_snapshot(
        config=config, outdoor=None, weather=None, room_states={}, health=None,
        problems=(), demands={}, states=states, version="test",
        ha_connected=online,
    )


class HydraulicResourceTests(unittest.TestCase):
    def test_absent_optional_graph_preserves_old_configuration(self):
        config = parse_options(base())
        self.assertEqual((), config.hydraulics.groups)
        self.assertEqual([], operations(config, {}, True)["home"]["hydraulics"]["separators"])

    def test_complete_graph_preserves_shared_pump_and_links(self):
        raw = base()
        raw["hydraulics"] = graph()
        config = parse_options(raw)
        self.assertEqual(2, len(config.hydraulics.groups))
        self.assertEqual(("shared",), config.hydraulics.groups[0].pump_ids)
        self.assertEqual(("shared",), config.hydraulics.groups[1].pump_ids)
        self.assertEqual(1, len(config.hydraulics.pumps))
        self.assertEqual("hall", config.hydraulics.circuits[0].room_id)
        ids = configured_entity_ids(config)
        self.assertIn("sensor.slow_pressure", ids)
        self.assertIn("climate.hall_floor", ids)
        self.assertIn("binary_sensor.valve_a_power", ids)

    def test_real_values_and_native_units_and_zero_are_preserved(self):
        raw = base()
        raw["hydraulics"] = graph()
        config = parse_options(raw)
        states = {
            "sensor.slow_supply": observed("28.1", "°C"),
            "sensor.slow_pressure": observed("0", "bar"),
            "binary_sensor.valve_a_power": observed("off"),
            "sensor.header_supply": observed("unavailable", "°C"),
        }
        snap = operations(config, states)
        h = snap["home"]["hydraulics"]
        slow = next(g for g in h["groups"] if g["id"] == "slow")
        self.assertEqual("28.1", slow["signals"][0]["state"])
        self.assertEqual("°C", slow["signals"][0]["unit"])
        self.assertEqual("0", slow["signals"][1]["state"])
        self.assertEqual("bar", slow["signals"][1]["unit"])
        self.assertTrue(slow["signals"][1]["available"])
        self.assertFalse(h["separators"][0]["signals"][0]["available"])
        self.assertIsNone(h["pumps"][0]["signals"][0]["state"])
        self.assertFalse(h["pumps"][0]["signals"][0]["available"])
        self.assertEqual("off", h["actuators"][0]["signals"][0]["state"])

    def test_disconnected_snapshot_does_not_reuse_stale_ha_readings(self):
        raw = base()
        raw["hydraulics"] = graph()
        config = parse_options(raw)
        snap = operations(config, {"sensor.slow_supply": observed("28.1", "°C")}, False)
        signal = snap["home"]["hydraulics"]["groups"][1]["signals"][0]
        self.assertIsNone(signal["state"])
        self.assertFalse(signal["available"])

    def test_no_separators_and_no_groups_are_allowed(self):
        raw = base()
        raw["hydraulics"] = {"circuits": [{
            "id": "radiators", "name": "Радиаторы", "room_id": "hall",
        }]}
        self.assertEqual("radiators", parse_options(raw).hydraulics.circuits[0].item_id)

    def test_unknown_and_duplicate_references_rejected(self):
        for changed in (
            {"pump_ids": ["missing"]},
            {"pump_ids": ["shared", "shared"]},
            {"separator_id": "other"},
        ):
            raw = base()
            h = graph()
            h["groups"][0].update(changed)
            raw["hydraulics"] = h
            with self.subTest(changed=changed), self.assertRaises(ConfigError):
                parse_options(raw)

    def test_unknown_room_and_telemetry_entity_rejected(self):
        raw = base()
        h = graph()
        h["circuits"][0]["room_id"] = "missing"
        raw["hydraulics"] = h
        with self.assertRaisesRegex(ConfigError, "unknown room"):
            parse_options(raw)
        raw = base()
        h = graph()
        h["groups"][1]["signals"]["supply_temperature"] = "foo.not_an_ha_domain"
        raw["hydraulics"] = h
        with self.assertRaises(ConfigError):
            parse_options(raw)

    def test_no_duplicate_physical_definitions_and_no_implicit_defaults(self):
        raw = base()
        h = graph()
        h["pumps"].append({"id": "shared", "name": "Насос-дубликат"})
        raw["hydraulics"] = h
        with self.assertRaisesRegex(ConfigError, "duplicate id"):
            parse_options(raw)
        raw = base()
        raw["hydraulics"] = {"groups": [{"id": "low", "name": "ТП"}]}
        with self.assertRaisesRegex(ConfigError, "temperature_class"):
            parse_options(raw)


if __name__ == "__main__":
    unittest.main()
