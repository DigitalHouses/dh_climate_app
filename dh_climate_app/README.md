# DigitalHouses Climate App

`dh_climate_app` is the compact Home Assistant App for whole-house climate control.

It preserves the useful **behavior contract** of the previous PostgreSQL DH Climate 5 system while replacing PostgreSQL orchestration, SQL jobs, Matrix/Dispatcher/UC and related runtime machinery with a small Python control core.

## Architecture

```text
Home Assistant states
        ↓
Python Climate Core
 ├─ outdoor priority + rolling avg24
 ├─ global HEAT / COOL / OFF season
 ├─ room thermostat + profiles
 ├─ humidity control
 └─ FAST / SLOW + safety policy
        ↓
desired physical state
        ↓
Home Assistant services
        ↓
climate / switch / humidifier

Python Climate Core
        ↓
MQTT Discovery
        ↓
Home Assistant facades
```

SQLite under `/data/dh_climate.db` stores only durable installation state. It is not a business-rule or orchestration engine.

## Implemented behavior

- prioritized outdoor temperature and humidity fallback chains;
- weather-condition precipitation typing plus current-hour forecast amount in mm;
- one schema-v2 MQTT Event stream for weather, season, window and Problem transitions;
- time-weighted rolling 24-hour outdoor average;
- global `HEAT / COOL / OFF` season;
- writable two-threshold `heat_cool` season thermostat;
- one MQTT Device and one room thermostat per configured room;
- Apple Home-compatible room thermostat with stable `off / auto` modes, active-profile target control, and read-only interseason temperature display;
- hidden configuration numbers for Heat/Cool Day/Night/Away targets plus internal Heat antifreeze target;
- one house-wide temperature hysteresis;
- persisted stateful room hysteresis;
- FAST heat/cool actuators;
- SLOW local floor thermostats with a separate comfort target;
- optional humidifier/dehumidifier control;
- optional room window context with per-device open-window shutdown;
- legacy cold-weather protection for reversible heat/cool climate devices;
- direct idempotent Home Assistant service reconciliation;
- bounded retry and aggregate Problem diagnostic;
- safe Home Assistant reconnect/snapshot handling;
- Version and Started at diagnostics;
- optional DigitalHouses Telemetry Protocol v1 support;
- immutable multi-architecture GHCR delivery workflow.

## Configuration

Home Assistant App option schemas have limited nesting depth, so the external configuration is intentionally flat:

- global scalar options at the top level;
- comma-separated entity lists;
- one flat record per room.

See [docs/CONFIG_EXAMPLE.yaml](docs/CONFIG_EXAMPLE.yaml) and [DOCS.md](DOCS.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Legacy behavior contract](docs/LEGACY_BEHAVIOR.md)
- [Configuration example](docs/CONFIG_EXAMPLE.yaml)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [HAOS acceptance plan](HAOS_TEST_PLAN.md)
- [Experimental update runbook](docs/EXPERIMENTAL_UPDATE_RUNBOOK.md)

## Release status

Version `0.1.7` is still an **experimental pre-release implementation**. Unit/CI and container-build validation are automated. The remaining release gate is end-to-end testing on a real Home Assistant OS installation with real MQTT discovery and physical actuator entities.

Canonical release identity:

```text
digitalhouses_climate_app-v<version>
```

Production images:

```text
ghcr.io/digitalhouses/digitalhouses-climate-app:<version>
```
