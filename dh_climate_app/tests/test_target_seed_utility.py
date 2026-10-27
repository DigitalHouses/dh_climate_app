"""Offline seed: dry-run immutable, backup-first, never overwrite targets."""
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from dh_climate_app.config import parse_options
from dh_climate_app.core import Profile
from dh_climate_app.persistence import StateStore
from test_target_topology import options


SCRIPT = Path(__file__).resolve().parents[1] / "tools/seed_slow_profiles.py"


class OfflineSeedTests(unittest.TestCase):
    def test_dry_run_and_apply_to_old_sqlite(self):
        with TemporaryDirectory() as root:
            db_path = Path(root) / "climate.db"
            store = StateStore(db_path)
            store.initialize(parse_options(options()))
            with store.connect() as db:
                db.execute("DROP TABLE slow_room_targets")

            command = [
                sys.executable, str(SCRIPT),
                "--db", str(db_path), "--room", "bedroom=27",
            ]
            dry = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, dry.returncode, dry.stderr)
            self.assertIn("DRY-RUN ONLY", dry.stdout)
            with sqlite3.connect(db_path) as conn:
                found = conn.execute(
                    "SELECT count(*) FROM sqlite_master "
                    "WHERE name='slow_room_targets'"
                ).fetchone()[0]
            self.assertEqual(0, found)

            rejected = subprocess.run(
                command + ["--apply"], capture_output=True, text=True,
            )
            self.assertNotEqual(0, rejected.returncode)
            applied = subprocess.run(
                command + [
                    "--apply", "--confirm-offline", "STOPPED_BACKED_UP",
                ], capture_output=True, text=True,
            )
            self.assertEqual(0, applied.returncode, applied.stderr)
            self.assertEqual(27.0, store.get_slow_target("bedroom", Profile.DAY))
            self.assertEqual(27.0, store.get_slow_target("bedroom", Profile.NIGHT))
            backups = list(Path(root).glob("climate.db.before-slow-seed-*.bak"))
            self.assertEqual(1, len(backups))

            store.set_slow_target("bedroom", Profile.NIGHT, 26.0)
            reapply = subprocess.run(
                command + [
                    "--apply", "--confirm-offline", "STOPPED_BACKED_UP",
                ], capture_output=True, text=True,
            )
            self.assertEqual(0, reapply.returncode, reapply.stderr)
            self.assertEqual(26.0, store.get_slow_target("bedroom", Profile.NIGHT))


if __name__ == "__main__":
    unittest.main()
