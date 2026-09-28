from __future__ import annotations

import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from dh_climate_app.ha_client import HaState, HomeAssistantClient, StateCache


def state(entity_id: str, value: str, at: datetime) -> HaState:
    return HaState(
        entity_id=entity_id,
        state=value,
        attributes={},
        last_changed=at,
        last_updated=at,
    )


class HomeAssistantHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_query_matches_statistics_window_contract(self) -> None:
        client = HomeAssistantClient(
            token="token",
            entity_ids=[],
        )
        start = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
        end = start + timedelta(hours=24)

        payload = [
            [
                {
                    "entity_id": "sensor.dh_climate_app_outdoor_temperature",
                    "state": "17.4",
                    "last_changed": "2026-09-27T13:00:00+00:00",
                    "last_updated": "2026-09-27T13:00:00+00:00",
                },
                {
                    "entity_id": "sensor.dh_climate_app_outdoor_temperature",
                    "state": "16.8",
                    "last_changed": "2026-09-27T14:00:00+00:00",
                    "last_updated": "2026-09-27T14:00:00+00:00",
                },
            ]
        ]

        with patch.object(client, "_request_json", return_value=payload) as request_json:
            states = await client.get_history(
                "sensor.dh_climate_app_outdoor_temperature",
                start_time=start,
                end_time=end,
            )

        self.assertEqual(["17.4", "16.8"], [item.state for item in states])
        args = request_json.call_args.args
        self.assertEqual("GET", args[0])
        self.assertIn("/history/period/", args[1])
        self.assertIn("filter_entity_id=sensor.dh_climate_app_outdoor_temperature", args[1])
        self.assertNotIn("significant_changes_only=0", args[1])
        self.assertIn("skip_initial_state", args[1])
        self.assertIn("no_attributes", args[1])
        self.assertIsNone(args[2])


class StateCacheTests(unittest.TestCase):
    def test_snapshot_filters_to_allowlist(self) -> None:
        now = datetime.now(timezone.utc)
        cache = StateCache(["sensor.allowed"])
        cache.replace_snapshot(
            [
                state("sensor.allowed", "10", now),
                state("sensor.other", "20", now),
            ]
        )
        self.assertEqual({"sensor.allowed": "10"}, cache.values())

    def test_older_buffered_event_cannot_override_snapshot(self) -> None:
        now = datetime.now(timezone.utc)
        cache = StateCache(["sensor.outdoor"])
        cache.replace_snapshot([state("sensor.outdoor", "12", now)])
        changed = cache.apply(
            state("sensor.outdoor", "11", now - timedelta(seconds=1))
        )
        self.assertFalse(changed)
        self.assertEqual("12", cache.values()["sensor.outdoor"])

    def test_parse_state_changed(self) -> None:
        parsed = HomeAssistantClient.parse_state_changed(
            {
                "type": "event",
                "event": {
                    "event_type": "state_changed",
                    "data": {
                        "new_state": {
                            "entity_id": "sensor.outdoor",
                            "state": "10.5",
                            "attributes": {"unit_of_measurement": "°C"},
                            "last_changed": "2026-09-25T15:00:00+00:00",
                            "last_updated": "2026-09-25T15:00:00+00:00",
                        }
                    },
                },
            }
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual("sensor.outdoor", parsed.entity_id)
        self.assertEqual("10.5", parsed.state)


if __name__ == "__main__":
    unittest.main()
