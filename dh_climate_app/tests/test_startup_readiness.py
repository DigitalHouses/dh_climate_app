from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from dh_climate_app.devices import DesiredDeviceState, StartupActuatorGate
from dh_climate_app.executor import DeviceExecutor
from dh_climate_app.ha_client import HaState


def fast(mode: str = "off") -> DesiredDeviceState:
    return DesiredDeviceState(
        entity_id="climate.bedroom_ac",
        domain="climate",
        hvac_mode=mode,
        target_temperature=30.0 if mode == "heat" else None,
        source="room:bedroom:fast",
    )


def slow(mode: str = "heat") -> DesiredDeviceState:
    return DesiredDeviceState(
        entity_id="climate.floor",
        domain="climate",
        hvac_mode=mode,
        target_temperature=27.0 if mode == "heat" else None,
        source="room:bedroom:slow",
    )


def humidify(power: bool = False) -> DesiredDeviceState:
    return DesiredDeviceState(
        entity_id="switch.humidifier",
        domain="switch",
        power=power,
        source="room:bedroom:humidity",
    )


def room(temperature):
    return {"bedroom": SimpleNamespace(current_temperature=temperature)}


def humidity(value):
    return {"bedroom": SimpleNamespace(current_humidity=value)}


def actual(state: str, **attributes) -> HaState:
    now = datetime.now(timezone.utc)
    return HaState("climate.bedroom_ac", state, attributes, now, now)


class FakeHA:
    def __init__(self) -> None:
        self.calls = []

    async def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))
        return {}


class StartupActuatorReadinessTests(unittest.TestCase):
    def test_missing_startup_temperature_does_not_command_off(self):
        gate = StartupActuatorGate()
        for second in (0, 10, 29):
            self.assertEqual(
                [],
                gate.filter(
                    [fast("off")],
                    room_states=room(None),
                    humidity_states={},
                    outdoor_available=True,
                    now_monotonic=second,
                ),
            )
            self.assertEqual(("climate.bedroom_ac",), gate.deferred_entities)

        self.assertEqual(
            [fast("heat")],
            gate.filter(
                [fast("heat")],
                room_states=room(24.7),
                humidity_states={},
                outdoor_available=True,
                now_monotonic=30,
            ),
        )
        self.assertFalse(gate.deferred_entities)

    def test_missing_outdoor_defers_thermal_but_not_ready_humidity(self):
        gate = StartupActuatorGate()
        devices = [fast(), slow(), humidify(True)]
        self.assertEqual(
            [humidify(True)],
            gate.filter(
                devices,
                room_states=room(22.0),
                humidity_states=humidity(44.0),
                outdoor_available=False,
                now_monotonic=0,
            ),
        )
        self.assertEqual(
            devices,
            gate.filter(
                devices,
                room_states=room(22.0),
                humidity_states=humidity(44.0),
                outdoor_available=True,
                now_monotonic=5,
            ),
        )

    def test_slow_requires_season_not_room_temperature(self):
        gate = StartupActuatorGate()
        self.assertEqual(
            [slow()],
            gate.filter(
                [slow()],
                room_states=room(None),
                humidity_states={},
                outdoor_available=True,
                now_monotonic=0,
            ),
        )

    def test_missing_humidity_does_not_inhibit_thermal_devices(self):
        gate = StartupActuatorGate()
        self.assertEqual(
            [fast("heat")],
            gate.filter(
                [fast("heat"), humidify()],
                room_states=room(20.0),
                humidity_states=humidity(None),
                outdoor_available=True,
                now_monotonic=0,
            ),
        )

    def test_later_sensor_loss_preserves_immediate_fail_safe_off(self):
        gate = StartupActuatorGate()
        gate.filter(
            [fast("heat")],
            room_states=room(20.0),
            humidity_states={},
            outdoor_available=True,
            now_monotonic=0,
        )
        self.assertEqual(
            [fast("off")],
            gate.filter(
                [fast("off")],
                room_states=room(None),
                humidity_states={},
                outdoor_available=True,
                now_monotonic=4,
            ),
        )

    def test_later_outdoor_loss_preserves_immediate_season_off(self):
        gate = StartupActuatorGate()
        gate.filter(
            [fast("heat")],
            room_states=room(20.0),
            humidity_states={},
            outdoor_available=True,
            now_monotonic=0,
        )
        self.assertEqual(
            [fast("off")],
            gate.filter(
                [fast("off")],
                room_states=room(20.0),
                humidity_states={},
                outdoor_available=False,
                now_monotonic=4,
            ),
        )

    def test_timeout_resumes_fail_safe_instead_of_waiting_forever(self):
        gate = StartupActuatorGate(grace_seconds=60)
        gate.filter(
            [fast()],
            room_states=room(None),
            humidity_states={},
            outdoor_available=True,
            now_monotonic=0,
        )
        self.assertEqual(
            [fast()],
            gate.filter(
                [fast()],
                room_states=room(None),
                humidity_states={},
                outdoor_available=True,
                now_monotonic=60,
            ),
        )
        self.assertTrue(gate.timed_out)

    def test_reconnect_starts_new_bounded_warmup(self):
        gate = StartupActuatorGate()
        gate.filter(
            [fast("heat")],
            room_states=room(20.0),
            humidity_states={},
            outdoor_available=True,
            now_monotonic=0,
        )
        gate.reset()
        self.assertEqual(
            [],
            gate.filter(
                [fast()],
                room_states=room(None),
                humidity_states={},
                outdoor_available=False,
                now_monotonic=100,
            ),
        )
        self.assertFalse(gate.timed_out)


class StartupSmartIRRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_warmup_eliminates_off_then_heat_ir_sequence(self):
        ha = FakeHA()
        executor = DeviceExecutor(ha)
        gate = StartupActuatorGate()

        before = gate.filter(
            [fast("off")],
            room_states=room(None),
            humidity_states={},
            outdoor_available=True,
            now_monotonic=0,
        )
        result = await executor.reconcile(
            before,
            {"climate.bedroom_ac": actual("heat", temperature=30)},
            now_monotonic=0,
        )
        self.assertEqual(0, result.commands)
        self.assertEqual([], ha.calls)

        after = gate.filter(
            [fast("heat")],
            room_states=room(24.7),
            humidity_states={},
            outdoor_available=True,
            now_monotonic=31,
        )
        result = await executor.reconcile(
            after,
            {"climate.bedroom_ac": actual("heat", temperature=30)},
            now_monotonic=31,
        )
        self.assertEqual(0, result.commands)
        self.assertEqual([], ha.calls)


if __name__ == "__main__":
    unittest.main()
