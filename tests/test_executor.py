from __future__ import annotations

import unittest
from datetime import datetime, timezone

from dh_climate_app.devices import DesiredDeviceState
from dh_climate_app.executor import DeviceExecutor
from dh_climate_app.ha_client import HaState


def actual(entity_id: str, state: str, **attributes) -> HaState:
    now = datetime.now(timezone.utc)
    return HaState(entity_id, state, attributes, now, now)


class FakeHa:
    def __init__(self) -> None:
        self.calls = []

    async def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))
        return {}


class ExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_switch_is_idempotent(self) -> None:
        ha = FakeHa()
        executor = DeviceExecutor(ha)
        summary = await executor.reconcile(
            [
                DesiredDeviceState(
                    entity_id="switch.heater",
                    domain="switch",
                    power=True,
                )
            ],
            {"switch.heater": actual("switch.heater", "on")},
        )
        self.assertEqual(0, summary.commands)
        self.assertEqual([], ha.calls)

    async def test_climate_mode_and_target(self) -> None:
        ha = FakeHa()
        executor = DeviceExecutor(ha)
        summary = await executor.reconcile(
            [
                DesiredDeviceState(
                    entity_id="climate.floor",
                    domain="climate",
                    hvac_mode="heat",
                    target_temperature=27,
                )
            ],
            {
                "climate.floor": actual(
                    "climate.floor",
                    "off",
                    temperature=22,
                )
            },
            now_monotonic=100,
        )
        self.assertEqual(2, summary.commands)
        self.assertEqual("set_hvac_mode", ha.calls[0][1])
        self.assertEqual("set_temperature", ha.calls[1][1])

    async def test_unavailable_device_is_not_commanded(self) -> None:
        ha = FakeHa()
        executor = DeviceExecutor(ha)
        summary = await executor.reconcile(
            [
                DesiredDeviceState(
                    entity_id="switch.heater",
                    domain="switch",
                    power=False,
                )
            ],
            {"switch.heater": actual("switch.heater", "unavailable")},
        )
        self.assertEqual(0, summary.commands)
        self.assertEqual("unavailable", summary.problems[0].reason)


if __name__ == "__main__":
    unittest.main()
