# Legacy DH Climate 5 — behavior extraction

This document records the behavior that the new `dh_climate_app` is expected to preserve from `DigitalHouses/dh_climate_1`.

It is a migration contract, not a request to port PostgreSQL code.

## Source reviewed

Current legacy repository:

```text
DigitalHouses/dh_climate_1
```

Relevant implementation:

```text
src/dh_climate_pg/workers/ha_thermostat_facade_worker.py      v5.12
src/dh_climate_pg/workers/ha_outdoor_thermostat_facade_worker.py
src/dh_climate_pg/workers/ha_system_facade_worker.py
_db_dump.sql
```

## Outdoor behavior

Legacy outdoor logic:

- providers have explicit priority;
- lower numeric priority wins;
- selected outdoor temperature/humidity feed derived values;
- rolling/current derived values include avg24;
- season is global;
- season thresholds are writable through the outdoor thermostat;
- season states are `HEAT`, `COOL`, `OFF`.

Season equation in the PostgreSQL implementation:

```text
avg24 < heat_threshold - hysteresis → HEAT
avg24 > cool_threshold + hysteresis → COOL
otherwise                           → OFF
```

Outdoor thermostat facade:

```text
domain              climate
mode                heat_cool
current_temperature avg24 when available
current_humidity    avg24 when available
target_temp_low     heat threshold
target_temp_high    cool threshold
hvac_action         heating / cooling / idle
```

## Room behavior

Legacy room inputs:

- temperature;
- humidity;
- target;
- profile;
- climate control;
- global season;
- global home/night facts.

Room sensor canonicalization averaged latest readings from all enabled sensors of the same kind.

Effective profile precedence:

```text
HEAT + climate_control=false → antifreeze
not at home                  → away
night mode                   → night
otherwise                    → day
```

Target identity:

```text
room × season × profile
```

Room thermostat facade:

- one climate entity per room;
- current temperature;
- selected/effective target temperature;
- season-constrained modes;
- HVAC action;
- profile presented as thermostat `fan_mode`;
- profile choices: day/night/away/antifreeze.

Legacy v5.12 profile selection is a facade edit overlay: choosing a profile lets the user edit that profile target and the overlay resets after an idle timeout.

## Important legacy inconsistency

The legacy PostgreSQL repository contains both:

1. a room facade view that behaves like a one-sided threshold/deadband calculation; and
2. project-level climate contracts describing a true stateful symmetric hysteresis.

The compact App deliberately adopts the stateful symmetric form because the product requirement is explicitly a global hysteresis and this avoids output chatter.

This is an intentional behavior cleanup, not a code-port accident.

## Deliberate changes in the new App

The following current product decisions override legacy implementation details:

- no PostgreSQL;
- no SQL business logic;
- no jobs/Matrix/Dispatcher/UC lifecycle;
- every room is a separate MQTT Device;
- the App directly executes configured `climate` / `switch` devices;
- actuator classes `FAST` and `SLOW` are part of the first architecture;
- SLOW floor target is separate from room air target;
- optional room humidity control is exposed as a native HA `humidifier` entity;
- room devices do not publish duplicate temperature/humidity sensors by default;
- the configured house-wide temperature hysteresis is one global value;
- outdoor avg24 is time-weighted in the new App.

## Compatibility principle

Migration is checked at the Home Assistant behavior boundary:

```text
same user intent
→ equivalent entity behavior
→ equivalent state transitions
→ equivalent target/profile/season meaning
```

The new Python implementation does not need to resemble the old Python/SQL implementation internally.
