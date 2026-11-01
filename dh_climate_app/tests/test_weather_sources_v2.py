"""New weather provider -> derived sensor -> priority contract.

These tests must not mutate a real HA, MQTT broker or running manifest.
"""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from dh_climate_app.config import ConfigError, configured_entity_ids, parse_options
from dh_climate_app.discovery import provider_discovery_payloads
from dh_climate_app.mqtt import ClimateMqttFacade
from dh_climate_app.outdoor import OutdoorEngine
from dh_climate_app.persistence import StateStore
from dh_climate_app.source_registry import (
    project_sensors, source_entity, weather_condition_entity,
)


def new_options():
    return {
        "outdoor": {
            # Historical Supervisor values are intentionally ignored when
            # an explicit v2 priorities object is present.
            "temperature_sources": ["weather.legacy"],
            "humidity_sources": ["weather.legacy"],
        },
        "providers": [
            {"id": "google", "entity_id": "weather.asyl_mura"},
            {"id": "forecast", "entity_id": "weather.forecast_home_assistant"},
        ],
        "physical_sensors": [
            {"id": "garden", "entity_id": "sensor.garden_temperature",
             "quantity": "temperature"},
            {"id": "garden_hum", "entity_id": "sensor.garden_humidity",
             "quantity": "humidity"},
        ],
        "priorities": {
            "temperature": ["garden", "google.temperature",
                            "forecast.temperature"],
            "humidity": ["forecast.humidity", "garden_hum", "google.humidity"],
        },
        "rooms": [],
    }


def fake_state(value, **attributes):
    return SimpleNamespace(state=str(value), attributes=attributes)


class WeatherSourceConfigurationTests(unittest.TestCase):
    def test_model_preserves_independent_priority_and_provider_identity(self):
        config = parse_options(new_options())
        self.assertEqual(config.outdoor.source_model, "sensors")
        self.assertEqual(config.outdoor.temperature_sources,
                         ("garden", "google.temperature", "forecast.temperature"))
        self.assertEqual(config.outdoor.humidity_sources,
                         ("forecast.humidity", "garden_hum", "google.humidity"))
        self.assertEqual(len(config.outdoor.providers), 2)
        self.assertEqual(weather_condition_entity(config.outdoor),
                         "weather.asyl_mura")
        ids = configured_entity_ids(config)
        self.assertIn("weather.asyl_mura", ids)
        self.assertIn("sensor.garden_temperature", ids)
        self.assertNotIn("weather.legacy", ids)
        self.assertNotIn("google.temperature", ids)
        self.assertEqual(source_entity(config.outdoor, "google.temperature"),
                         "weather.asyl_mura")

    def test_legacy_manifest_remains_usable(self):
        config = parse_options({"outdoor": {
            "temperature_sources": ["weather.forecast_home_assistant"],
            "humidity_sources": ["weather.forecast_home_assistant"],
        }})
        self.assertEqual(config.outdoor.source_model, "legacy")
        self.assertEqual(config.outdoor.providers, ())
        self.assertEqual(config.outdoor.temperature_sources,
                         ("weather.forecast_home_assistant",))
        self.assertEqual(weather_condition_entity(config.outdoor),
                         "weather.forecast_home_assistant")

    def test_missing_references_bad_quantities_and_duplicate_names_rejected(self):
        cases = [
            lambda d: d["priorities"]["temperature"].append("google.humidity"),
            lambda d: d["priorities"]["temperature"].append("missing.temperature"),
            lambda d: d["providers"].append(
                {"id": "google", "entity_id": "weather.other"}),
            lambda d: d["providers"].append(
                {"id": "other", "entity_id": "weather.asyl_mura"}),
            lambda d: d["physical_sensors"][0].update(quantity="pressure"),
            lambda d: d["physical_sensors"].append(
                {"id": "google", "entity_id": "sensor.temp_2",
                 "quantity": "temperature"}),
            lambda d: d["priorities"]["humidity"].append("forecast.humidity"),
            lambda d: d["providers"][0].update(entity_id="sensor.temperature"),
            lambda d: d["physical_sensors"][0].update(
                entity_id="sensor.dh_climate_app_provider_google_temperature"),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate.__code__.co_firstlineno):
                raw = new_options()
                mutate(raw)
                with self.assertRaises(ConfigError):
                    parse_options(raw)
        with self.assertRaises(ConfigError):
            parse_options({"providers": [{"id": "google",
                       "entity_id": "weather.asyl_mura"}]})

    def test_any_length_priority_chain_is_accepted(self):
        raw = new_options()
        for i in range(7):
            raw["providers"].append({"id": f"backup_{i}",
                                     "entity_id": f"weather.backup_{i}"})
            raw["priorities"]["temperature"].append(f"backup_{i}.temperature")
        config = parse_options(raw)
        self.assertEqual(len(config.outdoor.temperature_sources), 10)


class WeatherSourceReadingTests(unittest.TestCase):
    def setUp(self):
        self.config = parse_options(new_options()).outdoor

    def test_both_weather_measurements_independent_and_units_normalized(self):
        raw = {
            "weather.asyl_mura": fake_state(
                "partlycloudy", temperature=50, temperature_unit="°F",
                humidity=47),
            "weather.forecast_home_assistant": fake_state(
                "sunny", temperature=11, temperature_unit="°C",
                humidity=63),
            "sensor.garden_temperature": fake_state(
                "10.5", unit_of_measurement="°C"),
            "sensor.garden_humidity": fake_state("50", unit_of_measurement="%"),
        }
        readings = project_sensors(self.config, raw)
        self.assertEqual(readings["google.temperature"], 10)
        self.assertEqual(readings["google.humidity"], 47)
        self.assertEqual(readings["forecast.temperature"], 11)
        self.assertEqual(readings["forecast.humidity"], 63)
        self.assertEqual(readings["garden"], 10.5)
        self.assertEqual(readings["garden_hum"], 50)
        self.assertEqual(set(readings), {
            "google.temperature", "google.humidity",
            "forecast.temperature", "forecast.humidity",
            "garden", "garden_hum",
        })
        self.assertNotIn("sensor.dh_climate_app_provider_google_temperature",
                         raw, "No MQTT self-feedback into the source cache")

    def test_missing_humidity_never_becomes_zero_or_stale_value(self):
        states = {
            "weather.asyl_mura": fake_state(
                "partlycloudy", temperature=7, temperature_unit="°C"),
            "weather.forecast_home_assistant": fake_state(
                "unavailable", temperature=10,
                temperature_unit="°C", humidity=90),
            "sensor.garden_temperature": fake_state("unavailable",
                                                   unit_of_measurement="°C"),
            "sensor.garden_humidity": fake_state("unavailable"),
        }
        readings = project_sensors(self.config, states)
        self.assertEqual(readings["google.temperature"], 7)
        self.assertIsNone(readings["google.humidity"])
        self.assertIsNone(readings["forecast.temperature"])
        self.assertIsNone(readings["forecast.humidity"])
        self.assertIsNone(readings["garden"])
        self.assertIsNone(readings["garden_hum"])

    def test_nonfinite_units_and_bad_humidity_are_unknown(self):
        raw = {
            "weather.asyl_mura": fake_state(
                "sunny", temperature=float("inf"), temperature_unit="°C",
                humidity=140),
            "weather.forecast_home_assistant": fake_state(
                "sunny", temperature=35, humidity="nan"),
        }
        readings = project_sensors(self.config, raw)
        for key in ("google.temperature","google.humidity",
                    "forecast.temperature","forecast.humidity"):
            self.assertIsNone(readings[key])

    def test_control_priority_works_without_reading_mqtt_derived_sensors(self):
        now = datetime(2026,11,1,12,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as dirname:
            store = StateStore(Path(dirname) / "climate.db")
            config = parse_options(new_options())
            store.initialize(config)
            engine = OutdoorEngine(config=config.outdoor,store=store,
                                   hysteresis=1.0)
            raw = {
                "sensor.garden_temperature": fake_state(
                    "unavailable", unit_of_measurement="°C"),
                "sensor.garden_humidity": fake_state("55",unit_of_measurement="%"),
                "weather.asyl_mura": fake_state(
                    "partlycloudy", temperature=12, temperature_unit="°C",
                    humidity=49),
                "weather.forecast_home_assistant": fake_state(
                    "rainy", temperature=10, temperature_unit="°C",
                    humidity=60),
            }
            readings = project_sensors(config.outdoor,raw)
            result=engine.evaluate({**raw,**readings}, observed_at=now)
            self.assertEqual(result.temperature_source, "google.temperature")
            self.assertEqual(result.raw_temperature, 12)
            self.assertEqual(result.humidity_source, "forecast.humidity")
            self.assertEqual(result.current_humidity, 60)
            # physical source returns, becomes highest priority by itself
            raw["sensor.garden_temperature"] = fake_state(
                "11",unit_of_measurement="°C")
            result=engine.evaluate({**raw,**project_sensors(config.outdoor,raw)},
                                   observed_at=now+timedelta(minutes=1))
            self.assertEqual(result.temperature_source,"garden")
            self.assertEqual(result.raw_temperature,11)


class FakeBridge:
    def __init__(self):
        self.published=[]
    def set_message_handler(self, _):
        pass
    def publish(self, topic,payload,*,retain,force=False):
        self.published.append((topic,payload,retain,force))
        return True


class WeatherSourceMqttTests(unittest.TestCase):
    def setUp(self):
        self.config = parse_options(new_options()).outdoor
        self.bridge=FakeBridge()
        self.facade=ClimateMqttFacade(
            bridge=self.bridge,app_version="test",started_at=datetime.now(timezone.utc),
            rooms=(),command_queue=asyncio.Queue(),providers=self.config.providers,
        )
    def test_two_distinct_discovery_sensors_per_provider(self):
        payloads=provider_discovery_payloads("test",self.config.providers)
        self.assertEqual(len(payloads),4)
        self.assertEqual(len(set(topic for topic,_ in payloads.values())),4)
        for key,(topic,value) in payloads.items():
            self.assertEqual(value["device_class"],key.rsplit(".",1)[1])
            self.assertEqual(value["state_class"],"measurement")
            self.assertEqual(value["default_entity_id"].split(".",1)[0],"sensor")
            self.assertEqual(
                value["default_entity_id"],
                "sensor.dh_climate_app_weather_" + key.replace(".", "_"),
            )
            # Stable identity: changing suggested HA ID must not orphan
            # sensors already created under the 0.2.12 default ID.
            self.assertEqual(
                value["unique_id"],
                "dh_climate_app_provider_" + key.replace(".", "_"),
            )
        self.facade.publish_provider_discovery()
        self.assertEqual(
            len([x for x in self.bridge.published if x[0].startswith("homeassistant/sensor/")]),4)
    def test_renaming_updates_mqtt_discovery_but_never_sensor_ids(self):
        before=provider_discovery_payloads("test",self.config.providers)
        self.facade.configure_provider_labels({
            "provider:google":{"ru":"Google Weather"},
            "weather_sensor:google.temperature":{"ru":"Температура Google"},
            "weather_sensor:google.humidity":{"ru":"Влажность Google"},
        })
        after=provider_discovery_payloads("test",self.config.providers,
                                          self.facade._provider_labels)
        key="google.temperature"
        self.assertEqual(after[key][1]["name"],"Температура Google")
        self.assertEqual(after[key][1]["device"]["name"],
                         "DH Climate · Google Weather")
        self.assertEqual(before[key][1]["unique_id"],after[key][1]["unique_id"])
        self.assertEqual(before[key][1]["state_topic"],after[key][1]["state_topic"])
        self.facade.publish_provider_discovery()
        self.assertFalse(any(topic.endswith("/availability")
                             for topic,_,_,_ in self.bridge.published))

    def test_removed_provider_cleans_retained_topics_and_registry(self):
        from json import dumps, loads
        with tempfile.TemporaryDirectory() as dirname:
            path=Path(dirname)/"provider_ids.json"
            path.write_text(dumps({"schema_version":1,
                "providers":["obsolete","google"]}),encoding="utf-8")
            self.facade.provider_registry_path=path
            self.facade.publish_provider_discovery(reset_availability=True)
            self.assertIn(
                ("homeassistant/sensor/dh_climate_app_provider_obsolete_temperature/config",
                 "",True,True),self.bridge.published)
            self.assertIn(
                ("DigitalHouses/Global/dh_climate_app/weather/providers/obsolete/temperature/state",
                 "",True,True),self.bridge.published)
            self.assertEqual(loads(path.read_text())["providers"],
                             ["forecast","google"])
            self.assertNotIn("obsolete",loads(path.read_text())["providers"])

    def test_measurement_cadence_and_independent_availability(self):
        now=datetime(2026,11,1,12,tzinfo=timezone.utc)
        self.facade.publish_provider_discovery()
        self.bridge.published.clear()
        values={"google.temperature":12.12, "google.humidity":40,
                "forecast.temperature":10.0, "forecast.humidity":None}
        self.facade.publish_provider_samples(values,observed_at=now)
        self.assertIn(
            ("DigitalHouses/Global/dh_climate_app/weather/providers/google/temperature/state",
             "12.12",True,False),self.bridge.published)
        self.assertNotIn("forecast.humidity",self.facade._provider_online)
        self.bridge.published.clear()
        self.facade.publish_provider_samples({**values,"google.temperature":14},
                                            observed_at=now+timedelta(seconds=30))
        self.assertEqual(self.bridge.published,[])
        self.facade.publish_provider_samples({**values,"google.temperature":14},
                                            observed_at=now+timedelta(minutes=1))
        self.assertIn(
            ("DigitalHouses/Global/dh_climate_app/weather/providers/google/temperature/state",
             "14",True,False),self.bridge.published)
        self.bridge.published.clear()
        self.facade.publish_provider_samples({**values,"google.humidity":None},
                                            observed_at=now+timedelta(minutes=1,seconds=1))
        self.assertIn(
            ("DigitalHouses/Global/dh_climate_app/weather/providers/google/humidity/availability",
             "offline",True,False),self.bridge.published)
        self.assertIn("google.temperature",self.facade._provider_online)
        self.facade.set_provider_samples_unavailable()
        self.assertFalse(self.facade._provider_online)


if __name__=="__main__":
    unittest.main()
