from __future__ import annotations

import unittest

from dh_climate_app.app import ClimateRuntime
from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.rooms import ProfileEditOverlay, RoomState


class RoomPresetCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_none_clears_temporary_profile_overlay(self) -> None:
        runtime = object.__new__(ClimateRuntime)
        runtime.profile_overlay = ProfileEditOverlay(idle_timeout_seconds=10.0)
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
                hvac_mode="heat",
                hvac_action=HvacAction.IDLE,
                window_state="not_configured",
            )
        }

        runtime.profile_overlay.select(
            "livingroom",
            Profile.NIGHT,
            effective_profile=Profile.DAY,
            now_monotonic=100.0,
        )
        self.assertEqual(
            Profile.NIGHT,
            runtime.profile_overlay.selected(
                "livingroom",
                effective_profile=Profile.DAY,
                now_monotonic=105.0,
            ),
        )

        await runtime._handle_room_command("livingroom", "profile", "none")

        self.assertEqual(
            Profile.DAY,
            runtime.profile_overlay.selected(
                "livingroom",
                effective_profile=Profile.DAY,
                now_monotonic=105.0,
            ),
        )


if __name__ == "__main__":
    unittest.main()
