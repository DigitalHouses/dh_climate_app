# DigitalHouses Climate App

## What the App does

The App owns house climate decisions and exposes native Home Assistant climate entities through MQTT Discovery.

The control chain is:

```text
HA sensor states
→ outdoor / room facts
→ season + room thermostat decisions
→ FAST / SLOW device policy
→ direct HA service reconciliation
→ physical climate / switch / humidifier entities
```

The App does not use PostgreSQL. SQLite under `/data/dh_climate.db` is only durable state.

## Configuration shape

The Home Assistant App schema is intentionally flat. Home Assistant limits nested option schemas, so lists of Home Assistant entities are entered as comma-separated strings. Room entries contain only primitive fields; the App compiles them into the typed internal model.

See [docs/CONFIG_EXAMPLE.yaml](docs/CONFIG_EXAMPLE.yaml) for a complete example.

## Global settings


`hysteresis` is the one house-wide temperature hysteresis used by the season and room temperature controllers.

`humidity_hysteresis` is separate because relative humidity uses a different physical unit.

`night_mode` and `we_at_home` are optional Home Assistant facts. When a configured `we_at_home` entity is unavailable, the App uses the safer `away` profile.

## Outdoor sources

`outdoor_temperature_sources` and `outdoor_humidity_sources` are comma-separated ordered entity lists. Temperature and humidity have independent priority chains.

For each measurement, the App uses the first currently valid configured entity. If it becomes unavailable, the next entity is selected.

A normal `sensor.*` source is read from its numeric state. A `weather.*` source is supported directly: the App reads its current `temperature` attribute for outdoor temperature and its current `humidity` attribute for outdoor humidity. This allows entities such as `weather.forecast_home_assistant` to be used as primary or fallback sources without template sensors.

The App maintains a time-weighted rolling 24-hour outdoor average. Global season is:

```text
avg24 < heat_threshold - hysteresis → HEAT
avg24 > cool_threshold + hysteresis → COOL
otherwise                           → OFF
```

If no live outdoor temperature source is available, season is forced to `OFF`.

The season thermostat in Home Assistant is a `heat_cool` climate entity with two targets:

- lower/red target = heating-season threshold;
- upper/blue target = cooling-season threshold.

Changing either target persists it in SQLite.

## Rooms

Each configured room becomes its own MQTT Device. Assign that device to the matching Home Assistant Area.

The room thermostat exposes:

- current room temperature;
- current room humidity when configured;
- room target;
- current season-constrained HVAC mode;
- HVAC action;
- native climate presets `day / night / away`.

The room thermostat deliberately does not publish profile selection as
`fan_mode`. This keeps the entity semantically compatible with native
thermostat consumers such as HomeKit/Apple Home and avoids exposing climate
profiles as fan speeds.

`antifreeze` is an internal protection profile. In HEAT season, switching a
room thermostat off keeps the antifreeze target active internally; it is not
published as a user-selectable preset.

Multiple room temperature or humidity sensors are averaged from their latest available values.

Target identity is:

```text
room × season × profile
```

Selecting another profile through the thermostat is a short facade-only editing overlay, matching the previous DH Climate behavior. It resets after inactivity.

## Window context

Window contacts are optional per room through `window_sensors`.

Room window truth follows the previous DH Climate behavior:

```text
any open contact           → open
else any unavailable/other → unknown
otherwise                  → closed
```

Window state does **not** change room thermostat demand. It is device context. Put only the actuators that must stop with an open window in `window_off_devices`. Other thermal devices continue according to their normal policy.

An unknown configured window state is surfaced through the aggregate Problem diagnostic.

## FAST devices

FAST devices follow room demand.

Supported first-release domains:

- `switch`;
- `climate`.

`fast_heat` and `fast_cool` are comma-separated actuator lists. A `climate` entity may be present in both lists and is then treated as `heat_cool`. A `switch` must appear in only one list.

A reversible `climate` entity present in both FAST lists also inherits the legacy cold-weather heating protection. Below `ac_min_outdoor_temperature` (default `-10 °C`) the App keeps that device out of heating mode while other allowed heat sources can continue.

## Windows

Room window contacts are optional and configured in `window_sensors`.

Window state is **context**, not thermostat truth: opening a window does not rewrite the room target or HVAC action. Only devices explicitly listed in `window_off_devices` are forced off while any configured window is open. This preserves the legacy per-device window-policy behavior without recreating the old Firewall/Matrix layers.

If a configured window contact is unavailable and no other contact is open, the room reports an `unknown` window state through the aggregate problem diagnostic. The App does not invent a closed state.

## Cold-weather AC protection

A reversible FAST `climate` entity configured in both `fast_heat` and `fast_cool` is treated as the AC/heat-pump class for the legacy low-outdoor-temperature heating limit.

`ac_min_outdoor_temperature` is a global safety threshold. Below it, those reversible devices are inhibited from heating. Cooling behavior is unaffected. Heating-only switches and SLOW floor thermostats are not implicitly classified as AC devices.

## SLOW devices

SLOW is intended for underfloor heating or another high-inertia comfort loop with its own local thermostat and probe.

For safety, v0.1 accepts SLOW devices only as Home Assistant `climate` entities. They are listed in `slow_heat`, and all SLOW thermostats in one room use the room's separate `slow_target`.

During HEAT season:

```text
hvac_mode = heat
target    = configured SLOW target
```

During COOL or OFF:

```text
hvac_mode = off
```

The SLOW target is deliberately separate from the room air target.

## Humidity

Humidity control is optional per room and can be:

- `humidifier`;
- `dehumidifier`.

The App publishes a native Home Assistant `humidifier` entity containing current humidity and target humidity.

Its physical actuator may be a `switch` or an existing Home Assistant `humidifier` entity. Set `humidity_mode` to `off`, `humidifier`, or `dehumidifier`.

## Safety and reconciliation

The App compares desired and actual physical state before every service call.

It does not send a command when state already matches. Repeated mismatches are rate-limited, bounded and surfaced through the aggregate diagnostic problem entity.

Before sending climate commands, the App checks reported supported HVAC modes and target limits where Home Assistant exposes them.

On Home Assistant disconnect, cached facts are invalidated and App control is suspended until a fresh snapshot is obtained.

## Persistence

Persistent state includes:

- season thresholds;
- rolling outdoor samples;
- room profile targets;
- room climate-control enable state;
- previous thermostat action for hysteresis continuity;
- humidity targets and control state.

The database does not contain jobs, dispatcher queues or SQL business logic.

## Diagnostics

The system MQTT Device exposes:

- Version;
- Started at;
- Problem.

`Problem` is an aggregate diagnostic binary sensor with machine-readable problem details in attributes.


## Usage telemetry

Telemetry is optional and disabled by default with:

```yaml
telemetry_enabled: false
```

When enabled, the App sends the shared DigitalHouses Telemetry Protocol v1 heartbeat. The client payload contains only:

- protocol schema version;
- telemetry policy version;
- a random persistent installation UUID;
- product identifier `digitalhouses_climate_app`;
- released App version.

Country is derived server-side from network metadata. The App does not send room names, Home Assistant entity IDs, device inventory, climate values, targets, local/WAN addresses, Home Assistant identity or MQTT credentials.

A successful heartbeat is normally sent about once per 24 hours with deterministic jitter. Enabling telemetry or installing a newer released version is eligible for an immediate best-effort heartbeat. Failure uses a persisted one-hour backoff and never changes climate control or product health.

Disabling telemetry stops future heartbeats but does not delete retained server-side data. Use `button.dh_climate_app_delete_telemetry` for authenticated deletion of this installation's retained telemetry.

Development versions ending in `-local` never send production telemetry.
