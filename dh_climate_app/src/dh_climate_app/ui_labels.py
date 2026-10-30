"""Presentation-only names for the Explorer.

The UI label store deliberately has no relationship with the climate
configuration manifest or actuator control. Changes are immediate and do not
require Climate Engine restarts.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

from .manifest import _atomic_json, EditConflict, EditValidation

_KEY = re.compile(
    r"^(?:room:[a-z][a-z0-9_]*|"
    r"entity:(?:sensor|binary_sensor|climate|switch|weather|number|humidifier)\.[a-z0-9_]+|"
    r"resource:(?:boiler|central_heating|vrf)|"
    r"part:(?:boiler|central_heating|vrf):(?:pumps|circuits):[a-z][a-z0-9_]*)$"
)


class UILabels:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "dh_climate_ui_labels.json"
        self._lock = asyncio.Lock()
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "revision": 0, "labels": {}}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise EditValidation("Invalid UI labels schema")
        labels = raw.get("labels")
        if not isinstance(labels, dict) or type(raw.get("revision")) is not int:
            raise EditValidation("Invalid UI labels data")
        for key, values in labels.items():
            self._check(key, values)
        return raw

    @staticmethod
    def _check(key: Any, values: Any) -> None:
        if not isinstance(key, str) or _KEY.fullmatch(key) is None:
            raise EditValidation("Invalid object key")
        if not isinstance(values, dict) or set(values) - {"ru", "en"}:
            raise EditValidation("Invalid language keys")
        for value in values.values():
            if not isinstance(value, str) or len(value) > 120 or any(
                ord(ch) < 32 for ch in value
            ):
                raise EditValidation("UI names must be printable text up to 120 characters")

    async def state(self) -> dict[str, Any]:
        async with self._lock:
            return deepcopy(self._state)

    async def save(self, *, key: Any, names: Any, revision: Any) -> dict[str, Any]:
        self._check(key, names)
        if type(revision) is not int:
            raise EditValidation("Invalid UI labels revision")
        async with self._lock:
            if revision != self._state["revision"]:
                raise EditConflict("Names changed; refresh before saving")
            next_state = deepcopy(self._state)
            values = {lang: text.strip() for lang, text in names.items() if text.strip()}
            if values:
                next_state["labels"][key] = values
            else:
                next_state["labels"].pop(key, None)
            next_state["revision"] += 1
            _atomic_json(self.path, next_state)
            self._state = next_state
            return deepcopy(self._state)
