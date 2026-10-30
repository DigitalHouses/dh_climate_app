"""Small dependency-free HAOS Ingress HTTP/SSE server.

Ingress is the only trust boundary: reject traffic not originating from
Home Assistant Supervisor (172.30.32.2). Writes require an authenticated
HA system-admin group, CSRF-resistant JSON requests, and optimistic locking.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .manifest import ManifestEditor, EditConflict, EditValidation
from .ui_labels import UILabels
from .entity_catalog import EntityCatalog


WEB_ROOT = Path(__file__).with_name("web")
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/editor.js": ("editor.js", "text/javascript; charset=utf-8"),
    "/entity_picker.js": ("entity_picker.js", "text/javascript; charset=utf-8"),
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
        editor: ManifestEditor | None = None,
        labels: UILabels | None = None,
        catalog: EntityCatalog | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.allowed_peers = frozenset(allowed_peers)
        self.snapshot = initial
        self.editor = editor
        self.labels = labels
        self.catalog = catalog
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

    @staticmethod
    def _parse_headers(raw: bytes) -> tuple[str, str, dict[str, str]]:
        lines = raw.split(b"\r\n")
        method, path, version = lines[0].decode("ascii").split(" ", 2)
        if version != "HTTP/1.1":
            raise ValueError("Invalid HTTP version")
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if not line:
                continue
            key, value = line.decode("ascii").split(":", 1)
            key = key.strip().lower()
            if key in headers:
                raise ValueError("Duplicate HTTP header")
            headers[key] = value.strip()
        return method, path, headers

    @staticmethod
    def _is_admin(headers: dict[str, str]) -> bool:
        # Header injection from the browser is removed by Supervisor.
        # Never trust username or a blank/unrecognised group as admin.
        return bool(headers.get("x-remote-user-id", "").strip()) and (
            "system-admin" in {
                value.strip() for value in
                headers.get("x-remote-user-groups", "").split(",")
            }
        )

    async def _labels(self, reader: asyncio.StreamReader,
                      writer: asyncio.StreamWriter, method: str,
                      headers: dict[str, str], path: str = "/api/labels") -> None:
        if self.labels is None:
            await self._reply(writer, "404 Not Found", b"No UI labels")
            return
        if method == "GET" and path == "/api/labels":
            await self._reply(writer, "200 OK",
                              self._json(await self.labels.state()),
                              "application/json; charset=utf-8")
            return
        if method != "POST":
            await self._reply(writer, "405 Method Not Allowed", b"GET or POST required")
            return
        if not self._is_admin(headers):
            await self._reply(writer, "403 Forbidden", b"Administrator required")
            return
        if headers.get("x-requested-with") != "DHClimateExplorer":
            await self._reply(writer, "403 Forbidden", b"Invalid request marker")
            return
        if headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            await self._reply(writer, "415 Unsupported Media Type", b"JSON required")
            return
        if "transfer-encoding" in headers:
            await self._reply(writer, "400 Bad Request", b"Chunked not supported")
            return
        try:
            length = int(headers.get("content-length", ""))
        except ValueError:
            length = -1
        if not 0 < length <= 8192:
            await self._reply(writer, "413 Content Too Large", b"Invalid body size")
            return
        try:
            data = json.loads(await asyncio.wait_for(reader.readexactly(length), timeout=5))
            if not isinstance(data, dict):
                raise EditValidation("Invalid body")
            if path == "/api/room-area":
                result = await self.labels.save_area(
                    room_id=data.get("room_id"), area_id=data.get("area_id"),
                    revision=data.get("revision"),
                )
            else:
                result = await self.labels.save(
                    key=data.get("key"), names=data.get("names"),
                    revision=data.get("revision"),
                )
        except EditConflict as exc:
            await self._reply(writer, "409 Conflict",
                              self._json({"error": str(exc)}),
                              "application/json; charset=utf-8")
            return
        except (EditValidation, ValueError, TypeError,
                asyncio.IncompleteReadError, TimeoutError) as exc:
            await self._reply(writer, "422 Unprocessable Content",
                              self._json({"error": str(exc)}),
                              "application/json; charset=utf-8")
            return
        await self._reply(writer, "200 OK", self._json(result),
                          "application/json; charset=utf-8")

    async def _config(self, reader: asyncio.StreamReader,
                      writer: asyncio.StreamWriter, method: str,
                      path: str, headers: dict[str, str]) -> None:
        if self.editor is None:
            await self._reply(writer, "404 Not Found", b"No editor")
            return
        if not self._is_admin(headers):
            await self._reply(writer, "403 Forbidden", b"Administrator required")
            return
        if method == "GET" and path == "/api/config":
            result = await self.editor.state()
            await self._reply(writer, "200 OK", self._json(result),
                              "application/json; charset=utf-8")
            return
        actions = {"/api/config/draft": "save", "/api/config/validate": "validate",
                   "/api/config/apply": "apply", "/api/config/discard": "discard"}
        if path not in actions:
            await self._reply(writer, "404 Not Found", b"Not found")
            return
        if method != "POST":
            await self._reply(writer, "405 Method Not Allowed", b"POST required",
                              extra="Allow: POST\r\n")
            return
        if headers.get("x-requested-with") != "DHClimateExplorer":
            await self._reply(writer, "403 Forbidden", b"Invalid request marker")
            return
        if headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            await self._reply(writer, "415 Unsupported Media Type", b"JSON required")
            return
        if "transfer-encoding" in headers:
            await self._reply(writer, "400 Bad Request", b"Chunked not supported")
            return
        try:
            length = int(headers.get("content-length", ""))
        except ValueError:
            length = -1
        if not 0 < length <= 262144:
            await self._reply(writer, "413 Content Too Large", b"Invalid body size")
            return
        try:
            payload = json.loads(await asyncio.wait_for(reader.readexactly(length), timeout=5),
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
            if not isinstance(payload, dict):
                raise ValueError("Expected object")
            if path == "/api/config/apply" and payload.get("confirm") != "APPLY":
                raise EditValidation("Explicit APPLY confirmation required")
            args = {"base_hash": payload.get("base_hash"),
                    "revision": payload.get("revision")}
            if actions[path] == "save":
                args["options"] = payload.get("options")
                args["author_id"] = headers["x-remote-user-id"]
            result = await getattr(self.editor, actions[path])(**args)
        except EditConflict as exc:
            await self._reply(writer, "409 Conflict",
                              self._json({"error": str(exc)}),
                              "application/json; charset=utf-8")
            return
        except (EditValidation, ValueError, TypeError, json.JSONDecodeError,
                asyncio.IncompleteReadError, TimeoutError) as exc:
            await self._reply(writer, "422 Unprocessable Content",
                              self._json({"error": str(exc)}),
                              "application/json; charset=utf-8")
            return
        await self._reply(writer, "200 OK", self._json(result),
                          "application/json; charset=utf-8")

    async def _entities(self, writer: asyncio.StreamWriter, method: str,
                        headers: dict[str, str]) -> None:
        if method != "GET":
            await self._reply(writer, "405 Method Not Allowed", b"GET required",
                              extra="Allow: GET\r\n")
            return
        if not self._is_admin(headers):
            await self._reply(writer, "403 Forbidden", b"Administrator required")
            return
        if self.catalog is None:
            await self._reply(writer, "503 Service Unavailable", b"Catalog unavailable")
            return
        try:
            payload = await self.catalog.get()
        except Exception:
            # Catalog is a nonessential admin UI feature. Never let an HA
            # registry/WebSocket failure affect climate execution.
            await self._reply(writer, "503 Service Unavailable",
                              b"Home Assistant entity catalog temporarily unavailable")
            return
        await self._reply(writer, "200 OK", self._json(payload),
                          "application/json; charset=utf-8")

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> None:
        self._clients.add(writer)
        try:
            peer = writer.get_extra_info("peername")
            try:
                raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
                method, path, headers = self._parse_headers(raw)
            except (UnicodeError, ValueError, asyncio.IncompleteReadError,
                    asyncio.LimitOverrunError, TimeoutError):
                await self._reply(writer, "400 Bad Request", b"Bad request")
                return
            if peer is None or peer[0] not in self.allowed_peers:
                await self._reply(writer, "403 Forbidden", b"Forbidden")
                return
            if path == "/api/entities":
                await self._entities(writer, method, headers)
                return
            if path in ("/api/labels", "/api/room-area"):
                await self._labels(reader, writer, method, headers, path)
                return
            if path == "/api/config" or path.startswith("/api/config/"):
                await self._config(reader, writer, method, path, headers)
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
