from __future__ import annotations

import asyncio
import logging
from typing import Any


LOGGER = logging.getLogger(__name__)


class ClimateLog:
    """Dual-channel Climate diagnostic logger.

    The App logger is authoritative. The Home Assistant script mirror is
    best-effort, asynchronous and must never block climate control.
    """

    def __init__(self, ha: Any) -> None:
        self.ha = ha
        self._tasks: set[asyncio.Task[None]] = set()

    def write2climate_log(
        self,
        title: str,
        message: str,
        *,
        level: int = logging.INFO,
    ) -> None:
        LOGGER.log(level, "[%s] %s", title, message)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        task = loop.create_task(
            self._mirror(title, message),
            name="climate-log-mirror",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _mirror(self, title: str, message: str) -> None:
        try:
            await self.ha.call_service(
                "script",
                "write2climatelog",
                {
                    "title": title,
                    "message": message,
                },
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.warning(
                "climate.log mirror failed: title=%s",
                title,
                exc_info=True,
            )

    async def flush(self) -> None:
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    async def close(self) -> None:
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
