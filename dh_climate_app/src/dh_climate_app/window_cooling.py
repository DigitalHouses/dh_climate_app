"""Event-driven window debounce for cooling devices only.

The first observed OPEN starts the delay. A confirmed CLOSED clears the
inhibition; an UNKNOWN sensor never counts as a confirmed CLOSED or OPEN.
Window timestamps are transient, not persisted across HA disconnects.
"""
from __future__ import annotations

import math
import time
from typing import Mapping

from .rooms import RoomState


class WindowCoolingGuard:
    def __init__(self) -> None:
        self._opened_at: dict[str, float] = {}

    def reset(self) -> None:
        self._opened_at.clear()

    def evaluate(
        self,
        rooms: Mapping[str, RoomState],
        *,
        delay_seconds: float,
        now_monotonic: float | None = None,
    ) -> tuple[dict[str, bool], dict[str, float]]:
        if not math.isfinite(delay_seconds) or delay_seconds < 0:
            raise ValueError("invalid window delay")
        now = time.monotonic() if now_monotonic is None else now_monotonic
        blocked: dict[str, bool] = {}
        deadlines: dict[str, float] = {}

        for room_id, room in rooms.items():
            if room.window_state != "open":
                self._opened_at.pop(room_id, None)
                blocked[room_id] = False
                continue

            # Opening predates this process only if verified by actual runtime
            # observation, never by inventing a past timestamp.
            began = self._opened_at.setdefault(room_id, now)
            deadline = began + delay_seconds
            blocked[room_id] = now >= deadline
            if not blocked[room_id]:
                deadlines[room_id] = deadline

        for room_id in set(self._opened_at) - set(rooms):
            self._opened_at.pop(room_id, None)
        return blocked, deadlines
