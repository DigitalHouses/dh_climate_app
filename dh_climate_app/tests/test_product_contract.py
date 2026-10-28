from __future__ import annotations

from pathlib import Path
import re
import unittest

import yaml


APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent


class ProductContractTests(unittest.TestCase):
    def test_release_version_is_single_source_contract(self) -> None:
        config = yaml.safe_load(
            (APP_ROOT / "config.yaml").read_text(encoding="utf-8")
        )
        version = str(config["version"])
        dockerfile = (APP_ROOT / "Dockerfile").read_text(encoding="utf-8")
        changelog = (APP_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        pyproject = (APP_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn(f'ARG BUILD_VERSION="{version}"', dockerfile)
        self.assertIn(f"## {version}", changelog)
        self.assertIn(f'version = "{version}"', pyproject)

    def test_repository_contract_exists(self) -> None:
        repository = yaml.safe_load(
            (REPO_ROOT / "repository.yaml").read_text(encoding="utf-8")
        )
        self.assertTrue(repository["name"])
        self.assertEqual(
            "https://github.com/DigitalHouses/dh_climate_app",
            repository["url"],
        )
        self.assertTrue(repository["maintainer"])

    def test_haos_product_shell_exists(self) -> None:
        required = [
            "digitalhouses.app",
            "config.yaml",
            "Dockerfile",
            "README.md",
            "CHANGELOG.md",
            "rootfs/run.sh",
            "translations/en.yaml",
            "translations/ru.yaml",
        ]
        for path in required:
            self.assertTrue((APP_ROOT / path).exists(), path)

        marker = (APP_ROOT / "digitalhouses.app").read_text(encoding="utf-8")
        self.assertIn("type = haos_addon", marker)

    def test_supervisor_exposes_topology_not_room_targets(self) -> None:
        config = yaml.safe_load((APP_ROOT / "config.yaml").read_text(encoding="utf-8"))
        schema = config["schema"]
        self.assertIn("outdoor", schema)
        self.assertIn("temperature_sources", schema["outdoor"])
        self.assertIn("devices", schema["rooms"][0])
        self.assertEqual([{"entity": "str", "role": "list(slow_heat|fast_heat|fast_cool)", "device_type": "list(virtual|hardware)", "resource": "list(home_heating|vrf|independent)?", "screed_sensor_unavailable": "list(open|closed)?", "actuator": "list(normal_open|normal_closed)?", "temperature_sensor": "str?", "reversible": "bool?"}], schema["rooms"][0]["devices"])
        self.assertIn("heating_source", schema)
        self.assertIn("vrf", schema)
        self.assertIn("resources", schema)
        self.assertNotIn("temperature_hysteresis", schema)
        for key in ("hysteresis", "heat_threshold_default", "cool_threshold_default",
                    "ac_min_outdoor_temperature", "outdoor_temperature_ema_minutes"):
            self.assertNotIn(key, schema)
            self.assertNotIn(key, config["options"])
        for key in ("heat_day", "heat_night", "heat_away", "heat_antifreeze",
                    "cool_day", "cool_night", "cool_away", "humidity_target"):
            self.assertNotIn(key, schema["rooms"][0])

    def test_slug_is_stable(self) -> None:
        config = yaml.safe_load(
            (APP_ROOT / "config.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual("dh_climate_app", config["slug"])

    def test_haos_build_contract(self) -> None:
        config = yaml.safe_load(
            (APP_ROOT / "config.yaml").read_text(encoding="utf-8")
        )
        dockerfile = (APP_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertEqual("experimental", config["stage"])
        self.assertEqual(["amd64", "aarch64"], config["arch"])
        self.assertIn("FROM ghcr.io/home-assistant/base:latest", dockerfile)
        self.assertIn('ARG BUILD_ARCH="amd64"', dockerfile)
        self.assertIn('io.hass.arch="${BUILD_ARCH}"', dockerfile)
        self.assertNotIn("TARGETARCH", dockerfile)

    def test_release_workflow_uses_canonical_product_identity(self) -> None:
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "release.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("digitalhouses_climate_app-v", workflow)
        self.assertIn(
            "ghcr.io/digitalhouses/digitalhouses_climate_app:",
            workflow,
        )
        self.assertIn("org.opencontainers.image.revision", workflow)
        self.assertIn("steps.build.outputs.digest", workflow)


if __name__ == "__main__":
    unittest.main()
