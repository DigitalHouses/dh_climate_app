# DigitalHouses Climate App

`dh_climate_app` is the compact Home Assistant implementation of DigitalHouses climate control.

The project reuses the **behavior contract** of the previous PostgreSQL DH Climate system while removing PostgreSQL orchestration, SQL jobs, Matrix/Dispatcher/UC layers and other infrastructure that is unnecessary inside a Home Assistant App.

Current design:

```text
HA sensors → Python Climate Core → direct HA device execution
                         ↓
                 MQTT Discovery facade
```

Core features being implemented:

- prioritized outdoor temperature/humidity sources;
- time-weighted rolling 24h outdoor temperature;
- global HEAT / COOL / OFF season;
- two-threshold outdoor season thermostat;
- room thermostat per room;
- `day / night / away / antifreeze` target profiles;
- house-wide temperature hysteresis;
- FAST and SLOW actuator classes;
- separate floor/SLOW target temperature;
- optional per-room humidifier/dehumidifier facade;
- one MQTT Device per room so it can be assigned to a Home Assistant Area.

Documentation:

- [Architecture](docs/ARCHITECTURE.md)
- [Legacy behavior contract](docs/LEGACY_BEHAVIOR.md)
- [Proposed configuration](docs/CONFIG_EXAMPLE.yaml)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)

The first code slice is a dependency-free, testable Python climate core under `src/dh_climate_app/core.py`.
