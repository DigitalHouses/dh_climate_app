from __future__ import annotations

import asyncio
from datetime import datetime
import json
import tempfile
import unittest

from dh_climate_app.entity_catalog import EntityCatalog, build_catalog
from dh_climate_app.ingress import OperationsWebServer


class CatalogProjectionTests(unittest.TestCase):
    def test_registry_area_fallback_and_no_secret_leak(self):
        states=[
            {"entity_id":"sensor.th_livingroom_temperature","state":"29.0",
             "attributes":{"friendly_name":"Температура гостиной",
              "device_class":"temperature","unit_of_measurement":"°C",
              "access_token":"do-not-expose"}},
            {"entity_id":"climate.thermostat","state":"unavailable",
             "attributes":{"friendly_name":"Термостат"}},
            {"entity_id":"person.someone","state":"home",
             "attributes":{"friendly_name":"Private user"}},
            {"entity_id":"sensor.no_area","state":"unknown","attributes":{}},
        ]
        reg={"entities":[
            {"ei":"sensor.th_livingroom_temperature","di":"d1"},
            {"ei":"climate.thermostat","ai":"bedroom"},
        ]}
        devices=[{"id":"d1","area_id":"living","name_by_user":"Термостат в гостиной"}]
        areas=[{"area_id":"living","name":"Гостиная"},
               {"area_id":"bedroom","name":"Спальня"}]
        out=build_catalog(states,reg,devices,areas)
        self.assertEqual(len(out["entities"]),3)
        catalog={x["entity_id"]:x for x in out["entities"]}
        self.assertEqual(catalog["sensor.th_livingroom_temperature"]["area_name"],"Гостиная")
        self.assertEqual(catalog["climate.thermostat"]["area_id"],"bedroom")
        self.assertFalse(catalog["climate.thermostat"]["available"])
        self.assertIsNone(catalog["sensor.no_area"]["area_id"])
        self.assertNotIn("do-not-expose",json.dumps(out,ensure_ascii=False))
        self.assertNotIn("person.someone",json.dumps(out,ensure_ascii=False))
        self.assertIn("sensor.no_area",catalog)

    def test_unregistered_state_is_still_selectable(self):
        out=build_catalog([{"entity_id":"sensor.unregistered","state":"27",
                            "attributes":{"friendly_name":"Без реестра"}}],{},[],[])
        self.assertEqual(out["entities"][0]["name"],"Без реестра")
        self.assertFalse(out["truncated"])


class CatalogCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_on_demand_cache(self):
        obj=EntityCatalog(token="test",ttl_seconds=30)
        count=0
        async def mock_fetch():
            nonlocal count
            count+=1
            return {"areas":[],"entities":[]}
        obj._fetch=mock_fetch
        x,y=await asyncio.gather(obj.get(),obj.get())
        self.assertIs(x,y)
        self.assertEqual(count,1)
        obj._expires=0
        await obj.get()
        self.assertEqual(count,2)


class FakeCatalog:
    async def get(self):
        return {"areas":[{"id":"x","name":"Зал"}],
                "entities":[{"entity_id":"sensor.test","name":"Test","domain":"sensor"}],
                "truncated":False}


class CatalogHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app=OperationsWebServer({"app":{}},host="127.0.0.1",port=0,
            allowed_peers=("127.0.0.1",),catalog=FakeCatalog())
        await self.app.start()

    async def asyncTearDown(self):
        await self.app.stop()

    async def request(self,method,headers=None):
        reader,writer=await asyncio.open_connection("127.0.0.1",self.app.bound_port)
        h="".join(f"{k}: {v}\r\n" for k,v in (headers or {}).items())
        writer.write(f"{method} /api/entities HTTP/1.1\r\nHost: localhost\r\n{h}\r\n".encode())
        await writer.drain()
        data=await reader.read()
        writer.close()
        await writer.wait_closed()
        return int(data.split(b" ",2)[1]),data

    async def test_admin_only_and_get_only(self):
        self.assertEqual((await self.request("GET"))[0],403)
        headers={"X-Remote-User-Id":"u","X-Remote-User-Groups":"system-users"}
        self.assertEqual((await self.request("GET",headers))[0],403)
        headers["X-Remote-User-Groups"]="system-admin"
        status,data=await self.request("GET",headers)
        self.assertEqual(status,200)
        self.assertIn(b"sensor.test",data)
        self.assertEqual((await self.request("POST",headers))[0],405)


if __name__=="__main__":
    unittest.main()
