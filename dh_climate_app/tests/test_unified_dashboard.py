"""Lovelace v0.2 unified dashboard: repository contract and safe dynamic UI."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import jinja2
import yaml


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "lovelace"


def read(name: str):
    return yaml.safe_load((EXAMPLES / name).read_text(encoding="utf-8"))


class UnifiedDashboardTests(unittest.TestCase):
    def test_exact_views_and_existing_system_tree_url(self):
        data = read("dh_climate_dashboard_0.2.yaml")
        self.assertEqual(
            ["system", "climate", "outdoor", "admin"],
            [view["path"] for view in data["views"]],
        )
        system = data["views"][0]
        self.assertEqual("panel", system["type"])
        tree = system["cards"][0]
        self.assertEqual("markdown", tree["type"])
        self.assertIn("./?more-info-entity-id=", tree["content"])
        self.assertNotIn('href="?more-info-entity-id=', tree["content"])
        self.assertIn("sensor.dh_climate_app_topology", tree["entity_id"])

    def test_outdoor_and_admin_use_existing_runtime_facts(self):
        data = read("dh_climate_dashboard_0.2.yaml")
        text = json.dumps(data["views"], ensure_ascii=False)
        for entity in (
            "sensor.dh_climate_app_outdoor_temperature_raw",
            "sensor.dh_climate_app_outdoor_temperature_avg24",
            "sensor.dh_climate_app_outdoor_humidity",
            "binary_sensor.dh_climate_app_problem",
            "sensor.dh_climate_app_version",
            "number.dh_climate_app_window_open_delay_seconds",
        ):
            self.assertIn(entity, text)
        # No fabricated product-card state or unguarded destructive button.
        self.assertNotIn("sensor.dh_climate_app_card", text)
        self.assertNotIn("button.dh_climate_app_delete_telemetry", text)
        self.assertNotIn("tojson", text)

    def test_area_grouping_labs_excluded_and_native_features(self):
        data = read("dh_climate_dashboard_0.2.yaml")
        indoor = data["views"][1]
        self.assertEqual("panel", indoor["type"])
        card = indoor["cards"][0]
        self.assertEqual("custom:auto-entities", card["type"])
        template = jinja2.Environment().from_string(card["filter"]["template"])
        climate = [
            ("climate.dh_climate_app_season", None),
            ("climate.dh_climate_app_livingroom", "Гостиная"),
            ("climate.dh_climate_app_bedroom", "Спальня"),
            ("climate.dh_climate_app_lab_cool", "LAB"),
            ("climate.dh_climate_app_spare", "Гостиная"),
        ]
        humidifier = [
            ("humidifier.dh_climate_app_livingroom", "Гостиная"),
            ("humidifier.dh_climate_app_lab_humidifier", "LAB"),
        ]
        areas = dict(climate + humidifier)
        states = SimpleNamespace(
            climate=[SimpleNamespace(entity_id=id_) for id_, _ in climate],
            humidifier=[SimpleNamespace(entity_id=id_) for id_, _ in humidifier],
        )
        cards = json.loads(template.render(
            states=states, area_name=lambda entity: areas.get(entity),
        ))
        self.assertEqual(["Гостиная", "Спальня"], [
            group["cards"][0]["heading"] for group in cards
        ])
        self.assertEqual([4, 2], [len(group["cards"]) for group in cards])
        self.assertIn("target-temperature", json.dumps(cards))
        self.assertIn("target-humidity", json.dumps(cards))
        self.assertNotIn("lab_", json.dumps(cards))
        self.assertEqual([], json.loads(template.render(
            states=SimpleNamespace(climate=[], humidifier=[]),
            area_name=lambda entity: None,
        )))

    def test_additive_overlay_does_not_repeat_first_view(self):
        addon = read("dh_climate_dashboard_add_views_0.2.yaml")
        self.assertEqual(
            ["climate", "outdoor", "admin"],
            [view["path"] for view in addon["views"]],
        )
        spec = importlib.util.spec_from_file_location(
            "dh_dashboard_merge", ROOT / "tools" / "merge_dh_climate_dashboard.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source = {
            "title": "DH Climate",
            "views": [
                {"type": "panel", "cards": [{"type": "markdown", "content": "OLD LIVE SYSTEM TREE"}]},
                {"path": "outdoor", "type": "panel", "cards": []},
                {"path": "aqara-w500", "type": "sections", "sections": [{"type": "grid", "cards": []}]},
                {"path": "climate", "type": "sections", "sections": []},
            ],
        }
        combined, replaced, added = module.merge(source, addon)
        self.assertEqual(["climate", "outdoor"], replaced)
        self.assertEqual(["admin"], added)
        self.assertEqual(5, len(combined["views"]))
        self.assertEqual(source["views"][0], combined["views"][0])
        self.assertEqual(source["views"][2], combined["views"][2])
        with self.assertRaises(ValueError):
            module.merge(source, {"views": [{"path": "aqara-w500"}]})


if __name__ == "__main__":
    unittest.main()
