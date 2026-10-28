from __future__ import annotations

from dataclasses import replace
import asyncio
from unittest.mock import AsyncMock
import time
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from dh_climate_app.config import ConfigError, parse_options
from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.devices import compile_room_devices
from dh_climate_app.discovery import global_tuning_discovery_payloads
from dh_climate_app.persistence import StateStore
from dh_climate_app.rooms import RoomState
from dh_climate_app.window_cooling import WindowCoolingGuard


def window(value):
    return {"bedroom": SimpleNamespace(window_state=value)}


def room(season=Season.COOL, action=HvacAction.COOLING, *, blocked=False):
    return RoomState(
        room_id="bedroom",
        name="Bedroom",
        current_temperature=28.0,
        current_humidity=None,
        season=season,
        effective_profile=Profile.DAY,
        target_temperature=23.0,
        climate_control_enabled=True,
        control_action=action,
        hvac_mode=season.value,
        hvac_action=action,
        control_target_temperature=23.0,
        window_state="open",
        window_cooling_blocked=blocked,
    )


def config():
    return parse_options({
        "rooms": [{
            "id": "bedroom",
            "name": "Bedroom",
            "temperature_sensors": ["sensor.bedroom_temp"],
            "window_sensors": ["binary_sensor.bedroom_window"],
            "devices": [
                {"entity": "climate.virtual_ac", "role": "fast_heat", "control": "app", "reversible": True},
                {"entity": "climate.wall_ac", "role": "fast_cool", "control": "device"},
                {"entity": "switch.radiator", "role": "fast_heat", "control": "app"},
                {"entity": "switch.floor", "role": "slow_heat", "control": "app", "actuator": "normal_closed"},
            ],
        }],
    })


class WindowDebounceTests(unittest.TestCase):
    def test_delayed_cooling_inhibit_no_polling_and_close_cancel(self):
        g = WindowCoolingGuard()
        blocked, due = g.evaluate(window("open"), delay_seconds=10, now_monotonic=100)
        self.assertFalse(blocked["bedroom"])
        self.assertEqual({"bedroom": 110}, due)
        self.assertFalse(g.evaluate(window("open"), delay_seconds=10, now_monotonic=109)[0]["bedroom"])
        self.assertTrue(g.evaluate(window("open"), delay_seconds=10, now_monotonic=110)[0]["bedroom"])
        blocked, due = g.evaluate(window("closed"), delay_seconds=10, now_monotonic=111)
        self.assertFalse(blocked["bedroom"])
        self.assertEqual({}, due)
        self.assertFalse(g.evaluate(window("open"), delay_seconds=10, now_monotonic=112)[0]["bedroom"])

    def test_unknown_does_not_fake_closed_and_no_initial_fake_open(self):
        g = WindowCoolingGuard()
        self.assertFalse(g.evaluate(window("unknown"), delay_seconds=10, now_monotonic=1)[0]["bedroom"])
        g.evaluate(window("open"), delay_seconds=10, now_monotonic=2)
        self.assertTrue(g.evaluate(window("unknown"), delay_seconds=10, now_monotonic=13)[0]["bedroom"])
        self.assertTrue(g.evaluate(window("open"), delay_seconds=10, now_monotonic=14)[0]["bedroom"])
        self.assertFalse(g.evaluate(window("closed"), delay_seconds=10, now_monotonic=15)[0]["bedroom"])

    def test_changing_delay_and_reconnect_reset(self):
        g = WindowCoolingGuard()
        g.evaluate(window("open"), delay_seconds=10, now_monotonic=20)
        self.assertTrue(g.evaluate(window("open"), delay_seconds=5, now_monotonic=25)[0]["bedroom"])
        g.reset()
        self.assertFalse(g.evaluate(window("open"), delay_seconds=10, now_monotonic=26)[0]["bedroom"])

    def test_bad_delay_rejected(self):
        g = WindowCoolingGuard()
        for delay in (-1, float("nan"), float("inf")):
            with self.subTest(delay=delay), self.assertRaises(ValueError):
                g.evaluate(window("open"), delay_seconds=delay, now_monotonic=0)


class WindowActuatorTests(unittest.TestCase):
    def _desired(self, *, season, action, blocked):
        commands = compile_room_devices(
            config=config(),
            room_states={"bedroom": room(season, action, blocked=blocked)},
            humidity_states={},
            outdoor_temperature=0.0,
        )
        return {command.entity_id: command for command in commands}

    def test_both_hardware_and_virtual_cooling_blocked(self):
        cooling = self._desired(season=Season.COOL, action=HvacAction.COOLING, blocked=False)
        self.assertEqual("cool", cooling["climate.virtual_ac"].hvac_mode)
        self.assertEqual("cool", cooling["climate.wall_ac"].hvac_mode)
        blocked = self._desired(season=Season.COOL, action=HvacAction.COOLING, blocked=True)
        self.assertEqual("off", blocked["climate.virtual_ac"].hvac_mode)
        self.assertEqual("off", blocked["climate.wall_ac"].hvac_mode)
        self.assertIsNone(blocked["climate.virtual_ac"].target_temperature)
        self.assertFalse(blocked["switch.floor"].power)

    def test_heating_radiators_floor_and_reversible_ac_ignore_windows(self):
        for blocked in (False, True):
            with self.subTest(blocked=blocked):
                commands = self._desired(season=Season.HEAT, action=HvacAction.HEATING, blocked=blocked)
                self.assertEqual("heat", commands["climate.virtual_ac"].hvac_mode)
                self.assertTrue(commands["switch.radiator"].power)
                self.assertTrue(commands["switch.floor"].power)
                self.assertEqual("off", commands["climate.wall_ac"].hvac_mode)

    def test_cool_window_does_not_force_non_requested_devices_on(self):
        commands = self._desired(season=Season.COOL, action=HvacAction.IDLE, blocked=False)
        self.assertEqual("off", commands["climate.virtual_ac"].hvac_mode)


class WindowRuntimeTimerTests(unittest.IsolatedAsyncioTestCase):
    async def test_expiry_recalculates_without_polling(self):
        from dh_climate_app.app import ClimateRuntime
        runtime = object.__new__(ClimateRuntime)
        runtime._ha_connected = True
        runtime._window_recheck_tasks = {}
        runtime._recalculate = AsyncMock()
        runtime._sync_window_rechecks({"bedroom": time.monotonic() + 0.02})
        await asyncio.sleep(0.05)
        runtime._recalculate.assert_awaited_once()
        self.assertEqual({}, runtime._window_recheck_tasks)

    async def test_closed_before_deadline_cancels_event(self):
        from dh_climate_app.app import ClimateRuntime
        runtime = object.__new__(ClimateRuntime)
        runtime._ha_connected = True
        runtime._window_recheck_tasks = {}
        runtime._recalculate = AsyncMock()
        runtime._sync_window_rechecks({"bedroom": time.monotonic() + 0.12})
        runtime._sync_window_rechecks({})
        await asyncio.sleep(0.15)
        runtime._recalculate.assert_not_awaited()
        self.assertEqual({}, runtime._window_recheck_tasks)


class WindowSettingsTests(unittest.TestCase):
    def test_sqlite_seed_preserved_and_mqtt_number_seconds(self):
        with tempfile.TemporaryDirectory() as directory:
            db = StateStore(Path(directory) / "climate.db")
            c = config()
            db.initialize(c)
            self.assertEqual(10, db.get_global_tuning("window_open_delay_seconds"))
            db.set_global_tuning("window_open_delay_seconds", 23)
            db.initialize(c)
            self.assertEqual(23, db.get_global_tuning("window_open_delay_seconds"))
            with self.assertRaises(ValueError):
                db.set_global_tuning("window_open_delay_seconds", 301)

        payload = global_tuning_discovery_payloads("0.1.33")["window_open_delay_seconds"][1]
        self.assertEqual("s", payload["unit_of_measurement"])
        self.assertEqual(300, payload["max"])
        self.assertEqual(1, payload["step"])
        self.assertEqual("number.dh_climate_app_window_open_delay_seconds", payload["default_entity_id"])

    def test_old_window_off_is_rejected_by_new_supervisor_schema(self):
        with self.assertRaises(ConfigError):
            parse_options({"rooms": [{
                "id": "bedroom", "name": "Bedroom",
                "temperature_sensors": ["sensor.bedroom"],
                "devices": [{"entity": "climate.ac", "role": "fast_cool", "control": "app", "window_off": True}],
            }]})


if __name__ == "__main__":
    unittest.main()
