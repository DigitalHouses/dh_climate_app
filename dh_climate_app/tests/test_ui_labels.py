from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from dh_climate_app.ui_labels import UILabels
from dh_climate_app.manifest import EditConflict, EditValidation
from dh_climate_app.ingress import OperationsWebServer


class UILabelsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = UILabels(Path(self.temp.name))

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_room_and_entity_names_are_persistent(self):
        one = await self.store.save(key="room:livingroom",
            names={"ru": "Гостиная", "en": "Living Room"}, revision=0)
        self.assertEqual(one["revision"], 1)
        two = await self.store.save(key="entity:climate.termostat_livingroom",
            names={"ru": "Термостат гостиной"}, revision=1)
        self.assertEqual(two["revision"], 2)
        restarted = UILabels(Path(self.temp.name))
        self.assertEqual((await restarted.state())["labels"]["room:livingroom"]["ru"], "Гостиная")
        self.assertEqual((await restarted.state())["labels"]["entity:climate.termostat_livingroom"]["ru"],
                         "Термостат гостиной")
        self.assertEqual(restarted.path.stat().st_mode & 0o777, 0o600)

    async def test_empty_labels_reset_without_touching_other_items(self):
        await self.store.save(key="room:livingroom",names={"ru":"Гостиная"},revision=0)
        final = await self.store.save(key="room:livingroom", names={"ru":"  ","en":""},revision=1)
        self.assertNotIn("room:livingroom",final["labels"])

    async def test_rejects_stale_revision_and_invalid_keys(self):
        await self.store.save(key="room:bedroom",names={"ru":"Спальня"},revision=0)
        with self.assertRaises(EditConflict):
            await self.store.save(key="room:bedroom",names={"ru":"Спальня 2"},revision=0)
        for key in ("room:../../etc/passwd","entity:secret.password","system:home","entity:climate.ABC"):
            with self.subTest(key=key),self.assertRaises(EditValidation):
                await self.store.save(key=key,names={"ru":"X"},revision=1)
        for names in ({"ru":"\n"}, {"xx":"invalid"}, {"en":"X"*121}, {"ru":5}):
            with self.subTest(names=names),self.assertRaises(EditValidation):
                await self.store.save(key="room:bedroom",names=names,revision=1)


class UILabelIngressTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.labels = UILabels(Path(self.temp.name))
        self.server = OperationsWebServer(
            {"app":{}}, host="127.0.0.1",port=0,
            allowed_peers=("127.0.0.1",),labels=self.labels,
        )
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.stop()
        self.temp.cleanup()

    async def request(self, method, path, data=None, headers=None):
        reader, writer = await asyncio.open_connection("127.0.0.1",self.server.bound_port)
        body=json.dumps(data).encode() if data is not None else b""
        lines=[f"{method} {path} HTTP/1.1", "Host: localhost"]
        lines.extend(f"{key}: {value}" for key,value in (headers or {}).items())
        if data is not None:
            lines.extend([f"Content-Type: application/json",f"Content-Length: {len(body)}"])
        writer.write(("\r\n".join(lines)+"\r\n\r\n").encode()+body)
        await writer.drain()
        response=await reader.read()
        writer.close()
        await writer.wait_closed()
        return int(response.split(b" ",2)[1]),response.split(b"\r\n\r\n",1)[1]

    @staticmethod
    def admin(marker=False):
        result={"X-Remote-User-Id":"test-user","X-Remote-User-Groups":"system-admin"}
        if marker:
            result["X-Requested-With"]="DHClimateExplorer"
        return result

    async def test_viewer_can_read_but_not_write(self):
        code,raw=await self.request("GET","/api/labels")
        self.assertEqual(code,200)
        self.assertEqual(json.loads(raw)["labels"],{})
        update={"key":"room:livingroom","names":{"ru":"Гостиная"},"revision":0}
        self.assertEqual((await self.request("POST","/api/labels",update))[0],403)
        self.assertEqual((await self.request("POST","/api/labels",update,headers=self.admin()))[0],403)
        self.assertEqual((await self.request("POST","/api/labels",update,headers=self.admin(True)))[0],200)
        self.assertEqual((await self.request("GET","/api/labels"))[0],200)

    async def test_conflicts_and_limited_methods(self):
        update={"key":"room:bedroom","names":{"ru":"Спальня"},"revision":0}
        self.assertEqual((await self.request("POST","/api/labels",update,headers=self.admin(True)))[0],200)
        self.assertEqual((await self.request("POST","/api/labels",update,headers=self.admin(True)))[0],409)
        self.assertEqual((await self.request("DELETE","/api/labels",headers=self.admin(True)))[0],405)


if __name__=="__main__":
    unittest.main()
