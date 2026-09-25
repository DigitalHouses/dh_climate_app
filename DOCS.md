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

## Global settings

`global.hysteresis` is the one house-wide temperature hysteresis used by the season and room temperature controllers.

`global.humidity_hysteresis` is separate because relative humidity uses a different physical unit.

`night_mode` and `we_at_home` are optional Home Assistant facts. When a configured `we_at_home` entity is unavailable, the App uses the safer `away` profile.

## Outdoor sources

`outdoor.sources` is ordered by priority.

For each measurement independently, the App uses the first currently valid configured source. If it becomes unavailable, the next source is selected.

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
- `day / night / away / antifreeze` profile selector.

Multiple room temperature or humidity sensors are averaged from their latest available values.

Target identity is:

```text
room × season × profile
```

Selecting another profile through the thermostat is a short facade-only editing overlay, matching the previous DH Climate behavior. It resets after inactivity.

## FAST devices

FAST devices follow room demand.

Supported first-release domains:

- `switch`;
- `climate`.

A FAST `switch` must declare one explicit thermal function: `heat` or `cool`.

A FAST `climate` device may declare `heat`, `cool`, or `heat_cool`.

## SLOW devices

SLOW is intended for underfloor heating or another high-inertia comfort loop with its own local thermostat and probe.

For safety, v0.1 accepts SLOW devices only as Home Assistant `climate` entities.

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

Its physical actuator may be a `switch` or an existing Home Assistant `humidifier` entity.

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
