from __future__ import annotations

import unittest

from dh_climate_app.app import ClimateRuntime
from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.rooms import RoomState


class FakeStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Season, Profile, float]] = []

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


if __name__ == "__main__":
    unittest.main()
