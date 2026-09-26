from __future__ import annotations

import asyncio
import logging
from typing import Any


LOGGER = logging.getLogger(__name__)
MIRROR_QUEUE_MAXSIZE = 500


class ClimateLog:
    """Dual-channel Climate diagnostic logger.

    The App logger is authoritative. The Home Assistant script mirror is
    best-effort, asynchronous and serialized so climate.log preserves order.
    """

    def __init__(self, ha: Any) -> None:
        self.ha = ha
        self._queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(
            maxsize=MIRROR_QUEUE_MAXSIZE
        )
        self._worker: asyncio.Task[None] | None = None

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

        if self._worker is None or self._worker.done():
            self._worker = loop.create_task(
                self._mirror_worker(),
                name="climate-log-mirror",
            )

        try:
            self._queue.put_nowait((title, message))
        except asyncio.QueueFull:
            LOGGER.warning(
                "climate.log mirror queue full; dropped entry: title=%s",
                title,
            )

    async def _mirror_worker(self) -> None:
        while True:
            title, message = await self._queue.get()
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
            finally:
                self._queue.task_done()

    async def flush(self) -> None:
        await self._queue.join()

    async def close(self) -> None:
        worker = self._worker
        if worker is None:
            return
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        self._worker = None
