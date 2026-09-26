from __future__ import annotations

import unittest

from dh_climate_app.app import ClimateRuntime
from dh_climate_app.mqtt import MqttCommand
from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.rooms import RoomState


class FakeStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Season, Profile, float]] = []
        self.threshold_calls: list[tuple[float, float]] = []
        self.heat_threshold = 15.0
        self.cool_threshold = 29.8

    def get_season_thresholds(self):
        from dh_climate_app.persistence import SeasonThresholds
        return SeasonThresholds(self.heat_threshold, self.cool_threshold)

    def set_season_thresholds(self, heat: float, cool: float) -> None:
        if heat >= cool:
            raise ValueError("heat threshold must be lower than cool threshold")
        self.heat_threshold = heat
        self.cool_threshold = cool
        self.threshold_calls.append((heat, cool))

    def set_room_target(
        self,
        room_id: str,
        season: Season,
        profile: Profile,
        target: float,
    ) -> None:
        self.calls.append((room_id, season, profile, target))


class RoomTargetCommandTests(unittest.IsolatedAsyncioTestCase):
    def runtime(self) -> ClimateRuntime:
        runtime = object.__new__(ClimateRuntime)
        runtime.store = FakeStore()
        runtime.outdoor = type(
            "FakeOutdoor",
            (),
            {
                "set_thresholds": lambda _, heat, cool: runtime.store.set_season_thresholds(
                    heat,
                    cool,
                )
            },
        )()
        runtime._last_room_states = {
            "livingroom": RoomState(
                room_id="livingroom",
                name="Living Room",
                current_temperature=26.2,
                current_humidity=None,
                season=Season.HEAT,
                effective_profile=Profile.DAY,
                target_temperature=22.0,
                climate_control_enabled=True,
                control_action=HvacAction.IDLE,
                hvac_mode="auto",
                hvac_action=HvacAction.IDLE,
                control_profile=Profile.DAY,
                control_target_temperature=22.0,
                window_state="not_configured",
            )
        }
        return runtime

    async def test_climate_target_changes_only_active_profile(self) -> None:
        runtime = self.runtime()

        await runtime._handle_room_command(
            "livingroom",
            "target_temperature",
            "23.5",
        )

        self.assertEqual(
            [("livingroom", Season.HEAT, Profile.DAY, 23.5)],
            runtime.store.calls,
        )

    async def test_interseason_thermostat_commands_do_not_change_targets(self) -> None:
        runtime = self.runtime()
        runtime._last_room_states["livingroom"] = RoomState(
            room_id="livingroom",
            name="Living Room",
            current_temperature=26.2,
            current_humidity=None,
            season=Season.OFF,
            effective_profile=Profile.DAY,
            target_temperature=None,
            climate_control_enabled=True,
            control_action=HvacAction.OFF,
            hvac_mode="off",
            hvac_action=HvacAction.OFF,
        )

        await runtime._handle_room_command(
            "livingroom",
            "target_temperature",
            "23.5",
        )
        await runtime._handle_room_command(
            "livingroom",
            "hvac_mode",
            "auto",
        )

        self.assertEqual([], runtime.store.calls)

    async def test_profile_setting_can_edit_inactive_night_target(self) -> None:
        runtime = self.runtime()

        await runtime._handle_room_profile_target_command(
            "livingroom",
            "heat_night",
            "20.0",
        )

        self.assertEqual(
            [("livingroom", Season.HEAT, Profile.NIGHT, 20.0)],
            runtime.store.calls,
        )

    async def test_season_range_pair_is_applied_atomically(self) -> None:
        runtime = self.runtime()

        await runtime._handle_season_range_commands(
            [
                MqttCommand(
                    scope="season",
                    command="target_temp_low",
                    payload="30",
                ),
                MqttCommand(
                    scope="season",
                    command="target_temp_high",
                    payload="35",
                ),
            ]
        )

        self.assertEqual([(30.0, 35.0)], runtime.store.threshold_calls)

    async def test_season_range_pair_works_in_reverse_order(self) -> None:
        runtime = self.runtime()

        await runtime._handle_season_range_commands(
            [
                MqttCommand(
                    scope="season",
                    command="target_temp_high",
                    payload="35",
                ),
                MqttCommand(
                    scope="season",
                    command="target_temp_low",
                    payload="30",
                ),
            ]
        )

        self.assertEqual([(30.0, 35.0)], runtime.store.threshold_calls)

    async def test_invalid_single_season_threshold_is_rejected(self) -> None:
        runtime = self.runtime()

        with self.assertRaises(ValueError):
            await runtime._handle_season_range_commands(
                [
                    MqttCommand(
                        scope="season",
                        command="target_temp_low",
                        payload="30",
                    )
                ]
            )

        self.assertEqual([], runtime.store.threshold_calls)


if __name__ == "__main__":
    unittest.main()
