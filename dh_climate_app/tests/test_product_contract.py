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
        pyproject = (APP_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        config_match = re.search(r"^version:\s*([^\s]+)\s*$", config, re.MULTILINE)
        self.assertIsNotNone(config_match)
        assert config_match is not None
        version = config_match.group(1)

        self.assertIn(f'ARG BUILD_VERSION="{version}"', dockerfile)
        self.assertRegex(changelog, rf"(?m)^##\s+{re.escape(version)}(?:\s|$)")
        self.assertRegex(
            pyproject,
            rf'(?m)^version\s*=\s*"{re.escape(version)}"\s*
    def test_repository_contract_exists(self) -> None:
        repository = (REPO_ROOT / "repository.yaml").read_text(encoding="utf-8")
        self.assertRegex(repository, r"(?m)^name:\s*.+$")
        self.assertRegex(
            repository,
            r"(?m)^url:\s*https://github\.com/DigitalHouses/dh_climate_app\s*$",
        )
        self.assertRegex(repository, r"(?m)^maintainer:\s*.+$")

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

    def test_experimental_source_build_contract(self) -> None:
        config = (APP_ROOT / "config.yaml").read_text(encoding="utf-8")
        dockerfile = (APP_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertRegex(config, r"(?m)^stage:\s*experimental\s*$")
        self.assertNotRegex(config, r"(?m)^image:")
        self.assertIn("FROM ghcr.io/home-assistant/base:latest", dockerfile)
        self.assertIn('ARG BUILD_ARCH="amd64"', dockerfile)
        self.assertIn('io.hass.arch="${BUILD_ARCH}"', dockerfile)
        self.assertNotIn("TARGETARCH", dockerfile)
        self.assertRegex(
            config,
            r"(?ms)^arch:\s*\n\s*- amd64\s*\n\s*- aarch64\s*$",
        )


if __name__ == "__main__":
    unittest.main()
,
        )

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

    def test_experimental_source_build_contract(self) -> None:
        config = (APP_ROOT / "config.yaml").read_text(encoding="utf-8")
        dockerfile = (APP_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertRegex(config, r"(?m)^stage:\s*experimental\s*$")
        self.assertNotRegex(config, r"(?m)^image:")
        self.assertIn("FROM ghcr.io/home-assistant/base:latest", dockerfile)
        self.assertIn('ARG BUILD_ARCH="amd64"', dockerfile)
        self.assertIn('io.hass.arch="${BUILD_ARCH}"', dockerfile)
        self.assertNotIn("TARGETARCH", dockerfile)
        self.assertRegex(
            config,
            r"(?ms)^arch:\s*\n\s*- amd64\s*\n\s*- aarch64\s*$",
        )


if __name__ == "__main__":
    unittest.main()
