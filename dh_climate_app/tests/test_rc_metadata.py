"""Pre-release constraints: safe UI probe and coherent RC metadata."""
from pathlib import Path
import unittest

import yaml

from dh_climate_app.config import parse_options


ROOT = Path(__file__).resolve().parents[2]


class ReleaseCandidateChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = yaml.safe_load(
            (ROOT / "dh_climate_app" / "config.yaml").read_text(encoding="utf-8")
        )
        cls.probe = yaml.safe_load(
            (ROOT / "dh_climate_schema_probe" / "config.yaml").read_text(encoding="utf-8")
        )

    def test_probe_schema_equals_main_app(self):
        self.assertEqual(self.manifest["schema"], self.probe["schema"])
        self.assertEqual(self.manifest["version"], self.probe["version"])
        self.assertNotEqual(self.manifest["slug"], self.probe["slug"])
        self.assertEqual(len(parse_options(self.probe["options"]).rooms), 2)

    def test_probe_has_no_actuator_permissions_or_runtime_code(self):
        for key in (
            "homeassistant_api", "hassio_api", "services", "devices",
            "host_network", "privileged", "ports", "ingress", "image",
        ):
            self.assertNotIn(key, self.probe, f"probe must not declare {key}")
        self.assertEqual(self.probe["boot"], "manual")
        dockerfile = (ROOT / "dh_climate_schema_probe" / "Dockerfile").read_text()
        self.assertNotIn("/app/dh_climate_app", dockerfile)
        self.assertNotIn("bashio::", dockerfile)

    def test_rc_does_not_change_release_marker(self):
        self.assertEqual(self.manifest["version"], "0.1.32-rc1")
        marker = (ROOT / "dh_climate_app" / "RELEASE").read_text().strip()
        self.assertEqual(marker, "digitalhouses_climate_app-v0.1.31")


if __name__ == "__main__":
    unittest.main()
