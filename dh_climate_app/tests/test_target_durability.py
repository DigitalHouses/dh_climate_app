"""Non-destructive state, stale outdoor and physical valve timing regressions."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from dh_climate_app.core import HvacAction, Profile, Season
from dh_climate_app.devices import SlowValveIntervalGuard, compile_room_devices
from dh_climate_app.events import ClimateEventEngine
from dh_climate_app.health import reduce_climate_health
from dh_climate_app.outdoor import OutdoorEngine
from dh_climate_app.persistence import StateStore
from dh_climate_app.problems import Problem
from test_target_topology import device, options, state
from dh_climate_app.config import parse_options


NOW = datetime(2026, 10, 27, 2, 0, tzinfo=timezone.utc)


class TargetDurabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "climate.db"
        self.config = parse_options(options(device(
            "switch.floor", "slow_heat", "app",
            actuator="normal_closed", temperature_sensor="sensor.floor",
        )))
        self.store = StateStore(self.path)
        self.store.initialize(self.config)

    def test_sqlite_new_tables_preserve_existing_fast_and_season(self):
        self.store.set_room_target("bedroom", Season.HEAT, Profile.NIGHT, 21.5)
        self.store.set_season_thresholds(heat=9.0, cool=24.0)
        self.store.set_global_tuning("fast_heat_hysteresis", 0.8)
        self.store.seed_existing_slow_target("bedroom", 27.0)
        self.store.set_slow_target("bedroom", Profile.NIGHT, 26.0)
        self.store.initialize(self.config)
        self.store.seed_existing_slow_target("bedroom", 30.0)
        self.assertEqual(21.5, self.store.get_room_target(
            "bedroom", Season.HEAT, Profile.NIGHT
        ))
        thresholds = self.store.get_season_thresholds()
        self.assertEqual((9.0, 24.0), (thresholds.heat, thresholds.cool))
        self.assertEqual(0.8, self.store.get_global_tuning("fast_heat_hysteresis"))
        self.assertEqual(27.0, self.store.get_slow_target("bedroom", Profile.DAY))
        self.assertEqual(26.0, self.store.get_slow_target("bedroom", Profile.NIGHT))
        self.assertEqual(27.0, self.store.get_slow_target("bedroom", Profile.AWAY))
        self.assertEqual(5.0, self.store.get_global_tuning("slow_heat_min_on_time"))

    def test_no_slow_target_is_ever_invented_by_initialization(self):
        self.assertIsNone(self.store.get_slow_target("bedroom", Profile.DAY))
        self.assertIsNone(self.store.get_slow_target("bedroom", Profile.NIGHT))

    def test_min_on_time_survives_restart_and_safety_bypasses(self):
        self.store.set_slow_target("bedroom", Profile.DAY, 27.0)
        ready = state(action=HvacAction.IDLE)
        requested = compile_room_devices(
            config=self.config, room_states={"bedroom": ready},
            humidity_states={}, screed_values={"sensor.floor": 28.0},
            slow_targets={"bedroom": 27.0}, slow_hysteresis=0.5,
        )
        self.assertFalse(requested[0].power)
        guard = SlowValveIntervalGuard(self.store)
        # First observation gives no measured time (not a false startup transition).
        observed_off = {"switch.floor": SimpleNamespace(state="off")}
        self.assertEqual(False, guard.filter(
            requested, config=self.config,
            room_states={"bedroom": ready},
            observed=observed_off, sensor_values={"sensor.floor": 28.0}, now=NOW,
        )[0].power)
        # HA confirms ON transition; it is the only persisted clock origin.
        observed_on = {"switch.floor": SimpleNamespace(state="on")}
        guard.filter(
            requested, config=self.config, room_states={"bedroom": ready},
            observed=observed_on, sensor_values={"sensor.floor": 28.0},
            now=NOW + timedelta(minutes=1),
        )
        fresh_guard = SlowValveIntervalGuard(self.store)
        held = fresh_guard.filter(
            requested, config=self.config, room_states={"bedroom": ready},
            observed=observed_on, sensor_values={"sensor.floor": 28.0},
            now=NOW + timedelta(minutes=2),
        )
        self.assertTrue(held[0].power)
        released = fresh_guard.filter(
            requested, config=self.config, room_states={"bedroom": ready},
            observed=observed_on, sensor_values={"sensor.floor": 28.0},
            now=NOW + timedelta(minutes=7),
        )
        self.assertFalse(released[0].power)
        stop = state(season=Season.COOL)
        self.assertFalse(fresh_guard.filter(
            requested, config=self.config, room_states={"bedroom": stop},
            observed=observed_on, sensor_values={"sensor.floor": 28.0},
            now=NOW + timedelta(minutes=2),
        )[0].power)

    def test_outdoor_outage_restart_has_no_fake_readings(self):
        engine = OutdoorEngine(
            config=self.config.outdoor, store=self.store, hysteresis=0.5,
        )
        first = engine.evaluate(
            {"sensor.outdoor_a": "5.0"}, observed_at=NOW,
        )
        self.assertEqual(Season.HEAT, first.season)
        with self.store.connect() as db:
            before = db.execute(
                "SELECT count(*) FROM outdoor_samples WHERE kind='temperature'"
            ).fetchone()[0]
        after = engine.evaluate(
            {}, observed_at=NOW + timedelta(minutes=2),
        )
        self.assertTrue(after.stale)
        self.assertEqual(Season.HEAT, after.season)
        self.assertIsNone(after.raw_temperature)
        with self.store.connect() as db:
            after_samples = db.execute(
                "SELECT count(*) FROM outdoor_samples WHERE kind='temperature'"
            ).fetchone()[0]
        self.assertEqual(before, after_samples)
        restarted = OutdoorEngine(
            config=self.config.outdoor, store=self.store, hysteresis=0.5,
        )
        cached = restarted.evaluate(
            {}, observed_at=NOW + timedelta(minutes=3),
        )
        self.assertTrue(cached.stale)
        self.assertEqual(Season.HEAT, cached.season)
        self.assertEqual(first.last_valid_at, cached.last_valid_at)
        recovered = restarted.evaluate(
            {"sensor.outdoor_a": "6"}, observed_at=NOW + timedelta(minutes=4),
        )
        self.assertFalse(recovered.stale)
        self.assertEqual("sensor.outdoor_a", recovered.temperature_source)

    def test_health_transitions_and_room_name(self):
        engine = OutdoorEngine(
            config=self.config.outdoor, store=self.store, hysteresis=0.5,
        )
        outdoor = engine.evaluate({"sensor.outdoor_a": "6"}, observed_at=NOW)
        room = state()
        rooms = {"bedroom": room}
        healthy = reduce_climate_health(outdoor=outdoor, rooms=rooms, problems=())
        self.assertEqual("healthy", healthy.climate_state)
        events = ClimateEventEngine()
        self.assertFalse(events.observe(
            outdoor=outdoor, weather=None, rooms=rooms,
            problems=(), observed_at=NOW, health=healthy,
        ))
        problem = Problem(code="probe_lost", scope="room", room_id="bedroom")
        degraded = reduce_climate_health(
            outdoor=outdoor, rooms=rooms, problems=(problem,),
        )
        delta = events.observe(
            outdoor=outdoor, weather=None, rooms=rooms,
            problems=(problem,), observed_at=NOW, health=degraded,
        )
        kinds = {e["event_type"] for e in delta}
        self.assertIn("room_health_changed", kinds)
        self.assertIn("climate_health_changed", kinds)
        self.assertIn("problem_started", kinds)
        for event in delta:
            self.assertNotIn("schema_version", event)
            if "room_id" in event:
                self.assertEqual("Спальня", event["room_name"])
        self.assertFalse(events.observe(
            outdoor=outdoor, weather=None, rooms=rooms,
            problems=(problem,), observed_at=NOW, health=degraded,
        ))


if __name__ == "__main__":
    unittest.main()
