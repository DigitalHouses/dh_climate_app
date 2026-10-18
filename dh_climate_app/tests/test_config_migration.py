from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dh_climate_app.config import parse_options
from dh_climate_app.config_migration import (
    build_migrated_options,
    build_supervisor_patch,
    migrate_supervisor_options,
)
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

    def test_supervisor_merging_needs_null_deletion_markers(self) -> None:
        raw = options()
        new, _ = build_migrated_options(raw)
        patch = build_supervisor_patch(raw, new)
        self.assertIsNone(patch["hysteresis"])
        self.assertIsNone(patch["heat_threshold_default"])
        self.assertIsNone(patch["outdoor_temperature_ema_minutes"])
        self.assertNotIn("heat_day", patch["rooms"][0])
        self.assertEqual(raw["rooms"][0]["temperature_sensors"], patch["rooms"][0]["temperature_sensors"])

    def test_runtime_file_filtered_but_supervisor_old_options_still_saved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            raw = options()
            raw["hysteresis"] = 0.8
            raw["temperature_hysteresis"] = 0.5  # Supervisor new schema default
            validated, _ = build_migrated_options(raw)
            path.write_text(json.dumps(validated), encoding="utf-8")

            stored = json.loads(json.dumps(raw))
            payloads = []

            def reader():
                return {"result": "ok", "data": {"options": stored}}

            def sender(body: bytes):
                patch = json.loads(body)["options"]
                payloads.append(patch)
                for key, value in patch.items():
                    if value is None:
                        stored.pop(key, None)
                    else:
                        stored[key] = value
                return {"result": "ok", "data": {}}

            snapshot = Path(directory) / "old_options.json"
            self.assertTrue(migrate_supervisor_options(
                path, token="dummy", reader=reader, sender=sender,
                snapshot_path=snapshot,
            ))
            self.assertEqual(raw, json.loads(snapshot.read_text(encoding="utf-8")))
            self.assertEqual(0.8, stored["temperature_hysteresis"])
            self.assertNotIn("hysteresis", stored)
            self.assertNotIn("heat_day", stored["rooms"][0])
            self.assertEqual(raw["rooms"][0]["name"], stored["rooms"][0]["name"])
            self.assertFalse(migrate_supervisor_options(
                path, token="dummy", reader=reader, sender=sender,
                snapshot_path=snapshot,
            ))
            self.assertEqual(1, len(payloads))

    def test_supervisor_did_not_delete_legacy_options_means_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            raw = options()
            path.write_text(json.dumps(raw), encoding="utf-8")
            snapshot = Path(directory) / "old.json"
            self.assertFalse(migrate_supervisor_options(
                path, token="dummy", snapshot_path=snapshot,
                reader=lambda: {"result": "ok", "data": {"options": raw}},
                sender=lambda data: {"result": "ok", "data": {}},
            ))
            self.assertTrue(snapshot.exists())

    def test_supervisor_rejection_preserves_original(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            raw = options()
            path.write_text(json.dumps(raw), encoding="utf-8")
            snapshot = Path(directory) / "old.json"
            self.assertFalse(migrate_supervisor_options(
                path, token="dummy", snapshot_path=snapshot,
                reader=lambda: {"result": "ok", "data": {"options": raw}},
                sender=lambda data: {"result": "error", "message": "invalid"},
            ))
            self.assertTrue(snapshot.exists())


if __name__ == "__main__":
    unittest.main()
