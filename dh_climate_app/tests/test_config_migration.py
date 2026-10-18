from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dh_climate_app.config import parse_options
from dh_climate_app.config_migration import build_migrated_options, migrate_supervisor_options
from dh_climate_app.core import Profile, Season
from dh_climate_app.persistence import StateStore
from test_config import options


class ConfigMigrationTests(unittest.TestCase):
    def test_legacy_seed_then_cleanup_keeps_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db = StateStore(Path(directory) / "dh_climate.db")
            raw = options()
            raw["rooms"][0]["heat_away"] = 19.5
            raw["rooms"][0]["humidity_target"] = 57.0
            db.initialize(parse_options(raw))
            db.set_room_target("living_room", Season.HEAT, Profile.AWAY, 17.5)
            migrated, exceptions = build_migrated_options(raw)
            self.assertEqual((), exceptions)
            self.assertNotIn("heat_away", migrated["rooms"][0])
            self.assertNotIn("humidity_target", migrated["rooms"][0])
            self.assertNotIn("heat_threshold_default", migrated)
            self.assertEqual("switch.radiator", migrated["rooms"][0]["fast_heat"])
            db.initialize(parse_options(migrated))
            self.assertEqual(17.5, db.get_room_target("living_room", Season.HEAT, Profile.AWAY))
            self.assertEqual(57.0, db.get_humidity_target("living_room"))

    def test_custom_ema_and_ac_protection_are_not_silently_changed(self) -> None:
        raw = options()
        raw["ac_min_outdoor_temperature"] = -15.0
        raw["outdoor_temperature_ema_minutes"] = 30.0
        migrated, exceptions = build_migrated_options(raw)
        self.assertEqual(raw, migrated)
        self.assertEqual(
            ("ac_min_outdoor_temperature", "outdoor_temperature_ema_minutes"),
            exceptions,
        )

    def test_supervisor_write_has_snapshot_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            raw = options()
            raw["hysteresis"] = 0.8
            path.write_text(json.dumps(raw), encoding="utf-8")
            payloads = []

            def sender(body: bytes):
                payloads.append(json.loads(body))
                return {"result": "ok", "data": {}}

            snapshot = Path(directory) / "old_options.json"
            self.assertTrue(migrate_supervisor_options(
                path, token="dummy", sender=sender, snapshot_path=snapshot,
            ))
            self.assertEqual(raw, json.loads(snapshot.read_text(encoding="utf-8")))
            cleaned = payloads[0]["options"]
            self.assertEqual(0.8, cleaned["temperature_hysteresis"])
            self.assertNotIn("hysteresis", cleaned)
            self.assertNotIn("heat_day", cleaned["rooms"][0])
            self.assertEqual(raw["rooms"][0]["name"], cleaned["rooms"][0]["name"])
            path.write_text(json.dumps(cleaned), encoding="utf-8")
            self.assertFalse(migrate_supervisor_options(
                path, token="dummy", sender=sender, snapshot_path=snapshot,
            ))
            self.assertEqual(1, len(payloads))

    def test_supervisor_rejection_preserves_original(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(json.dumps(options()), encoding="utf-8")
            snapshot = Path(directory) / "old.json"
            self.assertFalse(migrate_supervisor_options(
                path, token="dummy", snapshot_path=snapshot,
                sender=lambda data: {"result": "error", "message": "invalid"},
            ))
            self.assertTrue(snapshot.exists())


if __name__ == "__main__":
    unittest.main()
