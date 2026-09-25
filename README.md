# DH Climate App

DigitalHouses climate control application for Home Assistant.

The project replaces the legacy PostgreSQL-heavy DH Climate runtime with a compact Python climate core while preserving the important DH Climate 5 user/business behavior.

## Architecture work

Current design branch: `architecture-v1`.

- [Architecture](docs/ARCHITECTURE.md)
- [Behavior contract](docs/BEHAVIOR_CONTRACT.md)
- [Configuration contract](docs/CONFIGURATION.md)
- [MQTT / Home Assistant contract](docs/MQTT_CONTRACT.md)
- [Legacy DH Climate 5 audit](docs/LEGACY_DH_CLIMATE_5_AUDIT.md)
- [Design decisions](docs/DESIGN_DECISIONS.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)

## Core direction

```text
Home Assistant facts
-> Python Climate Core
-> Device Plan
-> Home Assistant services

Python Core
-> SQLite continuity state
-> MQTT Discovery facade
```

No PostgreSQL orchestration, Matrix, Dispatcher, UC queue, Confirmator, or Supervisor is carried into the new App.
