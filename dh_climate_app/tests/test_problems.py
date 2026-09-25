from __future__ import annotations

import unittest
from datetime import datetime, timezone

from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.discovery import problem_state_payload
from dh_climate_app.executor import ExecutionProblem
from dh_climate_app.humidity import HumidityState
from dh_climate_app.outdoor import OutdoorState
from dh_climate_app.problems import collect_problems
from dh_climate_app.rooms import RoomState


class ProblemTests(unittest.TestCase):
    def test_aggregate_problem_contract(self) -> None:
        now = datetime.now(timezone.utc)
        outdoor = OutdoorState(
            observed_at=now,
            current_temperature=None,
            current_humidity=None,
            avg_24h_temperature=10.0,
            avg_24h_humidity=None,
            temperature_source=None,
            humidity_source=None,
            heat_threshold=12.0,
            cool_threshold=20.0,
            hysteresis=0.5,
            season=Season.OFF,
        )
        rooms = {
            "living": RoomState(
                room_id="living",
                name="Living",
                current_temperature=None,
                current_humidity=40.0,
                season=Season.OFF,
                effective_profile=Profile.DAY,
                target_temperature=None,
                climate_control_enabled=True,
                control_action=HvacAction.OFF,
                hvac_mode="off",
                hvac_action=HvacAction.OFF,
                window_state="unknown",
            )
        }
        humidity = {
            "living": HumidityState(
                room_id="living",
                controller_type="dehumidifier",
                current_humidity=40.0,
                target_humidity=50.0,
                control_enabled=True,
                active=False,
            )
        }
        problems = collect_problems(
            outdoor=outdoor,
            rooms=rooms,
            humidity=humidity,
            execution=(
                ExecutionProblem(
                    entity_id="switch.heater",
                    reason="unavailable",
                    details="entity unavailable",
                ),
            ),
        )
        codes = {item.code for item in problems}
        self.assertIn("outdoor_temperature_unavailable", codes)
        self.assertIn("room_temperature_unavailable", codes)
        self.assertIn("device_unavailable", codes)
        self.assertIn("room_window_state_unknown", codes)

        state, attrs = problem_state_payload(problems)
        self.assertEqual("ON", state)
        self.assertIn('"count":4', attrs)

    def test_no_problems_is_off(self) -> None:
        state, attrs = problem_state_payload(())
        self.assertEqual("OFF", state)
        self.assertIn('"count":0', attrs)


if __name__ == "__main__":
    unittest.main()
