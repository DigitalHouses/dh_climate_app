"""Persistent, versioned manifest editor; no mutation of a running climate engine.

The Supervisor owns /data/options.json. This module never writes it.
A validated active manifest takes precedence only after an app restart.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .config import ConfigError, parse_options

MAX_MANIFEST_BYTES = 256 * 1024


class EditConflict(ValueError):
    pass


class EditValidation(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise EditValidation(f"Invalid manifest at {path.name}")
    return obj


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _canonical(value) + b"\n"
    if len(data) > MAX_MANIFEST_BYTES:
        raise EditValidation("Manifest exceeds 256 KiB")
    fd, name = tempfile.mkstemp(prefix=".dh_climate_", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            os.chmod(name, 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        # Make the rename durable on filesystems supporting directory fsync.
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _manifest_options(obj: dict[str, Any]) -> dict[str, Any]:
    if obj.get("schema_version") != 1 or not isinstance(obj.get("options"), dict):
        raise EditValidation("Invalid manifest schema")
    return obj["options"]


def _validate(options: Any) -> dict[str, Any]:
    if not isinstance(options, dict):
        raise EditValidation("Options must be a JSON object")
    if len(_canonical(options)) > MAX_MANIFEST_BYTES:
        raise EditValidation("Options exceed 256 KiB")
    try:
        config = parse_options(options)
    except (ConfigError, ValueError, TypeError) as exc:
        raise EditValidation(str(exc)) from exc
    return {
        "rooms": len(config.rooms),
        "devices": sum(len(room.devices) for room in config.rooms),
        "temperature_sensors": sum(len(room.temperature_sensors) for room in config.rooms),
    }


class ManifestEditor:
    """Global optimistic-locking draft, explicit validation and restart apply.

    A draft is shared by administrators; if another admin saves, the first
    writer gets a conflict rather than losing edits.
    """

    def __init__(self, data_dir: Path, supervisor_options: dict[str, Any]):
        self.data_dir = Path(data_dir)
        self.active_path = self.data_dir / "dh_climate_manifest.json"
        self.draft_path = self.data_dir / "dh_climate_manifest.draft.json"
        self.previous_path = self.data_dir / "dh_climate_manifest.previous.json"
        self.supervisor_options = deepcopy(supervisor_options)
        self._lock = asyncio.Lock()
        self.running_options = deepcopy(self._active_options())
        self.running_hash = _digest(self.running_options)

    def _active_options(self) -> dict[str, Any]:
        active = _load(self.active_path)
        if active is not None:
            options = _manifest_options(active)
            # Invalid active manifest must stop startup, not silently start
            # actuators with an unexpected alternative topology.
            _validate(options)
            return deepcopy(options)
        _validate(self.supervisor_options)
        return deepcopy(self.supervisor_options)

    def effective_on_startup(self) -> dict[str, Any]:
        return deepcopy(self.running_options)

    def _active_hash(self) -> str:
        return _digest(self._active_options())

    def _get_draft(self, base_hash: str) -> dict[str, Any] | None:
        draft = _load(self.draft_path)
        if draft is None:
            return None
        if draft.get("schema_version") != 1 or not isinstance(draft.get("options"), dict):
            raise EditValidation("Invalid stored draft")
        if draft.get("base_hash") != base_hash:
            raise EditConflict("Draft is stale; configuration has changed")
        if type(draft.get("revision")) is not int or draft["revision"] < 1:
            raise EditValidation("Invalid draft revision")
        return draft

    def _state(self) -> dict[str, Any]:
        base = self._active_options()
        hash_ = _digest(base)
        draft = self._get_draft(hash_)
        pending = hash_ != self.running_hash
        return {
            "options": deepcopy(draft["options"] if draft else base),
            "base_hash": hash_,
            "revision": draft["revision"] if draft else 0,
            "dirty": draft is not None,
            "pending_restart": pending,
            "author_id": draft.get("author_id") if draft else None,
        }

    async def state(self) -> dict[str, Any]:
        async with self._lock:
            return self._state()

    def _check(self, base_hash: Any, revision: Any) -> dict[str, Any]:
        state = self._state()
        if not isinstance(base_hash, str) or base_hash != state["base_hash"]:
            raise EditConflict("Configuration changed; refresh the editor")
        if type(revision) is not int or revision != state["revision"]:
            raise EditConflict("Draft changed; refresh the editor")
        if state["pending_restart"]:
            raise EditConflict("Restart DH Climate App before further edits")
        return state

    async def save(self, *, options: Any, base_hash: Any,
                   revision: Any, author_id: str) -> dict[str, Any]:
        if not isinstance(options, dict):
            raise EditValidation("options must be an object")
        if len(_canonical(options)) > MAX_MANIFEST_BYTES:
            raise EditValidation("Options exceed 256 KiB")
        async with self._lock:
            state = self._check(base_hash, revision)
            new_revision = state["revision"] + 1
            _atomic_json(self.draft_path, {
                "schema_version": 1, "options": options, "base_hash": base_hash,
                "revision": new_revision, "author_id": author_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            return self._state()

    async def validate(self, *, base_hash: Any, revision: Any) -> dict[str, Any]:
        async with self._lock:
            state = self._check(base_hash, revision)
            if not state["dirty"]:
                raise EditValidation("Save a draft before validation")
            return _validate(state["options"])

    async def apply(self, *, base_hash: Any, revision: Any) -> dict[str, Any]:
        async with self._lock:
            state = self._check(base_hash, revision)
            if not state["dirty"]:
                raise EditValidation("No draft to apply")
            summary = _validate(state["options"])
            previous = _load(self.active_path)
            if previous is not None:
                _atomic_json(self.previous_path, previous)
            else:
                _atomic_json(self.previous_path, {
                    "schema_version": 1, "options": self.supervisor_options,
                    "origin": "supervisor",
                })
            _atomic_json(self.active_path, {
                "schema_version": 1, "options": state["options"],
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "parent_hash": base_hash,
            })
            self.draft_path.unlink(missing_ok=True)
            return {"summary": summary, "pending_restart": True,
                    "base_hash": self._active_hash()}

    async def discard(self, *, base_hash: Any, revision: Any) -> dict[str, Any]:
        async with self._lock:
            self._check(base_hash, revision)
            self.draft_path.unlink(missing_ok=True)
            return self._state()
