# Changelog

## 0.1.17 — 2026-09-27

- Restored native room thermostat semantics: the room state is `heat` in HEAT season, `cool` in COOL season, and `off` in interseason.
- Restored native Climate presets for `day / night / away` instead of misusing fan-speed semantics; Home Assistant's reserved `none` command clears the temporary profile-edit overlay.
- Restored the short-lived profile-edit overlay so an inactive profile target can be selected and edited from the room thermostat without changing the automatic day/night/away control source.
- Kept `hvac_action` independent from HVAC mode, exposing the actual current action as `heating / cooling / idle / off`.
- Kept room MQTT Climate capabilities stable as `off / heat / cool` across season transitions so Home Assistant does not rebuild the Climate entity and reset native preset state to `none`.
- Hardened the HAOS acceptance harness to wait for numeric room-target and season baseline values after App update before creating the baseline backup.
- Passed bundled live HAOS acceptance on 2026-09-27, including native room heat/cool/off state, day/night/away presets, preset reset, target range protection, bounded no-confirmation retry/cooldown, SLOW, window context, cold-weather reversible protection, humidity safe shutdown, and App-only backup/restore.

## 0.1.16 — unpublished candidate

- Intermediate HAOS validation candidate for the native room Climate UI. Superseded by 0.1.17 before immutable publication.

## 0.1.15 — 2026-09-27

- Fixed humidifier shutdown safety: inactive `humidifier.*` actuators no longer carry a target-humidity command, so an out-of-range target cannot block `turn_off`.
- Added cross-module humidity safety coverage for active target application, independent humidity disable, and inactive-device shutdown.
- Added cold `/data` durability coverage for season thresholds, room targets/control state, humidity targets/control state, hysteresis continuity, and telemetry installation identity.
- Added bundled actuator/safety acceptance coverage for SLOW floor behavior, window inhibition, cold-weather reversible climate protection, target range blocking, and retry/cooldown recovery.
- Passed bundled live HAOS runtime acceptance on 2026-09-27, including target range blocking, bounded no-confirmation retry/cooldown recovery, SLOW, window context, cold-weather protection, humidity safe shutdown, and Climate-App-only Supervisor backup/restore.
## 0.1.14 — development

- Separated Home Assistant service-call success from device-state verification: successful calls now log `SENT`, never `CONFIRMED`.
- Added event-driven delayed HA-state verification: post-command `state_changed` starts a settle window and only the later matching state becomes `VERIFIED_HA`.
- Added delayed drift detection for a previously stable actuator state before corrective commands are sent.
- Kept a bounded no-event watchdog/retry path and gave the final retry attempt its full confirmation window before entering cooldown.
- Reset transient verification evidence across Home Assistant disconnects.

## 0.1.13 — development

- Serialized the best-effort `script.write2climatelog` mirror through one asynchronous queue so `climate.log` preserves decision order.
- The authoritative App log remains immediate and climate control remains non-blocking.
- Added a bounded mirror queue to prevent an unavailable local log script from creating unbounded memory growth.

## 0.1.12 — development

- Fixed season range updates from the Home Assistant `heat_cool` thermostat: paired lower/upper MQTT commands are now coalesced and validated atomically.
- The order of `target_temp_low` / `target_temp_high` messages no longer matters.
- Single-threshold edits remain supported and invalid final ranges are still rejected.

## 0.1.11 — development

- Added dual-channel Climate diagnostic logging: authoritative App log plus asynchronous best-effort mirroring to local `script.write2climatelog`.
- Added transition-based room control logging and FAST/SLOW execution traces for desired/actual state, service calls, bounded retries, cooldown and confirmation without per-tick already-correct spam.
- Climate-log mirror failures are isolated from climate control, retries and Problem state.
- Actuator Problems now preserve `room_id` where applicable, so existing `problem_started` / `problem_recovered` events have enough room context for future local notifications.

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
