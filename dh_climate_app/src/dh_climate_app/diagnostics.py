"""Bounded, secret-aware support diagnostics for the Climate Explorer.

Export is initiated explicitly by an HA administrator. No HA secrets, full
Supervisor options, extra subscriptions or periodic polling are introduced.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import logging
import math
import re
from typing import Any, Mapping

SECRET_FIELD = re.compile(
    r"(?:password|passwd|secret|token|credential|authorization|cookie|"
    r"api[_-]?key|private[_-]?key|access[_-]?key|session[_-]?id|"
    r"author[_-]?id|user[_-]?id)",
    re.IGNORECASE,
)
SENSITIVE_PARAMETER = re.compile(
    r"([?&](?:access_token|token|api_key|password|secret|signature|"
    r"auth|code|key)=)[^&#\\s]+", re.IGNORECASE,
)
AUTH_HEADER = re.compile(
    r"(\\b(?:Bearer|Basic)\\s+)[A-Za-z0-9._~+/-]+={0,2}",
    re.IGNORECASE,
)
URL_PASSWORD = re.compile(
    r"(https?://)[^/\\s:@]+:[^/\\s@]+@", re.IGNORECASE,
)


def mask_text(value: str) -> str:
    """Protect credentials pasted into incidental labels/error messages."""
    value = SENSITIVE_PARAMETER.sub(r"\\1[REDACTED]", value)
    value = AUTH_HEADER.sub(r"\\1[REDACTED]", value)
    return URL_PASSWORD.sub(r"\\1[REDACTED]@", value)


def sanitize_export(value: Any, *, depth: int = 0) -> Any:
    """Allowlisted JSON primitives, recursive credential-key masking."""
    if depth >= 24:
        return "[DEPTH LIMIT]"
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[REDACTED]" if SECRET_FIELD.search(str(key))
                else sanitize_export(item, depth=depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_export(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, bool):
        return value
    return str(value)[:256]


class BoundedDiagnosticLogHandler(logging.Handler):
    """Capture only warning/error messages from app loggers, up to 120 entries."""

    def __init__(self, capacity: int = 120) -> None:
        super().__init__(level=logging.WARNING)
        self.entries: deque[dict[str, str]] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            formatted = mask_text(self.format(record))[:3000]
            self.entries.append({
                "at": datetime.fromtimestamp(
                    record.created, tz=timezone.utc
                ).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": formatted,
            })
        except Exception:
            self.handleError(record)

    def snapshot(self) -> list[dict[str, str]]:
        return list(self.entries)
