# Changelog

## 0.1.0 — development

- Established architecture baseline for the compact Home Assistant App.
- Extracted legacy DH Climate 5 behavior contract.
- Added pure Python core for source priority, rolling avg24, season selection, profiles, thermostat hysteresis and FAST/SLOW policy.
- Added typed App configuration model and validation.
- Added lightweight SQLite persistence for season thresholds, rolling outdoor samples, room targets, humidity targets and thermostat hysteresis continuity.
- Added unit coverage for configuration and persistence.
