"""Admin-only Supervisor self-restart endpoint; no real HAOS restart in tests."""
from __future__ import annotations

import asyncio
import json
import unittest

from dh_climate_app.ingress import OperationsWebServer


class FakeEditor:
    def __init__(self, pending: bool) -> None:
        self.pending = pending

    async def state(self) -> dict:
        return {"pending_restart": self.pending}


class RestartEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.calls = 0
        self.editor = FakeEditor(True)

        async def restart() -> None:
            self.calls += 1

        self.server = OperationsWebServer(
            {"app": {"ha_connected": True}},
            host="127.0.0.1", port=0, allowed_peers=("127.0.0.1",),
            editor=self.editor, restart_app=restart,
        )
        await self.server.start()

    async def asyncTearDown(self) -> None:
        await self.server.stop()
        task = self.server._restart_task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def request(
        self, *, method: str = "POST", admin: bool = True,
        marker: bool = True, content_type: str = "application/json",
        body: bytes = b'{"confirm":"RESTART"}',
    ) -> tuple[int, bytes]:
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", self.server.bound_port,
        )
        headers = [
            f"{method} /api/app/restart HTTP/1.1", "Host: localhost",
            f"Content-Type: {content_type}",
            f"Content-Length: {len(body)}",
        ]
        if admin:
            headers += [
                "X-Remote-User-Id: admin-test",
                "X-Remote-User-Groups: system-admin",
            ]
        if marker:
            headers += ["X-Requested-With: DHClimateExplorer"]
        writer.write(("\r\n".join(headers) + "\r\n\r\n").encode() + body)
        await writer.drain()
        raw = await asyncio.wait_for(reader.read(), timeout=3)
        writer.close()
        await writer.wait_closed()
        status = int(raw.split(b" ", 2)[1])
        return status, raw.split(b"\r\n\r\n", 1)[1]

    async def test_admin_authentication_required(self) -> None:
        status, _ = await self.request(admin=False)
        self.assertEqual(status, 403)
        self.assertEqual(self.calls, 0)

    async def test_only_post_and_csrf_marked_json(self) -> None:
        self.assertEqual((await self.request(method="GET"))[0], 405)
        self.assertEqual((await self.request(marker=False))[0], 403)
        self.assertEqual((await self.request(content_type="text/plain"))[0], 415)
        self.assertEqual((await self.request(body=b"bad json"))[0], 400)
        self.assertEqual((await self.request(body=b'{"confirm":"APPLY"}'))[0], 422)
        self.assertEqual(self.calls, 0)

    async def test_restart_requires_pending_apply(self) -> None:
        self.editor.pending = False
        status, _ = await self.request()
        self.assertEqual(status, 409)
        self.assertEqual(self.calls, 0)

    async def test_schedule_only_once_and_wait_for_explicit_acceptance(self) -> None:
        status, body = await self.request()
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(body), {"status": "scheduled"})
        self.assertEqual(self.calls, 0, "HTTP 202 is sent before restart")
        status2, _ = await self.request()
        self.assertEqual(status2, 409)
        self.assertIsNotNone(self.server._restart_task)
        await asyncio.wait_for(self.server._restart_task, timeout=2)
        self.assertEqual(self.calls, 1)

    async def test_peer_boundary_still_applies(self) -> None:
        self.server.allowed_peers = frozenset({"172.30.32.2"})
        status, _ = await self.request()
        self.assertEqual(status, 403)
        self.assertEqual(self.calls, 0)


if __name__ == "__main__":
    unittest.main()
