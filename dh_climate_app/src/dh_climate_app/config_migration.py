from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import DEFAULT_AC_MIN_OUTDOOR_TEMPERATURE, DEFAULT_OUTDOOR_EMA_MINUTES


LOGGER = logging.getLogger(__name__)
LEGACY_ROOM_KEYS = frozenset({
    "heat_day", "heat_night", "heat_away", "heat_antifreeze",
    "cool_day", "cool_night", "cool_away", "humidity_target",
})
LEGACY_GLOBAL_KEYS = frozenset({
    "hysteresis", "heat_threshold_default", "cool_threshold_default",
    "ac_min_outdoor_temperature", "outdoor_temperature_ema_minutes",
})


def build_migrated_options(raw: Mapping[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Remove obsolete seed values without changing device bindings or topology."""
    options = json.loads(json.dumps(raw))
    exceptions: list[str] = []
    for key, standard in (
        ("ac_min_outdoor_temperature", DEFAULT_AC_MIN_OUTDOOR_TEMPERATURE),
        ("outdoor_temperature_ema_minutes", DEFAULT_OUTDOOR_EMA_MINUTES),
    ):
        if key in options and float(options[key]) != standard:
            exceptions.append(key)

    # A nonstandard safety parameter is never silently converted to a default.
    if exceptions:
        return options, tuple(exceptions)

    if "hysteresis" in options:
        if (
            "temperature_hysteresis" not in options
            or options["temperature_hysteresis"] == 0.5
        ):
            options["temperature_hysteresis"] = options["hysteresis"]
    for key in LEGACY_GLOBAL_KEYS:
        options.pop(key, None)
    if isinstance(options.get("rooms"), list):
        for room in options["rooms"]:
            if isinstance(room, dict):
                for key in LEGACY_ROOM_KEYS:
                    room.pop(key, None)
    return options, ()


def build_supervisor_patch(
    raw: Mapping[str, Any],
    migrated: Mapping[str, Any],
) -> dict[str, Any]:
    """Supply explicit null tombstones: Supervisor merges option patches."""
    patch = json.loads(json.dumps(migrated))
    for key in LEGACY_GLOBAL_KEYS:
        if key in raw and key not in migrated:
            patch[key] = None
    # The full rooms array replaces its old entries, removing old target fields.
    return patch


def _supervisor_request(token: str, method: str, endpoint: str, body: bytes | None = None) -> dict[str, Any]:
    request = Request(
        f"http://supervisor/addons/self/{endpoint}",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def _read_stored_options(
    token: str,
    reader: Callable[[], Mapping[str, Any]] | None,
) -> dict[str, Any]:
    # /data/options.json is a VALIDATED runtime copy. Removed schema keys may
    # already be missing there while still remaining in Supervisor storage.
    response = (
        reader()
        if reader is not None
        else _supervisor_request(token, "GET", "info")
    )
    if response.get("result") != "ok":
        raise RuntimeError(f"Supervisor info returned: {response.get('message')}")
    data = response.get("data")
    raw = data.get("options") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        raise RuntimeError("Supervisor info does not contain options object")
    return json.loads(json.dumps(raw))


def migrate_supervisor_options(
    options_path: Path,
    *,
    token: str | None = None,
    snapshot_path: Path | None = None,
    reader: Callable[[], Mapping[str, Any]] | None = None,
    sender: Callable[[bytes], Mapping[str, Any]] | None = None,
) -> bool:
    """Cleanup AFTER SQLite seed; never update runtime targets from old YAML."""
    token = token if token is not None else os.environ.get("SUPERVISOR_TOKEN", "")
    if not token or not options_path.exists():
        return False

    try:
        raw = _read_stored_options(token, reader)
        migrated, exceptions = build_migrated_options(raw)
        if exceptions:
            LOGGER.warning(
                "Очистка Supervisor options остановлена: нестандартные параметры %s; "
                "требуется отдельная проверка",
                ", ".join(exceptions),
            )
            return False
        if migrated == raw:
            return False

        snapshot_path = snapshot_path or options_path.parent / "options_before_0.1.29_supervisor.json"
        if not snapshot_path.exists():
            snapshot_path.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        patch = build_supervisor_patch(raw, migrated)
        body = json.dumps({"options": patch}).encode("utf-8")
        response = (
            sender(body)
            if sender is not None
            else _supervisor_request(token, "POST", "options", body)
        )
        if response.get("result") != "ok":
            raise RuntimeError(f"Supervisor rejected migration: {response.get('message')}")

        stored_after = _read_stored_options(token, reader)
        actual, remaining = build_migrated_options(stored_after)
        if actual != stored_after or remaining:
            raise RuntimeError(
                "Supervisor still stores deprecated options after migration; "
                "next startup can retry"
            )

        LOGGER.info("Supervisor options очищены, SQLite и привязки устройств сохранены")
        return True
    except (HTTPError, URLError, OSError, RuntimeError, ValueError, TypeError) as exc:
        LOGGER.warning("Supervisor options migration deferred: %s", exc)
        return False
