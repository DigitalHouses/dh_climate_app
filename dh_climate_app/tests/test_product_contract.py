from __future__ import annotations

from pathlib import Path
import re
import unittest


APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent


class ProductContractTests(unittest.TestCase):
    def test_release_version_is_single_source_contract(self) -> None:
        config = (APP_ROOT / "config.yaml").read_text(encoding="utf-8")
        dockerfile = (APP_ROOT / "Dockerfile").read_text(encoding="utf-8")
        changelog = (APP_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        config_match = re.search(r"^version:\s*([^\s]+)\s*$", config, re.MULTILINE)
        self.assertIsNotNone(config_match)
        assert config_match is not None
        version = config_match.group(1)

        self.assertIn(f'ARG BUILD_VERSION="{version}"', dockerfile)
        self.assertRegex(changelog, rf"(?m)^##\s+{re.escape(version)}(?:\s|$)")

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

    def test_slug_is_stable(self) -> None:
        config = (APP_ROOT / "config.yaml").read_text(encoding="utf-8")
        self.assertRegex(config, r"(?m)^slug:\s*dh_climate_app\s*$")

    def test_immutable_delivery_contract(self) -> None:
        config = (APP_ROOT / "config.yaml").read_text(encoding="utf-8")
        workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(
            encoding="utf-8"
        )
        self.assertRegex(
            config,
            r"(?m)^image:\s*ghcr\.io/digitalhouses/digitalhouses-climate-app\s*$",
        )
        self.assertIn("digitalhouses_climate_app-v*", workflow)
        self.assertIn(
            "ghcr.io/digitalhouses/digitalhouses-climate-app:",
            workflow,
        )
        self.assertIn("context: ./dh_climate_app", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("contents: write", workflow)
        self.assertNotIn("workflow_dispatch:", workflow)


if __name__ == "__main__":
    unittest.main()
