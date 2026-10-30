from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from dh_climate_app.manifest import ManifestEditor, EditConflict, EditValidation
from dh_climate_app.ingress import OperationsWebServer


def options():
    return {
        "night_mode": "", "we_at_home": "",
        "outdoor": {"temperature_sources": [], "humidity_sources": []},
        "rooms": [{"id": "bedroom", "name": "Спальня",
                   "temperature_sensors": ["sensor.bedroom"],
                   "humidity_sensors": [], "window_sensors": [],
                   "devices": []}],
        "heating_source": "boiler", "vrf": "off",
        "resources": [], "pumps": [], "circuits": [],
        "telemetry_enabled": False, "log_level": "info",
    }


class ManifestEditorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.original = options()
        self.editor = ManifestEditor(self.path, self.original)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_draft_does_not_change_runtime_and_survives_restart(self):
        state = await self.editor.state()
        candidate = options()
        candidate["rooms"][0]["name"] = "Новая спальня"
        staged = await self.editor.save(options=candidate,
            base_hash=state["base_hash"], revision=state["revision"], author_id="user-1")
        self.assertTrue(staged["dirty"])
        self.assertFalse(staged["pending_restart"])
        self.assertEqual(self.editor.effective_on_startup()["rooms"][0]["name"], "Спальня")
        other = ManifestEditor(self.path, self.original)
        self.assertEqual((await other.state())["options"]["rooms"][0]["name"], "Новая спальня")
        summary = await other.validate(base_hash=staged["base_hash"], revision=1)
        self.assertEqual(summary["rooms"], 1)
        self.assertFalse(self.editor.active_path.exists())

    async def test_apply_is_atomic_and_requires_restart(self):
        first = await self.editor.state()
        candidate = options()
        candidate["rooms"].append({
            "id": "lab", "name": "LAB",
            "temperature_sensors": ["sensor.lab"], "devices": []})
        saved = await self.editor.save(options=candidate,
            base_hash=first["base_hash"], revision=0, author_id="admin")
        applied = await self.editor.apply(base_hash=saved["base_hash"], revision=1)
        self.assertEqual(applied["summary"]["rooms"], 2)
        self.assertTrue(applied["pending_restart"])
        self.assertTrue(self.editor.previous_path.exists())
        self.assertFalse(self.editor.draft_path.exists())
        self.assertEqual(len(self.editor.effective_on_startup()["rooms"]), 1)
        with self.assertRaises(EditConflict):
            await self.editor.save(options=options(),
                base_hash=applied["base_hash"], revision=0, author_id="admin")
        restarted = ManifestEditor(self.path, self.original)
        self.assertEqual(len(restarted.effective_on_startup()["rooms"]), 2)
        self.assertFalse((await restarted.state())["pending_restart"])

    async def test_invalid_draft_never_published(self):
        state = await self.editor.state()
        candidate = options()
        candidate["rooms"][0]["temperature_sensors"] = []
        saved = await self.editor.save(options=candidate,
            base_hash=state["base_hash"], revision=0, author_id="admin")
        with self.assertRaises(EditValidation):
            await self.editor.validate(base_hash=saved["base_hash"], revision=1)
        with self.assertRaises(EditValidation):
            await self.editor.apply(base_hash=saved["base_hash"], revision=1)
        self.assertFalse(self.editor.active_path.exists())

    async def test_optimistic_lock_and_discard(self):
        state = await self.editor.state()
        staged = await self.editor.save(options=options(),
            base_hash=state["base_hash"], revision=0, author_id="a")
        with self.assertRaises(EditConflict):
            await self.editor.save(options=options(),
                base_hash=state["base_hash"], revision=0, author_id="b")
        cleared = await self.editor.discard(
            base_hash=staged["base_hash"], revision=staged["revision"])
        self.assertFalse(cleared["dirty"])
        self.assertFalse(self.editor.draft_path.exists())

    async def test_bad_active_manifest_fail_closed(self):
        self.editor.active_path.write_text('{"schema_version":1,"options":{"rooms":[],"bogus":123}}')
        with self.assertRaises(EditValidation):
            ManifestEditor(self.path, self.original)


class IngressPermissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.editor = ManifestEditor(Path(self.tmp.name), options())
        self.server = OperationsWebServer({"app":{}}, host="127.0.0.1", port=0,
            allowed_peers=("127.0.0.1",), editor=self.editor)
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.stop()
        self.tmp.cleanup()

    async def request(self, method, path, data=None, headers=None):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.server.bound_port)
        body = json.dumps(data).encode("utf-8") if data is not None else b""
        header_lines = [f"{method} {path} HTTP/1.1", "Host: localhost"]
        for key, value in (headers or {}).items():
            header_lines.append(f"{key}: {value}")
        if data is not None:
            header_lines.extend([f"Content-Length: {len(body)}",
                                 "Content-Type: application/json"])
        writer.write(("\r\n".join(header_lines)+"\r\n\r\n").encode()+body)
        await writer.drain()
        response = await reader.read()
        writer.close()
        await writer.wait_closed()
        code = int(response.split(b" ", 2)[1])
        result = response.split(b"\r\n\r\n", 1)[1]
        return code, result

    @staticmethod
    def admin():
        return {"X-Remote-User-Id": "abc",
                "X-Remote-User-Groups": "system-users,system-admin"}

    def post_headers(self):
        return {**self.admin(), "X-Requested-With": "DHClimateExplorer"}

    async def test_absent_user_and_nonadmin_are_denied(self):
        self.assertEqual((await self.request("GET", "/api/config"))[0], 403)
        self.assertEqual((await self.request("GET", "/api/config",
            headers={"X-Remote-User-Id": "abc", "X-Remote-User-Groups":"system-users"}))[0], 403)
        self.assertEqual((await self.request("GET", "/api/config",
            headers={"X-Remote-User-Groups":"system-admin"}))[0], 403)
        self.assertEqual((await self.request("GET", "/api/config",headers=self.admin()))[0], 200)

    async def test_post_csrf_marker_and_immutable_runtime(self):
        code, raw = await self.request("GET", "/api/config", headers=self.admin())
        state = json.loads(raw)
        draft = {"options":options(),"base_hash":state["base_hash"],"revision":0}
        self.assertEqual((await self.request("POST","/api/config/draft",draft,headers=self.admin()))[0],403)
        self.assertEqual((await self.request("POST","/api/config/draft",draft,headers=self.post_headers()))[0],200)
        self.assertEqual((await self.request("POST","/api/config/apply",
            {"base_hash":state["base_hash"],"revision":1},headers=self.post_headers()))[0],422)
        self.assertEqual((await self.request("POST","/api/config/apply",
            {"base_hash":state["base_hash"],"revision":1,"confirm":"APPLY"},headers=self.post_headers()))[0],200)
        self.assertEqual(self.editor.effective_on_startup()["rooms"][0]["name"],"Спальня")

    async def test_arbitrary_methods_and_duplicate_headers_rejected(self):
        self.assertEqual((await self.request("DELETE","/api/config",headers=self.admin()))[0],404)
        self.assertEqual((await self.request("POST","/api/snapshot",headers=self.post_headers()))[0],405)
        headers=self.post_headers()
        headers["x-remote-user-id"]="other"
        self.assertEqual((await self.request("GET","/api/config",headers=headers))[0],400)


if __name__ == "__main__":
    unittest.main()
