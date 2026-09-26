# Changelog

## 0.1.3 — development

- Treat Home Assistant's reserved MQTT climate preset `none` as a reset of the temporary room profile overlay, returning to the automatically selected `day / night / away` profile.

## 0.1.2 — development

- Replaced room thermostat `fan_modes` with native climate `preset_modes` (`day / night / away`) so Apple Home and other thermostat consumers keep native thermostat semantics; `antifreeze` remains internal protection.

- Added direct `weather.*` support for outdoor temperature and humidity sources using current weather attributes.

- Established the compact Python architecture derived from DH Climate 5 behavior without PostgreSQL orchestration, Matrix, Dispatcher, UC, Confirmator or SQL business logic.
- Added Home Assistant Supervisor REST/WebSocket input adapter with subscribe-before-snapshot reconnect handling and stale-event protection.
- Added MQTT reconnect recovery that restores subscriptions, retained Discovery/state and online availability after broker restarts.
- Fixed the MQTT startup/reconnect subscription-set race observed on real HAOS.
- Enabled the Supervisor API permission required by the startup timezone lookup.
- Added independent prioritized outdoor temperature and humidity source chains.
- Added persisted, time-weighted rolling 24-hour outdoor averages and global `HEAT / COOL / OFF` season calculation.
- Added MQTT Discovery two-threshold `heat_cool` season thermostat with persisted heating/cooling season thresholds.
- Added one MQTT Device and room `climate` facade per configured room.
- Added `day / night / away / antifreeze` target profiles and the legacy short-lived profile-edit overlay.
- Added one house-wide temperature hysteresis and persisted stateful room thermostat action.
- Added direct FAST heat/cool actuator policy for Home Assistant `switch` and `climate` entities.
- Added SLOW floor/comfort control through local `climate` thermostats with a separate SLOW target.
- Added optional per-room humidifier/dehumidifier facade and direct actuator control with separate humidity hysteresis.
- Added optional room window-contact aggregation and per-device open-window shutdown policy.
- Added legacy cold-weather heating protection for reversible FAST climate devices, defaulting to `-10 °C`.
- Added idempotent Home Assistant service reconciliation, capability/range checks, bounded retry and cooldown.
- Added aggregate `Problem` diagnostic plus `Version` and `Started at` diagnostics.
- Added fail-safe behavior for unavailable outdoor temperature, room sensors, Home Assistant disconnects and unavailable presence input.
- Added lightweight SQLite persistence for season thresholds, outdoor samples, room targets, humidity targets and hysteresis continuity.
- Added opt-in DigitalHouses Telemetry Protocol v1 client with persistent installation credentials, daily jittered heartbeat, one-hour failure backoff and authenticated deletion.
- Added flat Supervisor-compatible App configuration, English/Russian translations and user documentation.
- Added immutable multi-architecture GHCR delivery workflow and canonical release-tag validation.
- Added architecture-specific Home Assistant image labels so amd64 and aarch64 manifest variants report the canonical HA architecture names.
- Added automated unit, contract, shell, Python compile and container-build CI validation.
