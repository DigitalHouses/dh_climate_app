from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from dh_climate_app.config import parse_options
from dh_climate_app.core import Season
from dh_climate_app.devices import DesiredDeviceState, compile_room_devices
from dh_climate_app.events import ClimateEventEngine
from dh_climate_app.executor import DeviceExecutor
from dh_climate_app.ha_client import HaState
from dh_climate_app.outdoor import OutdoorState
from dh_climate_app.persistence import StateStore
from dh_climate_app.problems import collect_problems
from dh_climate_app.rooms import RoomEngine
from test_config import options


def actual(entity_id: str, state: str, **attributes) -> HaState:
    now = datetime.now(timezone.utc)
    return HaState(entity_id, state, attributes, now, now)


class FakeHa:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    async def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))
        return {}


class FakeClimateLog:
    def __init__(self) -> None:
        self.entries: list[tuple[str, str, int]] = []

    def write2climate_log(self, title, message, *, level):
        self.entries.append((title, message, level))


class ActuatorSafetyBlockTests(unittest.IsolatedAsyncioTestCase):
    """Cross-module contract for the actuator/safety release block.

    These tests intentionally exercise config -> room truth -> desired devices
    -> executor -> Problem/Event rather than retesting each helper in isolation.
    """

    def _raw(self) -> dict:
        raw = options()
        raw["ac_min_outdoor_temperature"] = -10.0
        room = raw["rooms"][0]
        room["fast_heat"] = (
            "switch.radiator, switch.stubborn, "
            "climate.heatpump, climate.narrow"
        )
        room["fast_cool"] = "climate.heatpump"
        room["window_sensors"] = (
            "binary_sensor.window_a, binary_sensor.window_b"
        )
        room["window_off_devices"] = (
            "switch.radiator, climate.heatpump"
        )
        room["humidity_mode"] = "off"
        return raw

    def _build(
        self,
        *,
        season: Season,
        room_temperature: float,
        window_a: str = "off",
        window_b: str = "off",
    ):
        config = parse_options(self._raw())
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        store = StateStore(Path(directory.name) / "dh_climate.db")
        store.initialize(config)

        states = {
            "sensor.living_room_temperature": str(room_temperature),
            "sensor.living_room_humidity": "45",
            "binary_sensor.window_a": window_a,
            "binary_sensor.window_b": window_b,
            "input_boolean.we_at_home": "on",
            "input_boolean.night_mode": "off",
        }
        rooms = RoomEngine(config=config, store=store).evaluate_all(
            states,
            season=season,
        )
        return config, rooms

    @staticmethod
    def _outdoor(
        *,
        season: Season,
        temperature: float = 5.0,
    ) -> OutdoorState:
        now = datetime.now(timezone.utc)
        return OutdoorState(
            observed_at=now,
            current_temperature=temperature,
            current_humidity=45.0,
            avg_24h_temperature=temperature,
            avg_24h_humidity=45.0,
            temperature_source="sensor.outdoor_temperature",
            humidity_source="sensor.outdoor_humidity",
            heat_threshold=12.0,
            cool_threshold=20.0,
            hysteresis=0.5,
            season=season,
        )

    def _desired(
        self,
        *,
        season: Season,
        room_temperature: float,
        outdoor_temperature: float,
        window_a: str = "off",
        window_b: str = "off",
    ):
        config, rooms = self._build(
            season=season,
            room_temperature=room_temperature,
            window_a=window_a,
            window_b=window_b,
        )
        desired = compile_room_devices(
            config=config,
            room_states=rooms,
            humidity_states={},
            outdoor_temperature=outdoor_temperature,
        )
        return rooms, {item.entity_id: item for item in desired}

    def test_heat_policy_bundle_slow_window_and_cold_weather(self) -> None:
        rooms, normal = self._desired(
            season=Season.HEAT,
            room_temperature=20.0,
            outdoor_temperature=5.0,
        )

        self.assertEqual("heating", rooms["living_room"].control_action.value)
        self.assertTrue(normal["switch.radiator"].power)
        self.assertTrue(normal["switch.stubborn"].power)
        self.assertEqual("heat", normal["climate.heatpump"].hvac_mode)
        self.assertEqual(
            23.0,
            normal["climate.heatpump"].target_temperature,
        )
        self.assertEqual("heat", normal["climate.narrow"].hvac_mode)
        self.assertEqual(23.0, normal["climate.narrow"].target_temperature)

        # SLOW is season-driven and uses its own local thermostat target.
        self.assertEqual("heat", normal["climate.floor"].hvac_mode)
        self.assertEqual(27.0, normal["climate.floor"].target_temperature)

        _, cold = self._desired(
            season=Season.HEAT,
            room_temperature=20.0,
            outdoor_temperature=-15.0,
        )
        # Only the reversible heat/cool climate is blocked by low outdoor temp.
        self.assertEqual("off", cold["climate.heatpump"].hvac_mode)
        self.assertTrue(cold["switch.radiator"].power)
        self.assertTrue(cold["switch.stubborn"].power)
        self.assertEqual("heat", cold["climate.narrow"].hvac_mode)
        self.assertEqual("heat", cold["climate.floor"].hvac_mode)

        window_rooms, window = self._desired(
            season=Season.HEAT,
            room_temperature=20.0,
            outdoor_temperature=5.0,
            window_a="on",
        )
        # Window is context only; room thermostat truth remains heating.
        self.assertEqual(
            "heating",
            window_rooms["living_room"].control_action.value,
        )
        # Only explicitly listed devices are inhibited.
        self.assertFalse(window["switch.radiator"].power)
        self.assertEqual("off", window["climate.heatpump"].hvac_mode)
        self.assertTrue(window["switch.stubborn"].power)
        self.assertEqual("heat", window["climate.narrow"].hvac_mode)
        self.assertEqual("heat", window["climate.floor"].hvac_mode)

    def test_cooling_is_not_blocked_by_heating_only_cold_weather_rule(self) -> None:
        _, desired = self._desired(
            season=Season.COOL,
            room_temperature=30.0,
            outdoor_temperature=-20.0,
        )

        self.assertEqual("cool", desired["climate.heatpump"].hvac_mode)
        self.assertEqual(
            24.0,
            desired["climate.heatpump"].target_temperature,
        )
        self.assertFalse(desired["switch.radiator"].power)
        self.assertFalse(desired["switch.stubborn"].power)
        self.assertEqual("off", desired["climate.narrow"].hvac_mode)
        self.assertEqual("off", desired["climate.floor"].hvac_mode)

    async def test_target_out_of_range_is_problem_event_and_never_a_service_call(
        self,
    ) -> None:
        rooms, desired = self._desired(
            season=Season.HEAT,
            room_temperature=20.0,
            outdoor_temperature=5.0,
        )
        narrow = desired["climate.narrow"]

        ha = FakeHa()
        climate_log = FakeClimateLog()
        executor = DeviceExecutor(ha, climate_log=climate_log)
        actual_state = actual(
            "climate.narrow",
            "heat",
            temperature=25.0,
            hvac_modes=["off", "heat"],
            min_temp=25.0,
            max_temp=30.0,
        )

        summary = await executor.reconcile(
            [narrow],
            {"climate.narrow": actual_state},
            now_monotonic=100,
        )

        self.assertEqual(0, summary.commands)
        self.assertEqual([], ha.calls)
        self.assertEqual("target_out_of_range", summary.problems[0].reason)
        self.assertEqual(
            "target=23.0; min=25.0",
            summary.problems[0].details,
        )

        outdoor = self._outdoor(season=Season.HEAT)
        problems = collect_problems(
            outdoor=outdoor,
            rooms=rooms,
            humidity={},
            execution=summary.problems,
        )
        self.assertEqual("device_target_out_of_range", problems[0].code)

        events = ClimateEventEngine()
        events.observe(
            outdoor=outdoor,
            weather=None,
            rooms=rooms,
            problems=(),
            observed_at=outdoor.observed_at,
        )
        started = events.observe(
            outdoor=outdoor,
            weather=None,
            rooms=rooms,
            problems=problems,
            observed_at=outdoor.observed_at,
        )
        self.assertEqual("problem_started", started[0]["event_type"])
        self.assertEqual(
            "device_target_out_of_range",
            started[0]["problem_id"],
        )
        self.assertEqual("living_room", started[0]["room_id"])
        self.assertEqual("climate.narrow", started[0]["entity_id"])

        # A target inside the physical device range removes the block without
        # emitting any unnecessary service call when HA already matches.
        safe = replace(narrow, target_temperature=25.0)
        recovered_summary = await executor.reconcile(
            [safe],
            {"climate.narrow": actual_state},
            now_monotonic=101,
        )
        self.assertEqual(0, recovered_summary.commands)
        self.assertEqual((), recovered_summary.problems)
        self.assertEqual([], ha.calls)

        recovered_problems = collect_problems(
            outdoor=outdoor,
            rooms=rooms,
            humidity={},
            execution=recovered_summary.problems,
        )
        recovered = events.observe(
            outdoor=outdoor,
            weather=None,
            rooms=rooms,
            problems=recovered_problems,
            observed_at=outdoor.observed_at,
        )
        self.assertEqual("problem_recovered", recovered[0]["event_type"])
        self.assertEqual(
            "device_target_out_of_range",
            recovered[0]["problem_id"],
        )
        self.assertTrue(
            any(
                "SKIP target_out_of_range" in message
                for _, message, _ in climate_log.entries
            )
        )
        self.assertTrue(
            any(
                "UNBLOCKED" in message
                for _, message, _ in climate_log.entries
            )
        )

    async def test_no_confirmation_retries_cools_down_and_recovers(self) -> None:
        rooms, desired = self._desired(
            season=Season.HEAT,
            room_temperature=20.0,
            outdoor_temperature=5.0,
        )
        stubborn = desired["switch.stubborn"]

        ha = FakeHa()
        climate_log = FakeClimateLog()
        executor = DeviceExecutor(
            ha,
            climate_log=climate_log,
            retry_seconds=5,
            max_attempts=2,
            cooldown_seconds=300,
            settle_seconds=5,
        )
        still_off = {
            "switch.stubborn": actual("switch.stubborn", "off"),
        }

        first = await executor.reconcile(
            [stubborn],
            still_off,
            now_monotonic=100,
        )
        too_soon = await executor.reconcile(
            [stubborn],
            still_off,
            now_monotonic=101,
        )
        retry = await executor.reconcile(
            [stubborn],
            still_off,
            now_monotonic=105,
        )
        last_confirmation_window = await executor.reconcile(
            [stubborn],
            still_off,
            now_monotonic=106,
        )
        cooldown = await executor.reconcile(
            [stubborn],
            still_off,
            now_monotonic=110,
        )

        self.assertEqual(1, first.commands)
        self.assertEqual(0, too_soon.commands)
        self.assertEqual(1, retry.commands)
        self.assertEqual(0, last_confirmation_window.commands)
        self.assertEqual(0, cooldown.commands)
        self.assertEqual(2, len(ha.calls))
        self.assertEqual((), last_confirmation_window.problems)
        self.assertEqual("no_confirmation", cooldown.problems[0].reason)

        outdoor = self._outdoor(season=Season.HEAT)
        problems = collect_problems(
            outdoor=outdoor,
            rooms=rooms,
            humidity={},
            execution=cooldown.problems,
        )
        self.assertEqual("device_no_confirmation", problems[0].code)

        events = ClimateEventEngine()
        events.observe(
            outdoor=outdoor,
            weather=None,
            rooms=rooms,
            problems=(),
            observed_at=outdoor.observed_at,
        )
        started = events.observe(
            outdoor=outdoor,
            weather=None,
            rooms=rooms,
            problems=problems,
            observed_at=outdoor.observed_at,
        )
        self.assertEqual("problem_started", started[0]["event_type"])
        self.assertEqual("device_no_confirmation", started[0]["problem_id"])

        # The emulator eventually changes state. A real state_changed event
        # starts the settle window; only after it expires may VERIFIED_HA occur.
        self.assertTrue(
            executor.observe_state_change(
                "switch.stubborn",
                now_monotonic=111,
            )
        )
        recovered_summary = await executor.reconcile(
            [stubborn],
            {"switch.stubborn": actual("switch.stubborn", "on")},
            now_monotonic=116,
        )
        self.assertEqual(0, recovered_summary.commands)
        self.assertEqual((), recovered_summary.problems)

        recovered_problems = collect_problems(
            outdoor=outdoor,
            rooms=rooms,
            humidity={},
            execution=recovered_summary.problems,
        )
        recovered = events.observe(
            outdoor=outdoor,
            weather=None,
            rooms=rooms,
            problems=recovered_problems,
            observed_at=outdoor.observed_at,
        )
        self.assertEqual("problem_recovered", recovered[0]["event_type"])
        self.assertEqual("device_no_confirmation", recovered[0]["problem_id"])

        messages = [message for _, message, _ in climate_log.entries]
        self.assertTrue(any("RETRY 2/2" in message for message in messages))
        self.assertTrue(any("COOLDOWN 300s" in message for message in messages))
        self.assertTrue(any("VERIFIED_HA" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
