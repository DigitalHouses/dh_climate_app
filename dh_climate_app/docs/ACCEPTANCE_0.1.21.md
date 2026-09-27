# DigitalHouses Climate App 0.1.21 — HAOS acceptance

Date: 2026-09-27

## Scope

Version `0.1.21` was validated on a real Home Assistant OS installation using
the bundled acceptance harness.

This release reduces Home Assistant Recorder churn from MQTT facade entities
without disabling useful history.

## Recorder churn result

The live run confirmed:

- `climate.dh_climate_app_season` no longer exposes a per-recalculation
  `observed_at` attribute;
- outdoor temperature and humidity facades expose stable source attributes;
- with unchanged values and sources, both outdoor facade entities retained
  exactly the same Home Assistant `last_updated` values across a runtime tick;
- the new acceptance gate reported:
  `PASS stable outdoor facades do not update every runtime tick`;
- source failover and source recovery still update the facades when they
  actually change;
- avg24, room climate and actuator behavior are unaffected.

The repository regression suite also proves that advancing only the internal
observation clock by ten seconds causes zero second MQTT publication for both
outdoor/season state and weather precipitation state.

## MQTT contract changes

The release removes synthetic state churn by:

- removing `observed_at` from season, outdoor and weather entity attributes;
- splitting outdoor temperature and humidity attribute topics;
- removing dynamic JSON attributes from the avg24 sensor;
- splitting precipitation type and amount attribute topics;
- rounding public season humidity attributes to one decimal;
- clearing the legacy shared retained attribute topics during startup.

## Regression result

The bundled live run also passed:

- dedicated outdoor temperature avg24 sensor;
- outdoor primary/backup failover and preferred-source recovery;
- outdoor temperature/source logging and source-change Event;
- native room HEAT / COOL / OFF semantics;
- native day / night / away presets;
- target-range safety;
- bounded no-confirmation retry/cooldown recovery;
- SLOW floor control;
- window context and selective inhibition;
- cold-weather reversible climate protection;
- humidity active path and safe shutdown;
- Climate-App-only Supervisor backup/restore;
- final clean baseline with aggregate Problem off.

## Runtime acceptance result

```text
repository CI = green
container build = green
real HAOS update/start = green
recorder churn guard = green
stable outdoor last_updated across runtime tick = green
outdoor source failover/recovery = green
full existing regression suite = green
Climate-App-only backup/restore = green
final clean baseline = green
runtime acceptance = PASS
```

## Release target

- tag: `digitalhouses_climate_app-v0.1.21`;
- image: `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.21`.

No published immutable image version may be overwritten with different content.
