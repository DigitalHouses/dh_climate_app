from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace as NS
import unittest

from dh_climate_app.topology import build_topology
from dh_climate_app.discovery import (
    TOPOLOGY_ATTRIBUTES_TOPIC, TOPOLOGY_STATE_TOPIC, topology_discovery_payload,
)
from dh_climate_app.mqtt import ClimateMqttFacade

NOW = datetime(2026, 10, 28, tzinfo=timezone.utc)


def state(value, **attributes):
    return NS(state=value, attributes=attributes)


def room(rid, devices=(), humidity=False):
    hum = NS(enabled=humidity, actuator=NS(entity_id=f"switch.{rid}_humidity") if humidity else None,
             controller_type="humidifier" if humidity else None)
    return NS(room_id=rid, name="Комната " + rid, devices=devices, humidity=hum)


def device(entity, control="device", role="fast_heat", function="heat"):
    return NS(entity_id=entity, control=control, device_class=NS(value="slow" if role=="slow_heat" else "fast"), function=function)


def scenario(rooms=(), snapshot=None, temperature_sources=(), humidity_sources=(), season="heat"):
    snapshot = snapshot or {}
    outdoor = NS(current_temperature=13, avg_24h_temperature=11.7, last_valid_at=None, stale=False, season=NS(value=season))
    config = NS(global_config=NS(night_mode="input_boolean.night", we_at_home="input_boolean.presence"),
                outdoor=NS(temperature_sources=temperature_sources, humidity_sources=humidity_sources), rooms=tuple(rooms))
    targets = {r.room_id: {"heat_day": 23, "heat_night": 20, "heat_away": 18, "heat_antifreeze": 10,
                           "cool_day": 25, "cool_night": 24, "cool_away": 28} for r in rooms}
    room_states = {r.room_id: NS(season=NS(value=season), current_temperature=22.5, target_temperature=20,
                                hvac_mode=season, hvac_action=NS(value="idle"),
                                effective_profile=NS(value="night")) for r in rooms}
    health = NS(climate_state="healthy", global_state="healthy", rooms={r.room_id: "healthy" for r in rooms})
    return build_topology(
        config=config, outdoor=outdoor, weather=None, room_states=room_states,
        humidity_states={}, health=health, snapshot=snapshot, app_version="0.1.33",
        started_at=NOW, observed_at=NOW, ha_connected=True, room_targets=targets,
    )


def plain(result):
    return "\n".join(row["prefix"] + "".join(part["text"] for part in row["parts"]) for row in result["lines"])


class SystemTreeTests(unittest.TestCase):
    def test_empty_rooms_no_fictional_resources(self):
        output = plain(scenario())
        self.assertIn("ROOMS · 0", output)
        for forbidden in ("BOILER", "SALUS", "PUMPS", "CIRCUITS", "VRF"):
            self.assertNotIn(forbidden, output)

    def test_multiple_rooms_follow_yaml_order(self):
        output = plain(scenario((room("livingroom"), room("спальня"), room("balcony"))))
        self.assertIn("ROOMS · 3", output)
        self.assertLess(output.index("Комната livingroom"), output.index("Комната спальня"))
        self.assertLess(output.index("Комната спальня"), output.index("Комната balcony"))

    def test_hardware_climate_uses_real_attributes_and_more_info(self):
        r = room("livingroom", [device("climate.wall_thermostat")])
        t = scenario((r,), snapshot={"climate.wall_thermostat": state("heat", friendly_name="Радиатор",
                     hvac_action="idle", current_temperature=22.2, temperature=20)})
        output = plain(t)
        self.assertIn("HARDWARE", output)
        self.assertIn("🌡️ 22.2°C / 20.0°C", output)
        self.assertIn("HEAT · IDLE", output)
        self.assertTrue(any(p.get("entity_id")=="climate.wall_thermostat"
                            for l in t["lines"] for p in l["parts"]))

    def test_reversible_climate_displays_heat_and_cool_capability(self):
        r = room("bedroom", [device("climate.bedroom_ac", control="app", function="heat_cool")])
        tree = plain(scenario((r,), snapshot={"climate.bedroom_ac": state("heat", hvac_action="idle")}))
        self.assertIn("FAST HEAT/COOL · VIRTUAL", tree)
        self.assertIn("🔥 HEAT · IDLE", tree)

    def test_cooling_device_has_cold_emoji(self):
        r = room("cool", [device("climate.cooler", control="app", function="cool")])
        output = plain(scenario((r,), snapshot={"climate.cooler": state("cool", hvac_action="cooling")}, season="cool"))
        self.assertIn("❄️ climate.cooler", output)
        self.assertIn("❄️ COOL · COOLING", output)

    def test_switch_never_invents_hvac_action(self):
        r = room("bedroom", [device("switch.valve", control="app")])
        output = plain(scenario((r,), snapshot={"switch.valve": state("on")}))
        self.assertIn("VIRTUAL", output)
        self.assertIn("🔌 ON", output)
        self.assertNotIn("HEATING", output)

    def test_different_outdoor_priorities_do_not_merge(self):
        output = plain(scenario(temperature_sources=("weather.primary", "sensor.backup"),
                    humidity_sources=("weather.primary", "sensor.hum_backup"),
                    snapshot={"weather.primary": state("sunny", temperature=11.5, humidity=39),
                              "sensor.backup": state("12.2"), "sensor.hum_backup": state("42")}))
        self.assertIn("TEMPERATURE SOURCES", output)
        self.assertIn("HUMIDITY SOURCES", output)
        self.assertIn("sensor.backup · 🌡️ 12.2°C", output)
        self.assertIn("sensor.hum_backup · 💧 42.0%", output)
        self.assertIn("💧 sensor.hum_backup", output)

    def test_missing_physical_device_not_healthy(self):
        r = room("lab", [device("climate.offline")])
        output = plain(scenario((r,), snapshot={"climate.offline": state("unavailable")}))
        self.assertIn("climate.offline · ⚪ UNKNOWN", output)

    def test_cool_no_antifreeze_and_off_no_targets(self):
        r = room("lab")
        self.assertIn("🎯 ☀️", plain(scenario((r,), season="cool")))
        self.assertNotIn("🛡️", plain(scenario((r,), season="cool")))
        self.assertNotIn("🎯 ☀️", plain(scenario((r,), season="off")))

    def test_humidity_child(self):
        r = room("lab", humidity=True)
        output = plain(scenario((r,), snapshot={"switch.lab_humidity": state("off")}))
        self.assertIn("Humidifier", output)
        self.assertIn("VIRTUAL · OFF", output)

    def test_approved_tree_emoji_and_compact_targets(self):
        r = room("bedroom", [device("climate.bedroom_ac", control="app", function="heat_cool")])
        output = plain(scenario((r,), season="heat"))
        self.assertIn("🔥 Season: HEAT", output)
        self.assertIn("📊 Average 24h: 11.7°C", output)
        self.assertIn("🎯 ☀️23 · 🌙20 · 🧳18 · 🛡️10°C", output)
        self.assertIn("💤 IDLE · 🌙 NIGHT", output)

    def test_native_markdown_card_uses_only_precomputed_lines(self):
        from pathlib import Path
        import yaml
        card_path = Path(__file__).resolve().parents[1] / "examples/lovelace/dh_climate_system_tree.yaml"
        card = yaml.safe_load(card_path.read_text(encoding="utf-8"))
        self.assertEqual("markdown", card["type"])
        self.assertEqual(["sensor.dh_climate_app_topology"], card["entity_id"])
        self.assertEqual(12, card["grid_options"]["columns"])
        self.assertIn("<pre style=", card["content"])
        self.assertIn('<a href="?more-info-entity-id=', card["content"])
        self.assertIn("part['entity_id'] | urlencode", card["content"])
        self.assertIn("part['text'] | e", card["content"])
        self.assertNotIn("states.sensor", card["content"])

    def test_native_markdown_more_info_links_and_escaping(self):
        from pathlib import Path
        from jinja2 import Environment
        import yaml

        card_path = Path(__file__).resolve().parents[1] / "examples/lovelace/dh_climate_system_tree.yaml"
        card = yaml.safe_load(card_path.read_text(encoding="utf-8"))
        sample = [
            {"prefix": "├─ ", "parts": [
                {"text": "☀️ <unsafe> & More Info", "entity_id": "climate.bedroom_ac"},
                {"text": " · MODE: HEAT"},
            ]},
            {"prefix": "└─ ", "parts": [
                {"text": "sensor.outdoor", "entity_id": "sensor.outdoor"}
            ]},
        ]
        output = Environment(autoescape=True).from_string(card["content"]).render(
            state_attr=lambda e, attr: sample,
            is_state=lambda e, value: value == "ready",
        )
        self.assertIn('href="?more-info-entity-id=climate.bedroom_ac"', output)
        self.assertIn('href="?more-info-entity-id=sensor.outdoor"', output)
        self.assertIn("&lt;unsafe&gt; &amp; More Info", output)
        self.assertIn("\n└─ ", output)
        self.assertEqual(2, output.count("<a href="))

    def test_discovery_stable_unique_id(self):
        topic, payload = topology_discovery_payload("0.1.33")
        self.assertEqual("homeassistant/sensor/dh_climate_app_topology/config", topic)
        self.assertEqual("sensor.dh_climate_app_topology", payload["default_entity_id"])
        self.assertEqual(TOPOLOGY_ATTRIBUTES_TOPIC, payload["json_attributes_topic"])
        self.assertEqual(TOPOLOGY_STATE_TOPIC, payload["state_topic"])

    def test_mqtt_size_guard_never_emits_truncated_tree(self):
        class Bridge:
            def __init__(self):
                self.sent = {}
            def publish(self, topic, payload, *, retain, force=False):
                self.sent[topic] = payload
                return True
        facade = object.__new__(ClimateMqttFacade)
        facade.bridge = Bridge()
        facade.publish_topology({"schema_version": 1, "lines": []})
        self.assertEqual("ready", facade.bridge.sent[TOPOLOGY_STATE_TOPIC])
        facade.publish_topology({"schema_version": 1, "lines": [{"prefix": "", "parts": [{"text": "x"*33_000}]}]})
        self.assertEqual("too_large", facade.bridge.sent[TOPOLOGY_STATE_TOPIC])
        self.assertNotIn("x"*1000, facade.bridge.sent[TOPOLOGY_ATTRIBUTES_TOPIC])


if __name__ == "__main__":
    unittest.main()
