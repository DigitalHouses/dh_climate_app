#!/usr/bin/env python3
"""One-time, explicit offline seed of already known SLOW screed targets.

Never infers targets from hardware or room air. On --apply creates a SQLite
backup and INSERT OR IGNORE; no existing profile is overwritten.
Run ONLY after cold App stop and backup, with the actual legacy slow_target
values confirmed from the old Supervisor options.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import sys


ROOM_ID = re.compile(r"^[a-z0-9][a-z0-9_]*$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument(
        "--room", action="append", required=True, metavar="ROOM_ID=TEMP",
        help="Exact old slow_target for room, e.g. bedroom=27",
    )
    parser.add_argument("--apply", action="store_true", help="Write seed only if missing")
    parser.add_argument(
        "--confirm-offline", default="",
        help="Required literal STOPPED_BACKED_UP for any --apply",
    )
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error("database does not exist; no database is created")
    values: dict[str, float] = {}
    for expression in args.room:
        if "=" not in expression:
            parser.error(f"invalid --room format: {expression!r}")
        room_id, raw = expression.split("=", 1)
        if not ROOM_ID.fullmatch(room_id) or room_id in values:
            parser.error(f"invalid/duplicate room_id: {room_id!r}")
        try:
            target = float(raw)
        except ValueError:
            parser.error(f"invalid float: {raw!r}")
        if not 5.0 <= target <= 45.0:
            parser.error(f"temperature outside 5..45°C for {room_id}")
        values[room_id] = target
    if args.apply and args.confirm_offline != "STOPPED_BACKED_UP":
        parser.error("--apply requires --confirm-offline STOPPED_BACKED_UP")
    with sqlite3.connect(f"file:{args.db.resolve()}?mode=rw", uri=True) as db:
        db.row_factory = sqlite3.Row
        healthy = db.execute("PRAGMA integrity_check").fetchone()[0]
        if healthy != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {healthy}")
        rooms = {
            r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "room_runtime" not in rooms:
            raise RuntimeError("existing room_runtime missing; wrong database")
        known = {
            r[0] for r in db.execute("SELECT room_id FROM room_runtime")
        }
        if not set(values).issubset(known):
            raise RuntimeError(
                f"unknown configured room(s): {sorted(set(values) - known)}"
            )
        existing = (
            {
                (r["room_id"], r["profile"]): r["target"]
                for r in db.execute(
                    "SELECT room_id, profile, target FROM slow_room_targets"
                )
            }
            if "slow_room_targets" in rooms else {}
        )
        pending = [
            (room, profile, target)
            for room, target in values.items()
            for profile in ("day", "night", "away")
            if (room, profile) not in existing
        ]
        for room, target in values.items():
            print(
                f"{room}: old slow_target={target}; "
                f"existing={{day:{existing.get((room, 'day'))}, "
                f"night:{existing.get((room, 'night'))}, "
                f"away:{existing.get((room, 'away'))}}}"
            )
        if "slow_room_targets" not in rooms:
            print("SLOW profile table absent in old DB; will create on --apply")
        print(f"missing profiles to seed: {len(pending)}")
        if not args.apply:
            print("DRY-RUN ONLY: zero SQLite changes")
            return 0
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = args.db.with_name(args.db.name + f".before-slow-seed-{timestamp}.bak")
        if backup.exists():
            raise RuntimeError(f"backup already exists: {backup}")
        with sqlite3.connect(backup) as bdb:
            db.backup(bdb)
        print(f"SQLite consistent backup: {backup}")
        with db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS slow_room_targets (
                    room_id TEXT NOT NULL,
                    profile TEXT NOT NULL CHECK (profile IN ('day', 'night', 'away')),
                    target REAL NOT NULL,
                    PRIMARY KEY (room_id, profile)
                )"""
            )
            db.executemany(
                """INSERT OR IGNORE INTO slow_room_targets(
                       room_id, profile, target) VALUES (?,?,?)""",
                pending,
            )
        print("APPLIED: INSERT OR IGNORE; existing profiles preserved")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (sqlite3.Error, OSError, RuntimeError) as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        sys.exit(2)
