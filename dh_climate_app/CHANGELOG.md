# Changelog

## 0.1.10 — development

- Standardized every public App temperature value to one decimal place.
- Internal climate calculations retain full precision; rounding is applied only at Home Assistant, MQTT and machine-event presentation boundaries.
- Rounded current/avg24 outdoor temperature, season thresholds and temperature fields in semantic events.

## 0.1.9 — development

- Added dedicated UI sensors for current outdoor temperature and humidity.
- Outdoor UI sensors use the same prioritized/fallback sources as Climate Core and never replace current values with avg24 values.
- Added source and avg24 context as sensor attributes.

## 0.1.8 — development

- Changed interseason room climate behavior from unavailable to readable-Off: current room temperature remains visible, no seasonal target is exposed, and room thermostat commands are ignored while season is OFF.
- Added normalized precipitation state from configured `weather.*` sources: current precipitation type plus current-hour forecast precipitation amount in millimetres.
- Added one schema-v2 MQTT Event entity for semantic Climate transitions, initially covering season, precipitation, windows and aggregate Problem start/recovery; events use QoS 1, retain=false and are not replayed after reconnect.
- Added explicit rain/snow/mixed/hail classification and rain↔snow transition events without generating routine thermostat-cycle event noise.

## 0.1.7 — development

- Fixed migration of profile target Number availability after the 0.1.6 interseason change. Existing MQTT Discovery entities now explicitly replace the old room-dependent availability list with system-only availability, so target settings remain editable while room thermostats are unavailable between seasons.

## 0.1.6 — development

- Room thermostats are now deliberately unavailable while global season is `OFF`, preventing users from changing an inactive thermostat during interseason.
- Profile target configuration Number entities remain available independently so seasonal targets can still be prepared in advance.

## 0.1.5 — development

- Reworked room climate facade for Apple Home/HomeKit: stable `off / auto` HVAC modes, no fan or preset semantics, and the thermostat target always edits the currently active `day / night / away` profile.
- Separated the user-facing scheduled target from the internal HEAT antifreeze control target, so turning a room Off does not expose the antifreeze setpoint as the normal thermostat target.
- Replaced the temporary Profile select with hidden-by-default configuration Number entities for Heat/Cool Day/Night/Away targets and Heat antifreeze target; the old retained select Discovery entry is removed automatically on upgrade.

## 0.1.4 — development

- Removed room profiles from MQTT Climate presets entirely. Each room now exposes a separate `select` Profile entity with exactly `day / night / away`, so the thermostat remains a plain native climate entity and Home Assistant no longer injects the reserved `none` preset into its UI.

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
