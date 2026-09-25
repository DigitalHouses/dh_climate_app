from __future__ import annotations

import unittest
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
