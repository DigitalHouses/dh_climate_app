from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping
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
    """Удалить старые начальные уставки, не меняя топологию и параметры управления."""
    options = json.loads(json.dumps(raw))
    exceptions: list[str] = []
    for key, standard in (
        ("ac_min_outdoor_temperature", DEFAULT_AC_MIN_OUTDOOR_TEMPERATURE),
        ("outdoor_temperature_ema_minutes", DEFAULT_OUTDOOR_EMA_MINUTES),
    ):
        if key in options and float(options[key]) != standard:
            exceptions.append(key)

    # При нестандартных защитных настройках значения остаются рабочими
    # через совместимый parser: никакой скрытой смены алгоритма.
    if exceptions:
        return options, tuple(exceptions)

    if "hysteresis" in options:
        if "temperature_hysteresis" not in options or options["temperature_hysteresis"] == 0.5:
            options["temperature_hysteresis"] = options["hysteresis"]
    for key in LEGACY_GLOBAL_KEYS:
        options.pop(key, None)
    if isinstance(options.get("rooms"), list):
        for room in options["rooms"]:
            if isinstance(room, dict):
                for key in LEGACY_ROOM_KEYS:
                    room.pop(key, None)
    return options, ()


def migrate_supervisor_options(
    options_path: Path,
    *,
    token: str | None = None,
    snapshot_path: Path | None = None,
    sender=None,
) -> bool:
    """Очистить Supervisor после SQLite seed; сетевые ошибки не останавливают климат."""
    token = token if token is not None else os.environ.get("SUPERVISOR_TOKEN", "")
    if not token or not options_path.exists():
        return False
    raw = json.loads(options_path.read_text(encoding="utf-8"))
    migrated, exceptions = build_migrated_options(raw)
    if exceptions:
        LOGGER.warning(
            "Миграция options отложена: нестандартные защитные настройки %s; "
            "старые значения продолжают действовать",
            ", ".join(exceptions),
        )
        return False
    if migrated == raw:
        return False
    snapshot_path = snapshot_path or options_path.parent / "options_before_0.1.28.json"
    if not snapshot_path.exists():
        snapshot_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    body = json.dumps({"options": migrated}).encode("utf-8")

    def send(payload: bytes) -> dict[str, Any]:
        request = Request(
            "http://supervisor/addons/self/options",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        response = (sender or send)(body)
        if response.get("result") != "ok":
            raise RuntimeError(f"Supervisor rejected options migration: {response.get('message')}")
    except (HTTPError, URLError, OSError, RuntimeError, ValueError) as exc:
        LOGGER.warning("Supervisor options не очищены, повторим при следующем запуске: %s", exc)
        return False
    LOGGER.info("Старые параметры конфигурации удалены из Supervisor; SQLite сохранена")
    return True
