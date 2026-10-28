"""Small dependency-free, read-only Ingress HTTP/SSE server.

Ingress is the only trust boundary: reject traffic not originating from
Home Assistant Supervisor (172.30.32.2). No HA or Supervisor credentials
are ever sent to the browser.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any


WEB_ROOT = Path(__file__).with_name("web")
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/i18n/en.json": ("i18n/en.json", "application/json; charset=utf-8"),
    "/i18n/ru.json": ("i18n/ru.json", "application/json; charset=utf-8"),
}
COMMON_HEADERS = (
    "X-Content-Type-Options: nosniff\r\n"
    "X-Frame-Options: SAMEORIGIN\r\n"
    "Referrer-Policy: no-referrer\r\n"
    "Cache-Control: no-store\r\n"
    "Content-Security-Policy: default-src 'self'; "
    "script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'self' data:; object-src 'none'; base-uri 'none'\r\n"
)


class OperationsWebServer:
    def __init__(
        self, initial: dict[str, Any], *, host: str = "0.0.0.0",
        port: int = 8099, allowed_peers: tuple[str, ...] = ("172.30.32.2",),
    ) -> None:
        self.host = host
        self.port = port
        self.allowed_peers = frozenset(allowed_peers)
        self.snapshot = initial
        self.revision = 0
        self._server: asyncio.AbstractServer | None = None
        self._condition = asyncio.Condition()
        self._clients: set[asyncio.StreamWriter] = set()

    @property
    def bound_port(self) -> int:
        if self._server is None:
            raise RuntimeError("Ingress server not started")
        return self._server.sockets[0].getsockname()[1]

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle, self.host, self.port, limit=8192,
        )

    async def stop(self) -> None:
        for writer in tuple(self._clients):
            writer.close()
        async with self._condition:
            self._condition.notify_all()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._clients.clear()

    async def publish(self, snapshot: dict[str, Any]) -> None:
        if snapshot != self.snapshot:
            async with self._condition:
                self.snapshot = snapshot
                self.revision += 1
                self._condition.notify_all()

    @staticmethod
    def _json(snapshot: dict[str, Any]) -> bytes:
        return json.dumps(
            snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")

    @staticmethod
    async def _reply(
        writer: asyncio.StreamWriter, status: str, body: bytes,
        content_type: str = "text/plain; charset=utf-8", *,
        head: bool = False, extra: str = "",
    ) -> None:
        headers = (
            f"HTTP/1.1 {status}\r\n"
            f"{COMMON_HEADERS}"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"{extra}"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        writer.write(headers + (b"" if head else body))
        await writer.drain()

    async def _events(self, writer: asyncio.StreamWriter) -> None:
        writer.write((
            "HTTP/1.1 200 OK\r\n"
            + COMMON_HEADERS
            + "Content-Type: text/event-stream; charset=utf-8\r\n"
              "Connection: keep-alive\r\n\r\n"
        ).encode("ascii"))
        await writer.drain()
        previous = -1
        while not writer.is_closing():
            if previous != self.revision:
                previous = self.revision
                writer.write(
                    b"event: snapshot\ndata: " + self._json(self.snapshot) + b"\n\n"
                )
                await writer.drain()
            try:
                async with self._condition:
                    if previous == self.revision:
                        await asyncio.wait_for(self._condition.wait(), timeout=25)
            except TimeoutError:
                writer.write(b": heartbeat\n\n")
                await writer.drain()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> None:
        self._clients.add(writer)
        try:
            peer = writer.get_extra_info("peername")
            try:
                request = await asyncio.wait_for(
                    reader.readuntil(b"\r\n\r\n"), timeout=5,
                )
                line = request.split(b"\r\n", 1)[0].decode("ascii")
                method, path, _version = line.split(" ", 2)
            except (UnicodeError, ValueError, asyncio.IncompleteReadError,
                    asyncio.LimitOverrunError, TimeoutError):
                await self._reply(writer, "400 Bad Request", b"Bad request")
                return
            if peer is None or peer[0] not in self.allowed_peers:
                await self._reply(writer, "403 Forbidden", b"Forbidden")
                return
            if method not in ("GET", "HEAD"):
                await self._reply(
                    writer, "405 Method Not Allowed", b"Read-only",
                    extra="Allow: GET, HEAD\r\n",
                )
                return
            if path == "/api/snapshot":
                await self._reply(
                    writer, "200 OK", self._json(self.snapshot),
                    "application/json; charset=utf-8", head=method == "HEAD",
                )
            elif path == "/api/events":
                if method == "HEAD":
                    await self._reply(writer, "405 Method Not Allowed", b"",
                                      extra="Allow: GET\r\n", head=True)
                else:
                    await self._events(writer)
            elif path in ASSETS:
                name, mime = ASSETS[path]
                data = (WEB_ROOT / name).read_bytes()
                await self._reply(
                    writer, "200 OK", data, mime, head=method == "HEAD",
                )
            else:
                await self._reply(writer, "404 Not Found", b"Not found")
        except (ConnectionError, BrokenPipeError, asyncio.CancelledError):
            pass
        finally:
            self._clients.discard(writer)
            writer.close()
