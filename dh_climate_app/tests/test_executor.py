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


class FakeClimateLog:
    def __init__(self) -> None:
        self.entries = []

    def write2climate_log(self, title, message, *, level):
        self.entries.append((title, message, level))


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
                    source="room:livingroom:fast",
                )
            ],
            {"switch.heater": actual("switch.heater", "unavailable")},
        )
        self.assertEqual(0, summary.commands)
        self.assertEqual("unavailable", summary.problems[0].reason)
        self.assertEqual("livingroom", summary.problems[0].room_id)

    async def test_fast_trace_requires_event_and_settle_before_verification(self) -> None:
        ha = FakeHa()
        climate_log = FakeClimateLog()
        executor = DeviceExecutor(
            ha,
            climate_log=climate_log,
            settle_seconds=5,
        )
        desired = DesiredDeviceState(
            entity_id="climate.fast",
            domain="climate",
            hvac_mode="heat",
            target_temperature=22.0,
            source="room:livingroom:fast",
        )
        matching = {
            "climate.fast": actual(
                "climate.fast",
                "heat",
                temperature=22.0,
                hvac_modes=["off", "heat", "cool"],
                min_temp=5,
                max_temp=35,
            )
        }

        first = await executor.reconcile(
            [desired],
            {
                "climate.fast": actual(
                    "climate.fast",
                    "off",
                    temperature=24.0,
                    hvac_modes=["off", "heat", "cool"],
                    min_temp=5,
                    max_temp=35,
                )
            },
            now_monotonic=100,
        )

        # A matching state alone is not confirmation. The executor requires a
        # post-command state_changed event and then a settle window.
        before_event = await executor.reconcile(
            [desired],
            matching,
            now_monotonic=101,
        )
        self.assertFalse(
            any("VERIFIED_HA" in message for _, message, _ in climate_log.entries)
        )

        self.assertTrue(
            executor.observe_state_change(
                "climate.fast",
                now_monotonic=101,
            )
        )
        settling = await executor.reconcile(
            [desired],
            matching,
            now_monotonic=101,
        )
        self.assertFalse(
            any("VERIFIED_HA" in message for _, message, _ in climate_log.entries)
        )

        verified = await executor.reconcile(
            [desired],
            matching,
            now_monotonic=106,
        )

        self.assertEqual(2, first.commands)
        self.assertEqual(0, before_event.commands)
        self.assertEqual(0, settling.commands)
        self.assertEqual(0, verified.commands)
        self.assertTrue(
            any(
                title == "FAST · livingroom"
                and "desired=mode=heat target=22.0" in message
                for title, message, _ in climate_log.entries
            )
        )
        self.assertTrue(
            any(
                "CALL climate.set_hvac_mode -> heat" in message
                for _, message, _ in climate_log.entries
            )
        )
        self.assertTrue(
            any(
                "CALL climate.set_temperature -> 22.0" in message
                for _, message, _ in climate_log.entries
            )
        )
        self.assertTrue(
            any("SENT" in message for _, message, _ in climate_log.entries)
        )
        self.assertTrue(
            any("VERIFIED_HA" in message for _, message, _ in climate_log.entries)
        )
        self.assertFalse(
            any("CONFIRMED" in message for _, message, _ in climate_log.entries)
        )

    async def test_unavailable_trace_is_not_repeated_each_reconcile(self) -> None:
        ha = FakeHa()
        climate_log = FakeClimateLog()
        executor = DeviceExecutor(ha, climate_log=climate_log)
        desired = DesiredDeviceState(
            entity_id="switch.heater",
            domain="switch",
            power=True,
            source="room:livingroom:fast",
        )
        states = {
            "switch.heater": actual("switch.heater", "unavailable"),
        }

        await executor.reconcile([desired], states, now_monotonic=100)
        await executor.reconcile([desired], states, now_monotonic=110)

        skips = [
            message
            for _, message, _ in climate_log.entries
            if "SKIP unavailable" in message
        ]
        self.assertEqual(1, len(skips))
        self.assertEqual([], ha.calls)

    async def test_retry_is_bounded_and_last_attempt_gets_confirmation_window(self) -> None:
        ha = FakeHa()
        climate_log = FakeClimateLog()
        executor = DeviceExecutor(
            ha,
            climate_log=climate_log,
            retry_seconds=5,
            max_attempts=2,
            cooldown_seconds=300,
        )
        desired = DesiredDeviceState(
            entity_id="switch.heater",
            domain="switch",
            power=True,
            source="room:livingroom:fast",
        )
        states = {"switch.heater": actual("switch.heater", "off")}

        first = await executor.reconcile([desired], states, now_monotonic=100)
        too_soon = await executor.reconcile([desired], states, now_monotonic=101)
        second = await executor.reconcile([desired], states, now_monotonic=105)
        final_window = await executor.reconcile(
            [desired],
            states,
            now_monotonic=106,
        )
        cooldown = await executor.reconcile([desired], states, now_monotonic=110)

        self.assertEqual(1, first.commands)
        self.assertEqual(0, too_soon.commands)
        self.assertEqual(1, second.commands)
        self.assertEqual(0, final_window.commands)
        self.assertEqual(0, cooldown.commands)
        self.assertEqual(2, len(ha.calls))
        self.assertEqual((), second.problems)
        self.assertEqual((), final_window.problems)
        self.assertEqual("no_confirmation", cooldown.problems[0].reason)
        self.assertTrue(
            any("RETRY 2/2" in message for _, message, _ in climate_log.entries)
        )
        self.assertTrue(
            any("COOLDOWN 300s" in message for _, message, _ in climate_log.entries)
        )

    async def test_verified_state_drift_waits_for_settle_before_correction(self) -> None:
        ha = FakeHa()
        climate_log = FakeClimateLog()
        executor = DeviceExecutor(
            ha,
            climate_log=climate_log,
            settle_seconds=5,
        )
        desired = DesiredDeviceState(
            entity_id="switch.heater",
            domain="switch",
            power=True,
            source="room:livingroom:fast",
        )

        # An already-correct state establishes the stable baseline.
        await executor.reconcile(
            [desired],
            {"switch.heater": actual("switch.heater", "on")},
            now_monotonic=100,
        )

        self.assertTrue(
            executor.observe_state_change(
                "switch.heater",
                now_monotonic=101,
            )
        )

        immediate = await executor.reconcile(
            [desired],
            {"switch.heater": actual("switch.heater", "off")},
            now_monotonic=101,
        )
        corrected = await executor.reconcile(
            [desired],
            {"switch.heater": actual("switch.heater", "off")},
            now_monotonic=106,
        )

        self.assertEqual(0, immediate.commands)
        self.assertEqual(1, corrected.commands)
        self.assertEqual(1, len(ha.calls))
        self.assertTrue(
            any("DRIFT" in message for _, message, _ in climate_log.entries)
        )

    async def test_unsupported_climate_mode_is_not_commanded(self) -> None:
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
                    hvac_modes=["off", "cool"],
                    min_temp=5,
                    max_temp=35,
                )
            },
        )
        self.assertEqual(0, summary.commands)
        self.assertEqual("unsupported_mode", summary.problems[0].reason)
        self.assertEqual([], ha.calls)

    async def test_out_of_range_target_is_not_commanded(self) -> None:
        ha = FakeHa()
        executor = DeviceExecutor(ha)
        summary = await executor.reconcile(
            [
                DesiredDeviceState(
                    entity_id="climate.floor",
                    domain="climate",
                    hvac_mode="heat",
                    target_temperature=40,
                )
            ],
            {
                "climate.floor": actual(
                    "climate.floor",
                    "heat",
                    temperature=25,
                    hvac_modes=["off", "heat"],
                    min_temp=5,
                    max_temp=35,
                )
            },
        )
        self.assertEqual(0, summary.commands)
        self.assertEqual("target_out_of_range", summary.problems[0].reason)
        self.assertEqual([], ha.calls)


if __name__ == "__main__":
    unittest.main()
