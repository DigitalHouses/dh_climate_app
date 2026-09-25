from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from typing import Iterator

from .config import AppConfig
from .core import HvacAction, Profile, Sample, Season


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SeasonThresholds:
    heat: float
    cool: float


class StateStore:
    """Small durable state store. It does not contain business orchestration."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self, config: AppConfig) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS season_settings (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    heat_threshold REAL NOT NULL,
                    cool_threshold REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS outdoor_samples (
                    kind TEXT NOT NULL CHECK (kind IN ('temperature', 'humidity')),
                    observed_at TEXT NOT NULL,
                    value REAL NOT NULL,
                    source_name TEXT NOT NULL,
                    PRIMARY KEY (kind, observed_at)
                );

                CREATE INDEX IF NOT EXISTS ix_outdoor_samples_kind_time
                    ON outdoor_samples(kind, observed_at);

                CREATE TABLE IF NOT EXISTS room_targets (
                    room_id TEXT NOT NULL,
                    season TEXT NOT NULL CHECK (season IN ('heat', 'cool')),
                    profile TEXT NOT NULL CHECK (
                        profile IN ('day', 'night', 'away', 'antifreeze')
                    ),
                    target REAL NOT NULL,
                    PRIMARY KEY (room_id, season, profile)
                );

                CREATE TABLE IF NOT EXISTS room_runtime (
                    room_id TEXT PRIMARY KEY,
                    previous_action TEXT NOT NULL DEFAULT 'off',
                    climate_control_enabled INTEGER NOT NULL DEFAULT 1
                        CHECK (climate_control_enabled IN (0, 1))
                );

                CREATE TABLE IF NOT EXISTS humidity_targets (
                    room_id TEXT PRIMARY KEY,
                    target REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS humidity_runtime (
                    room_id TEXT PRIMARY KEY,
                    previous_active INTEGER NOT NULL DEFAULT 0
                        CHECK (previous_active IN (0, 1)),
                    control_enabled INTEGER NOT NULL DEFAULT 1
                        CHECK (control_enabled IN (0, 1))
                );
                """
            )
            db.execute(
                """
                INSERT INTO metadata(key, value)
                VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(SCHEMA_VERSION),),
            )
            db.execute(
                """
                INSERT OR IGNORE INTO season_settings(
                    singleton, heat_threshold, cool_threshold
                ) VALUES (1, ?, ?)
                """,
                (
                    config.outdoor.heat_threshold_default,
                    config.outdoor.cool_threshold_default,
                ),
            )

            for room in config.rooms:
                db.execute(
                    """
                    INSERT OR IGNORE INTO room_runtime(
                        room_id, previous_action, climate_control_enabled
                    ) VALUES (?, 'off', 1)
                    """,
                    (room.room_id,),
                )
                for profile, target in room.targets.heat.items():
                    db.execute(
                        """
                        INSERT OR IGNORE INTO room_targets(
                            room_id, season, profile, target
                        ) VALUES (?, 'heat', ?, ?)
                        """,
                        (room.room_id, profile.value, float(target)),
                    )
                for profile, target in room.targets.cool.items():
                    db.execute(
                        """
                        INSERT OR IGNORE INTO room_targets(
                            room_id, season, profile, target
                        ) VALUES (?, 'cool', ?, ?)
                        """,
                        (room.room_id, profile.value, float(target)),
                    )
                if room.humidity.enabled and room.humidity.target_default is not None:
                    db.execute(
                        """
                        INSERT OR IGNORE INTO humidity_targets(room_id, target)
                        VALUES (?, ?)
                        """,
                        (room.room_id, float(room.humidity.target_default)),
                    )
                    db.execute(
                        """
                        INSERT OR IGNORE INTO humidity_runtime(
                            room_id, previous_active, control_enabled
                        ) VALUES (?, 0, 1)
                        """,
                        (room.room_id,),
                    )

    def integrity_check(self) -> bool:
        with self.connect() as db:
            row = db.execute("PRAGMA integrity_check").fetchone()
            return bool(row and row[0] == "ok")

    def get_season_thresholds(self) -> SeasonThresholds:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT heat_threshold, cool_threshold
                FROM season_settings
                WHERE singleton=1
                """
            ).fetchone()
        if row is None:
            raise RuntimeError("season_settings are not initialized")
        return SeasonThresholds(float(row["heat_threshold"]), float(row["cool_threshold"]))

    def set_season_thresholds(self, heat: float, cool: float) -> None:
        if heat >= cool:
            raise ValueError("heat threshold must be lower than cool threshold")
        with self.connect() as db:
            db.execute(
                """
                UPDATE season_settings
                SET heat_threshold=?, cool_threshold=?
                WHERE singleton=1
                """,
                (float(heat), float(cool)),
            )

    def add_outdoor_sample(
        self,
        *,
        kind: str,
        observed_at: datetime,
        value: float,
        source_name: str,
    ) -> None:
        if kind not in {"temperature", "humidity"}:
            raise ValueError("kind must be temperature or humidity")
        with self.connect() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO outdoor_samples(
                    kind, observed_at, value, source_name
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    kind,
                    observed_at.isoformat(),
                    float(value),
                    source_name,
                ),
            )

    def load_outdoor_samples(
        self,
        *,
        kind: str,
        since: datetime,
        include_previous: bool = False,
    ) -> list[Sample]:
        if kind not in {"temperature", "humidity"}:
            raise ValueError("kind must be temperature or humidity")
        with self.connect() as db:
            rows = list(
                db.execute(
                    """
                    SELECT observed_at, value
                    FROM outdoor_samples
                    WHERE kind=? AND observed_at>=?
                    ORDER BY observed_at
                    """,
                    (kind, since.isoformat()),
                ).fetchall()
            )
            if include_previous:
                previous = db.execute(
                    """
                    SELECT observed_at, value
                    FROM outdoor_samples
                    WHERE kind=? AND observed_at<?
                    ORDER BY observed_at DESC
                    LIMIT 1
                    """,
                    (kind, since.isoformat()),
                ).fetchone()
                if previous is not None:
                    rows.insert(0, previous)
        return [
            Sample(datetime.fromisoformat(str(row["observed_at"])), float(row["value"]))
            for row in rows
        ]

    def prune_outdoor_samples(
        self,
        *,
        now: datetime,
        keep: timedelta = timedelta(hours=25),
    ) -> int:
        """Prune old history but keep one baseline sample per metric.

        The baseline is required for time-weighted integration at the left
        edge of the rolling window when a sensor has not changed recently.
        """
        cutoff = (now - keep).isoformat()
        deleted = 0
        with self.connect() as db:
            for kind in ("temperature", "humidity"):
                baseline = db.execute(
                    """
                    SELECT max(observed_at)
                    FROM outdoor_samples
                    WHERE kind=? AND observed_at<?
                    """,
                    (kind, cutoff),
                ).fetchone()[0]
                if baseline is None:
                    continue
                cursor = db.execute(
                    """
                    DELETE FROM outdoor_samples
                    WHERE kind=? AND observed_at<? AND observed_at<>?
                    """,
                    (kind, cutoff, baseline),
                )
                deleted += int(cursor.rowcount)
        return deleted

    def get_room_target(
        self,
        room_id: str,
        season: Season,
        profile: Profile,
    ) -> float | None:
        if season is Season.OFF:
            return None
        with self.connect() as db:
            row = db.execute(
                """
                SELECT target
                FROM room_targets
                WHERE room_id=? AND season=? AND profile=?
                """,
                (room_id, season.value, profile.value),
            ).fetchone()
        return None if row is None else float(row["target"])

    def set_room_target(
        self,
        room_id: str,
        season: Season,
        profile: Profile,
        target: float,
    ) -> None:
        if season is Season.OFF:
            raise ValueError("OFF season does not have a room target")
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO room_targets(room_id, season, profile, target)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(room_id, season, profile)
                DO UPDATE SET target=excluded.target
                """,
                (room_id, season.value, profile.value, float(target)),
            )

    def get_previous_action(self, room_id: str) -> HvacAction:
        with self.connect() as db:
            row = db.execute(
                "SELECT previous_action FROM room_runtime WHERE room_id=?",
                (room_id,),
            ).fetchone()
        if row is None:
            return HvacAction.OFF
        try:
            return HvacAction(str(row["previous_action"]))
        except ValueError:
            return HvacAction.OFF

    def set_previous_action(self, room_id: str, action: HvacAction) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO room_runtime(room_id, previous_action)
                VALUES (?, ?)
                ON CONFLICT(room_id)
                DO UPDATE SET previous_action=excluded.previous_action
                """,
                (room_id, action.value),
            )

    def get_climate_control_enabled(self, room_id: str) -> bool:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT climate_control_enabled
                FROM room_runtime
                WHERE room_id=?
                """,
                (room_id,),
            ).fetchone()
        return True if row is None else bool(row["climate_control_enabled"])

    def set_climate_control_enabled(self, room_id: str, enabled: bool) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO room_runtime(room_id, climate_control_enabled)
                VALUES (?, ?)
                ON CONFLICT(room_id)
                DO UPDATE SET climate_control_enabled=excluded.climate_control_enabled
                """,
                (room_id, int(bool(enabled))),
            )

    def get_humidity_target(self, room_id: str) -> float | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT target FROM humidity_targets WHERE room_id=?",
                (room_id,),
            ).fetchone()
        return None if row is None else float(row["target"])

    def set_humidity_target(self, room_id: str, target: float) -> None:
        if not 0.0 <= float(target) <= 100.0:
            raise ValueError("humidity target must be between 0 and 100")
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO humidity_targets(room_id, target)
                VALUES (?, ?)
                ON CONFLICT(room_id)
                DO UPDATE SET target=excluded.target
                """,
                (room_id, float(target)),
            )


    def get_humidity_previous_active(self, room_id: str) -> bool:
        with self.connect() as db:
            row = db.execute(
                "SELECT previous_active FROM humidity_runtime WHERE room_id=?",
                (room_id,),
            ).fetchone()
        return False if row is None else bool(row["previous_active"])

    def set_humidity_previous_active(self, room_id: str, active: bool) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO humidity_runtime(room_id, previous_active, control_enabled)
                VALUES (?, ?, 1)
                ON CONFLICT(room_id)
                DO UPDATE SET previous_active=excluded.previous_active
                """,
                (room_id, int(bool(active))),
            )

    def get_humidity_control_enabled(self, room_id: str) -> bool:
        with self.connect() as db:
            row = db.execute(
                "SELECT control_enabled FROM humidity_runtime WHERE room_id=?",
                (room_id,),
            ).fetchone()
        return True if row is None else bool(row["control_enabled"])

    def set_humidity_control_enabled(self, room_id: str, enabled: bool) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO humidity_runtime(room_id, previous_active, control_enabled)
                VALUES (?, 0, ?)
                ON CONFLICT(room_id)
                DO UPDATE SET control_enabled=excluded.control_enabled
                """,
                (room_id, int(bool(enabled))),
            )
