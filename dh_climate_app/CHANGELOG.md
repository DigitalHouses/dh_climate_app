# Changelog

## 0.1.26 — development

- Added one outdoor-temperature processing path for both normal source noise and provider/sensor failover steps: selected RAW temperature → one-minute EMA → public filtered temperature → rolling avg24 → season.
- Added configurable `outdoor_temperature_ema_minutes` with a 20-minute default and a hard one-minute minimum filter/sample cadence.
- Added diagnostic `sensor.dh_climate_app_outdoor_temperature_raw` for debugging; RAW, filtered and avg24 temperature sensors use state-only MQTT contracts without custom dynamic attributes.
- Changed avg24 to the arithmetic mean of persisted one-minute filtered samples, removing dependence on irregular weather-provider update frequency. Existing pre-EMA temperature history is converted once through the EMA on upgrade.
- Preserved hard low-temperature AC heating protection on the selected RAW temperature so smoothing cannot delay `ac_min_outdoor_temperature` safety behavior.
- Removed Recorder history as a climate-calculation dependency; Recorder remains the observation/history surface for the public RAW, filtered and avg24 sensors.
- Aligned the change with the normative DigitalHouses application-development standards maintained in `DigitalHouses/home-assistant-apps`.

## 0.1.25 — development

- Align Recorder bootstrap filtering with native Home Assistant Statistics: request only significant/state changes from History instead of forcing `significant_changes_only=0`.
- This excludes Recorder rows where the outdoor-temperature state is unchanged and only attributes changed, preventing duplicate equal-valued samples from biasing the 24-hour arithmetic mean.
- Keep the 0.1.24 startup deduplication, empty-history bootstrap, runtime sampling and humidity behavior unchanged.
- Retain `sensor.avg_outdoor_temperature_24_temp` as the live acceptance oracle; the App avg24 must match it to one decimal after restart.

## 0.1.24 — development

- Fix the remaining Home Assistant Statistics parity gap on App startup: when Recorder history already contains the current canonical outdoor-temperature value, the startup snapshot no longer inserts that same value a second time into the 24-hour mean.
- Seed the runtime transition baseline from the newest restored Recorder sample, so a genuinely different live temperature is still appended immediately while an identical startup value is deduplicated.
- Keep the empty-history contract unchanged: the first live outdoor temperature becomes the initial `avg24` sample.
- Add regression coverage for both startup deduplication and a real live transition immediately after Recorder bootstrap.

## 0.1.23 — development

- Make outdoor temperature `avg24` follow Home Assistant Statistics `state_characteristic: mean` / `max_age: 24h` startup semantics instead of relying only on the App's private SQLite sample history.
- On each Home Assistant snapshot/reconnect, rebuild the temperature sample window from Recorder history of `sensor.dh_climate_app_outdoor_temperature`, excluding any pre-window baseline exactly like Statistics.
- If Recorder has no usable history, bootstrap the mean from the current live outdoor temperature; no historical value is fabricated.
- During runtime, sample the same one-decimal public outdoor temperature transitions that Home Assistant sees, so raw source precision or source-only switches cannot skew the mean away from the Statistics oracle.
- Keep outdoor humidity on its existing time-weighted path; season thresholds and hysteresis semantics are unchanged.
- Extend unit/live acceptance so the temporary `sensor.avg_outdoor_temperature_24_temp` can be used as an optional 0.1 °C oracle on HAOS.

## 0.1.22 — development

- Changed outdoor temperature `avg24` to match Home Assistant Statistics `state_characteristic: mean`: a simple arithmetic mean of persisted temperature samples inside the rolling 24-hour window.
- Removed the pre-window baseline sample from the temperature mean so values older than 24 hours cannot influence season selection.
- Kept outdoor humidity on the existing time-weighted rolling average; season thresholds, hysteresis and `decide_season()` semantics are unchanged.
- Added regression coverage for irregular sample spacing, 24-hour window exclusion, SQLite restart durability and season transition from the new mean.

## 0.1.21 — 2026-09-27

- Reduced Home Assistant Recorder churn from Climate App MQTT facades by removing per-recalculation `observed_at` timestamps from entity attributes.
- Split outdoor temperature and humidity attribute topics so one source/value change no longer updates unrelated outdoor entities; the avg24 sensor no longer carries dynamic JSON attributes.
- Split precipitation type and precipitation amount attribute topics so weather-condition changes and hourly amount metadata no longer rewrite both entities together.
- Rounded public season humidity attributes to one decimal, matching the existing public temperature precision and preventing insignificant floating-point drift from becoming Recorder rows.
- Added regression coverage proving that a 10-second observation-clock advance with unchanged public climate/weather data produces zero second MQTT publication.
- Passed bundled live HAOS acceptance on 2026-09-27, including the Recorder churn guard: stable outdoor temperature/humidity facades retained identical `last_updated` values across a runtime tick while the full source-failover, room-climate, safety, backup/restore and clean-baseline suite remained green.

## 0.1.20 — 2026-09-27

- Added outdoor-temperature source observability: every public one-decimal temperature change is logged with the currently active source.
- Added explicit source-switch logging and the machine Event `outdoor_temperature_source_changed` with previous/current source and temperature values.
- Confirmed and documented the existing ordered fallback contract: `outdoor_temperature_sources` accepts mixed comma-separated `sensor.*` and `weather.*` entities; the first currently valid source wins and the preferred source is restored automatically when it recovers.
- Extended HAOS acceptance with deterministic primary/backup outdoor sources, failover, preferred-source recovery, log assertions, and source-change Event assertions.
- Passed bundled live HAOS acceptance on 2026-09-27, including primary→backup failover, preferred-source recovery, temperature-change logging, source-switch logging/Event payloads, the existing room-climate/safety suite, App-only backup/restore, and final clean baseline.

## 0.1.19 — 2026-09-27

- Added a dedicated `sensor.dh_climate_app_outdoor_temperature_avg24` entity for the App's existing time-weighted 24-hour outdoor temperature average.
- The sensor reuses the same persisted Climate Core rolling average, publishes one-decimal °C values, and does not introduce a second calculation path.
- Passed bundled live HAOS acceptance on 2026-09-27; the new avg24 sensor matched the season facade `avg_24h_temperature` value and the full existing safety/backup suite remained green.

## 0.1.18 — 2026-09-27

- Restored season-specific room Climate capabilities: HEAT exposes only `off / heat`, COOL exposes only `off / cool`, and interseason exposes only `off`.
- Preserved native `day / night / away` presets across those MQTT Discovery updates by using season-scoped retained preset-state topics and publishing the authoritative preset before the Discovery payload.
- Removed the user-visible opposite-season HVAC mode from the room thermostat while retaining runtime rejection of invalid opposite-season commands.
- Passed bundled live HAOS acceptance on 2026-09-27, including exact seasonal `hvac_modes`, native preset preservation across HEAT → COOL → OFF, target-range safety, bounded no-confirmation retry/cooldown, SLOW, window context, cold-weather reversible protection, humidity safe shutdown, App-only backup/restore, and final clean baseline.

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
