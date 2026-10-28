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
            # Windows are irrelevant to every heating device, including
            # reversible AC operating in HEAT season.
            if room.season.value != "cool":
                self._opened_at.pop(room_id, None)
                blocked[room_id] = False
                continue
            if room.window_state in ("closed", "not_configured"):
                self._opened_at.pop(room_id, None)
                blocked[room_id] = False
                continue
            if room.window_state == "open":
                # First evidence of OPEN starts the delay; unknown states
                # do not independently start new cooling inhibition.
                self._opened_at.setdefault(room_id, now)

            # UNKNOWN is not a confirmed CLOSED. If the room had already
            # observed OPEN, hold the pending/active inhibition until a
            # confirmed CLOSED arrives. If no OPEN was seen, do not guess.
            began = self._opened_at.get(room_id)
            if began is None:
                blocked[room_id] = False
                continue
            deadline = began + delay_seconds
            blocked[room_id] = now >= deadline
            if not blocked[room_id]:
                deadlines[room_id] = deadline

        for room_id in set(self._opened_at) - set(rooms):
            self._opened_at.pop(room_id, None)
        return blocked, deadlines
