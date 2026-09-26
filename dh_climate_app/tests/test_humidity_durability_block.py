from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from dh_climate_app.config import parse_options
from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.devices import compile_room_devices
from dh_climate_app.executor import DeviceExecutor
from dh_climate_app.ha_client import HaState
from dh_climate_app.humidity import HumidityEngine
from dh_climate_app.persistence import StateStore
from dh_climate_app.rooms import RoomEngine
from dh_climate_app.telemetry import TelemetryClient
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


class HumidityDurabilityBlockTests(unittest.IsolatedAsyncioTestCase):
    def _humidity_runtime(
        self,
        *,
        mode: str,
        actuator: str,
        current_humidity: float,
        enabled: bool = True,
    ):
        raw = options()
        room = raw["rooms"][0]
        room["humidity_mode"] = mode
        room["humidity_actuator"] = actuator

        config = parse_options(raw)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        store = StateStore(Path(directory.name) / "dh_climate.db")
        store.initialize(config)
        store.set_humidity_control_enabled("living_room", enabled)

        states = {
            "sensor.living_room_temperature": "21",
            "sensor.living_room_humidity": str(current_humidity),
            "input_boolean.we_at_home": "on",
            "input_boolean.night_mode": "off",
        }
        rooms = RoomEngine(config=config, store=store).evaluate_all(
            states,
            season=Season.OFF,
        )
        humidity = HumidityEngine(config=config, store=store).evaluate_all(
            states
        )
        desired = compile_room_devices(
            config=config,
            room_states=rooms,
            humidity_states=humidity,
            outdoor_temperature=10.0,
        )
        return store, humidity["living_room"], {
            item.entity_id: item for item in desired
        }

    async def test_inactive_humidifier_can_always_be_turned_off(self) -> None:
        _, humidity, desired = self._humidity_runtime(
            mode="humidifier",
            actuator="humidifier.living_room",
            current_humidity=40.0,
            enabled=False,
        )
        actuator = desired["humidifier.living_room"]

        self.assertFalse(humidity.control_enabled)
        self.assertFalse(humidity.active)
        self.assertFalse(actuator.power)
        self.assertIsNone(actuator.target_humidity)

        ha = FakeHa()
        executor = DeviceExecutor(ha)
        summary = await executor.reconcile(
            [actuator],
            {
                "humidifier.living_room": actual(
                    "humidifier.living_room",
                    "on",
                    humidity=70.0,
                    min_humidity=60.0,
                    max_humidity=80.0,
                )
            },
            now_monotonic=100,
        )

        # The persisted target is 50%, outside this physical device's 60..80%
        # range. That must never block the safety-critical turn_off command.
        self.assertEqual(1, summary.commands)
        self.assertEqual((), summary.problems)
        self.assertEqual(
            [
                (
                    "humidifier",
                    "turn_off",
                    {"entity_id": "humidifier.living_room"},
                )
            ],
            ha.calls,
        )

    async def test_active_humidifier_applies_power_and_target(self) -> None:
        _, humidity, desired = self._humidity_runtime(
            mode="humidifier",
            actuator="humidifier.living_room",
            current_humidity=40.0,
            enabled=True,
        )
        actuator = desired["humidifier.living_room"]

        self.assertTrue(humidity.active)
        self.assertTrue(actuator.power)
        self.assertEqual(50.0, actuator.target_humidity)

        ha = FakeHa()
        executor = DeviceExecutor(ha)
        summary = await executor.reconcile(
            [actuator],
            {
                "humidifier.living_room": actual(
                    "humidifier.living_room",
                    "off",
                    humidity=45.0,
                    min_humidity=30.0,
                    max_humidity=80.0,
                )
            },
            now_monotonic=100,
        )

        self.assertEqual(2, summary.commands)
        self.assertEqual((), summary.problems)
        self.assertEqual("turn_on", ha.calls[0][1])
        self.assertEqual("set_humidity", ha.calls[1][1])
        self.assertEqual(50.0, ha.calls[1][2]["humidity"])

    async def test_switch_humidity_control_is_independent_of_thermal_season(
        self,
    ) -> None:
        store, humidity, desired = self._humidity_runtime(
            mode="dehumidifier",
            actuator="switch.dehumidifier",
            current_humidity=60.0,
            enabled=True,
        )
        self.assertTrue(humidity.active)
        self.assertTrue(desired["switch.dehumidifier"].power)

        store.set_humidity_control_enabled("living_room", False)

        raw = options()
        config = parse_options(raw)
        states = {
            "sensor.living_room_temperature": "21",
            "sensor.living_room_humidity": "60",
            "input_boolean.we_at_home": "on",
            "input_boolean.night_mode": "off",
        }
        rooms = RoomEngine(config=config, store=store).evaluate_all(
            states,
            season=Season.OFF,
        )
        humidity_states = HumidityEngine(
            config=config,
            store=store,
        ).evaluate_all(states)
        compiled = compile_room_devices(
            config=config,
            room_states=rooms,
            humidity_states=humidity_states,
            outdoor_temperature=10.0,
        )
        by_id = {item.entity_id: item for item in compiled}

        self.assertFalse(humidity_states["living_room"].active)
        self.assertFalse(by_id["switch.dehumidifier"].power)

    def test_cold_data_snapshot_restores_all_durable_control_state(self) -> None:
        raw = options()
        config = parse_options(raw)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            live = root / "live"
            backup = root / "backup"
            restored = root / "restored"
            live.mkdir()

            store = StateStore(live / "dh_climate.db")
            store.initialize(config)
            store.set_season_thresholds(11.0, 21.0)
            store.set_room_target(
                "living_room",
                Season.HEAT,
                Profile.DAY,
                24.5,
            )
            store.set_previous_action(
                "living_room",
                HvacAction.HEATING,
            )
            store.set_climate_control_enabled("living_room", False)
            store.set_humidity_target("living_room", 55.0)
            store.set_humidity_previous_active("living_room", True)
            store.set_humidity_control_enabled("living_room", False)
            self.assertTrue(store.integrity_check())

            telemetry = TelemetryClient(
                enabled=False,
                version="0.1.15",
                state_file=live / "telemetry.json",
            )
            installation_id = telemetry.installation_id
            installation_token = telemetry.installation_token

            # config.yaml declares backup: cold. This models the App's /data
            # directory after the process has no open StateStore connections.
            shutil.copytree(live, backup)
            shutil.copytree(backup, restored)

            restored_store = StateStore(restored / "dh_climate.db")
            restored_store.initialize(config)
            self.assertTrue(restored_store.integrity_check())

            thresholds = restored_store.get_season_thresholds()
            self.assertEqual((11.0, 21.0), (thresholds.heat, thresholds.cool))
            self.assertEqual(
                24.5,
                restored_store.get_room_target(
                    "living_room",
                    Season.HEAT,
                    Profile.DAY,
                ),
            )
            self.assertEqual(
                HvacAction.HEATING,
                restored_store.get_previous_action("living_room"),
            )
            self.assertFalse(
                restored_store.get_climate_control_enabled("living_room")
            )
            self.assertEqual(
                55.0,
                restored_store.get_humidity_target("living_room"),
            )
            self.assertTrue(
                restored_store.get_humidity_previous_active("living_room")
            )
            self.assertFalse(
                restored_store.get_humidity_control_enabled("living_room")
            )

            restored_telemetry = TelemetryClient(
                enabled=False,
                version="0.1.15",
                state_file=restored / "telemetry.json",
            )
            self.assertEqual(
                installation_id,
                restored_telemetry.installation_id,
            )
            self.assertEqual(
                installation_token,
                restored_telemetry.installation_token,
            )


if __name__ == "__main__":
    unittest.main()
