from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import unittest

from dh_climate_app.diagnostics import (
    BoundedDiagnosticLogHandler, sanitize_export,
)
from dh_climate_app.ingress import OperationsWebServer


class DiagnosticPrivacyTests(unittest.TestCase):
    def test_recursive_redaction_without_losing_configuration(self):
        raw = {
            "options": {
                "rooms": [{"id": "bedroom", "name": "Спальня"}],
                "outdoor": {"temperature_sources": ["sensor.outdoor"]},
                "mqtt_password": "do-not-export",
                "SUPERVISOR_TOKEN": "do-not-export",
                "nested": {"api_key": "do-not-export"},
            },
            "author_id": "private-user-id",
            "error": "Bearer abcdef01 https://api.example.org/?access_token=abc123&ok=1",
        }
        serialized = json.dumps(sanitize_export(raw), ensure_ascii=False)
        self.assertIn("sensor.outdoor", serialized)
        self.assertIn("Спальня", serialized)
        self.assertIn("[REDACTED]", serialized)
        self.assertNotIn("do-not-export", serialized)
        self.assertNotIn("private-user-id", serialized)
        self.assertNotIn("abcdef01", serialized)
        self.assertNotIn("abc123", serialized)

    def test_recent_log_is_bounded_and_redacts_credentials(self):
        collector = BoundedDiagnosticLogHandler(capacity=2)
        logger = logging.getLogger("dh_climate_app.diagnostic_test")
        logger.addHandler(collector)
        previous = logger.level
        logger.setLevel(logging.WARNING)
        try:
            logger.warning("Bearer aSecretToHide")
            logger.warning("Source unavailable: sensor.garden")
            logger.error("Failed request ?token=unknown-private")
        finally:
            logger.removeHandler(collector)
            logger.setLevel(previous)
        recent = collector.snapshot()
        self.assertEqual(len(recent), 2)
        self.assertIn("sensor.garden", recent[0]["message"])
        self.assertNotIn("unknown-private", str(recent))


class _Editor:
    async def state(self):
        return {
            "options": {
                "rooms": [], "password": "never-display",
                "providers": [{"id": "google", "entity_id": "weather.asyl_mura"}],
            },
            "dirty": True, "pending_restart": False, "revision": 2,
            "author_id": "private-user",
        }


class _Labels:
    async def state(self):
        return {"labels": {"provider:google": {"ru": "Google погода"}}}


class _Catalog:
    async def get(self):
        return {"entities": [
            {"entity_id": "sensor.weather_google",
             "name": "Температура Google", "state": "7.2"}
        ]}


class DiagnosticsHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = OperationsWebServer(
            {"app": {"version": "0.2.21"}, "weather": {"season": "heat"}},
            host="127.0.0.1", port=0, allowed_peers=("127.0.0.1",),
            editor=_Editor(), labels=_Labels(), catalog=_Catalog(),
            diagnostics_provider=lambda: {
                "ha_connected": True, "queued_commands": 0,
                "SUPERVISOR_TOKEN": "do-not-send",
            },
        )
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.stop()

    async def request(self, method="GET", admin=False):
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", self.server.bound_port,
        )
        auth = (
            "X-Remote-User-Id: test-user\r\n"
            "X-Remote-User-Groups: system-admin\r\n"
        ) if admin else ""
        writer.write(
            (f"{method} /api/diagnostics HTTP/1.1\r\n"
             f"Host: localhost\r\n{auth}\r\n").encode()
        )
        await writer.drain()
        response = await reader.read()
        writer.close()
        await writer.wait_closed()
        code = int(response.split(b" ", 2)[1])
        return code, response.split(b"\r\n\r\n", 1)[1]

    async def test_admin_only_and_read_only(self):
        self.assertEqual((await self.request())[0], 403)
        self.assertEqual((await self.request("POST", admin=True))[0], 405)
        self.assertEqual((await self.request("GET", admin=True))[0], 200)

    async def test_complete_report_without_credentials(self):
        code, body = await self.request(admin=True)
        self.assertEqual(code, 200)
        self.assertNotIn(b"never-display", body)
        self.assertNotIn(b"do-not-send", body)
        self.assertNotIn(b"private-user", body)
        report = json.loads(body)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["snapshot"]["weather"]["season"], "heat")
        self.assertEqual(report["manifest"]["options"]["providers"][0]["id"], "google")
        self.assertEqual(report["manifest"]["options"]["password"], "[REDACTED]")
        self.assertTrue(report["manifest"]["dirty"])
        self.assertEqual(report["entity_catalog"]["entities"][0]["state"], "7.2")
        self.assertEqual(report["runtime"]["queued_commands"], 0)
        self.assertEqual(report["labels"]["labels"]["provider:google"]["ru"], "Google погода")
        self.assertEqual(report["errors"], {})


if __name__ == "__main__":
    unittest.main()
