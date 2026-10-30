from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from dh_climate_app.ingress import OperationsWebServer
from dh_climate_app.operations import build_operations_snapshot, _entity


def make_snapshot(online: bool):
    s = lambda **kw: SimpleNamespace(**kw)
    now = datetime.now(timezone.utc)
    config = s(
        rooms=[s(
            room_id="bedroom", name="Bedroom",
            temperature_sensors=("sensor.bedroom",), humidity_sensors=(),
            window_sensors=(),
            devices=(s(
                entity_id="switch.relay_15", device_type="virtual",
                device_class=s(value="fast"), function="heat",
                resource="home_heating",
            ),),
        )],
        resources={},
        outdoor=s(temperature_sources=("sensor.outdoor",), humidity_sources=()),
        global_config=s(we_at_home="", night_mode=""),
        heating_source="boiler", vrf_enabled=False,
    )
    states = {
        "sensor.bedroom": s(state="21.0", attributes={}, last_updated=now),
        "switch.relay_15": s(state="on", attributes={}, last_updated=now),
    }
    return build_operations_snapshot(
        config=config, outdoor=s(
            season=s(value="heat"), raw_temperature=8.4, current_temperature=8.2,
            avg_24h_temperature=9.0, current_humidity=None,
            temperature_source="sensor.outdoor", stale=False,
        ),
        weather=None,
        room_states={
            "bedroom": s(
                current_temperature=21.0, current_humidity=None,
                target_temperature=22.0, effective_profile=s(value="day"),
                hvac_mode="heat", hvac_action=s(value="heating"),
                window_state="not_configured", window_cooling_blocked=False,
            )
        },
        health=s(climate_state="healthy", rooms={"bedroom": "healthy"}),
        problems=(),
        demands={},
        states=states if online else {},
        version="test",
        ha_connected=online,
    )


class OperationsProjectionTests(unittest.TestCase):
    def test_facts_have_clear_provenance(self):
        snap = make_snapshot(True)
        self.assertEqual(snap["schema_version"], 1)
        self.assertEqual(snap["rooms"][0]["devices"][0]["entity_id"], "switch.relay_15")
        self.assertEqual(snap["rooms"][0]["devices"][0]["observed"]["state"], "on")
        self.assertIsNone(snap["rooms"][0]["devices"][0]["hvac_action"])
        self.assertEqual(snap["home"]["heating_source"], "boiler")
        self.assertEqual(snap["weather"]["temperature"], 8.2)
        self.assertEqual(snap["rooms"][0]["name"], "Bedroom")
        json.dumps(snap, allow_nan=False)

    def test_weather_source_attributes_are_limited_to_measurements(self):
        sample = SimpleNamespace(
            state="partlycloudy",
            attributes={
                "temperature": 8.25, "humidity": 63,
                "api_token": "never-expose", "forecast": [1, 2],
            },
            last_updated=datetime.now(timezone.utc),
        )
        result = _entity("weather.home", {"weather.home": sample})
        self.assertEqual(result["attributes"], {"temperature": 8.25, "humidity": 63.0})
        self.assertNotIn("api_token", json.dumps(result))
        self.assertEqual(_entity("sensor.outdoor", {"sensor.outdoor": sample})["attributes"], {})

    def test_friendly_names_are_projection_only_and_never_replace_ids(self):
        snap = make_snapshot(True)
        self.assertIsNone(snap["rooms"][0]["friendly_name"])
        self.assertIsNone(snap["rooms"][0]["sensors"]["temperature"][0]["friendly_name"])

        now = datetime.now(timezone.utc)
        info = lambda value, friendly: SimpleNamespace(
            state=value,
            attributes={"friendly_name": friendly, "secret": "must-not-leak"},
            last_updated=now,
        )
        canonical = "climate.dh_climate_app_bedroom"
        entity = _entity("sensor.bedroom", {"sensor.bedroom": info("21", "Температура спальни")})
        self.assertEqual(entity["entity_id"], "sensor.bedroom")
        self.assertEqual(entity["friendly_name"], "Температура спальни")
        self.assertNotIn("secret", json.dumps(entity, ensure_ascii=False))

        empty = _entity("switch.relay", {"switch.relay": info("on", "  ")})
        self.assertIsNone(empty["friendly_name"])
        self.assertIsNone(_entity("sensor.missing", {})["friendly_name"])
        malformed = _entity("sensor.bad", {"sensor.bad": info("22", {"ru": "No"})})
        self.assertIsNone(malformed["friendly_name"])

        base = make_snapshot(True)
        self.assertEqual(base["rooms"][0]["id"], "bedroom")
        self.assertEqual(base["rooms"][0]["name"], "Bedroom")

    def test_offline_does_not_expose_stale_live_facts(self):
        snap = make_snapshot(False)
        self.assertFalse(snap["app"]["ha_connected"])
        self.assertEqual(snap["app"]["health"], "unknown")
        self.assertIsNone(snap["rooms"][0]["temperature"])
        self.assertIsNone(snap["rooms"][0]["devices"][0]["observed"]["state"])
        self.assertIsNone(snap["weather"]["temperature"])


class OperationsIngressTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = OperationsWebServer(
            make_snapshot(False), host="127.0.0.1", port=0,
            allowed_peers=("127.0.0.1",),
        )
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.stop()

    async def request(self, method, path):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.server.bound_port)
        writer.write(
            (method + " " + path + " HTTP/1.1\r\nHost: localhost\r\n\r\n").encode()
        )
        await writer.drain()
        response = await reader.read()
        writer.close()
        await writer.wait_closed()
        return response

    async def test_read_only_routes(self):
        response = await self.request("GET", "/api/snapshot")
        self.assertIn(b"200 OK", response.split(b"\r\n", 1)[0])
        payload = json.loads(response.split(b"\r\n\r\n", 1)[1])
        self.assertEqual(payload["rooms"][0]["id"], "bedroom")
        self.assertNotIn(b"SUPERVISOR_TOKEN", response)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            response = await self.request(method, "/api/snapshot")
            self.assertIn(b"405 Method Not Allowed", response.split(b"\r\n", 1)[0])

    async def test_static_assets_and_no_traversal(self):
        self.assertIn(b"200 OK", await self.request("GET", "/"))
        self.assertIn(b"200 OK", await self.request("GET", "/app.js"))
        self.assertIn(b"200 OK", await self.request("GET", "/i18n/ru.json"))
        self.assertIn(b"404 Not Found", await self.request("GET", "/../../data/options.json"))

    async def test_server_rejects_untrusted_peer(self):
        self.server.allowed_peers = frozenset({"172.30.32.2"})
        self.assertIn(b"403 Forbidden", await self.request("GET", "/api/snapshot"))

    async def test_event_stream_updates(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.server.bound_port)
        writer.write(b"GET /api/events HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
        self.assertIn(b"text/event-stream", headers)
        initial = await asyncio.wait_for(reader.readuntil(b"\n\n"), timeout=2)
        self.assertIn(b'"ha_connected":false', initial)
        await self.server.publish(make_snapshot(True))
        updated = await asyncio.wait_for(reader.readuntil(b"\n\n"), timeout=2)
        self.assertIn(b'"ha_connected":true', updated)
        writer.close()


if __name__ == "__main__":
    unittest.main()
