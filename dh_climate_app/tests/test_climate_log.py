from __future__ import annotations

import unittest

from dh_climate_app.climate_log import ClimateLog


class FakeHa:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    async def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))
        if self.fail:
            raise RuntimeError("mirror unavailable")
        return {}


class ClimateLogTests(unittest.IsolatedAsyncioTestCase):
    async def test_mirrors_to_write2climatelog(self) -> None:
        ha = FakeHa()
        climate_log = ClimateLog(ha)

        climate_log.write2climate_log("FAST · livingroom", "test message")
        await climate_log.flush()

        self.assertEqual(
            [
                (
                    "script",
                    "write2climatelog",
                    {
                        "title": "FAST · livingroom",
                        "message": "test message",
                    },
                )
            ],
            ha.calls,
        )

    async def test_mirror_failure_is_isolated(self) -> None:
        ha = FakeHa(fail=True)
        climate_log = ClimateLog(ha)

        climate_log.write2climate_log("FAST · livingroom", "test message")
        await climate_log.flush()

        self.assertEqual(1, len(ha.calls))

    async def test_mirror_preserves_write_order(self) -> None:
        ha = FakeHa()
        climate_log = ClimateLog(ha)

        climate_log.write2climate_log("FAST · livingroom", "desired=on")
        climate_log.write2climate_log("FAST · livingroom", "CALL switch.turn_on")
        climate_log.write2climate_log("FAST · livingroom", "CONFIRMED")
        await climate_log.flush()

        self.assertEqual(
            [
                "desired=on",
                "CALL switch.turn_on",
                "CONFIRMED",
            ],
            [call[2]["message"] for call in ha.calls],
        )


if __name__ == "__main__":
    unittest.main()
