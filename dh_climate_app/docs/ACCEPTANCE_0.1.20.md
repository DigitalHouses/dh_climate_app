# DigitalHouses Climate App 0.1.20 — HAOS acceptance

Date: 2026-09-27

## Scope

Version `0.1.20` was validated on a real Home Assistant OS installation using
the bundled acceptance harness.

This release adds observability for the existing prioritized outdoor
temperature source chain.

## Outdoor source result

The live run confirmed:

- the active source is visible through the season facade;
- a same-source temperature change is written to `climate.log` with the
  active source;
- primary source loss switches to the configured backup;
- the failover writes a dedicated source-switch log line;
- the failover emits `outdoor_temperature_source_changed`;
- the Event contains previous/current source and previous/current temperatures;
- recovery of the preferred primary source switches back automatically;
- the preferred-source recovery emits the reverse transition;
- the first complete observation after startup/reconnect remains a baseline,
  not a synthetic source-change Event.

Observed live sequence:

```text
primary 5.0 °C
primary 7.0 °C
primary unavailable
backup 6.0 °C
primary restored 5.0 °C
```

## Regression result

The same bundled run passed the complete existing acceptance set:

- dedicated outdoor temperature avg24 sensor;
- native room HEAT / COOL / OFF semantics;
- native day / night / away presets;
- target-range safety;
- bounded no-confirmation retry and cooldown recovery;
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
outdoor source temperature-change log = green
primary -> backup failover = green
source-switch log = green
outdoor_temperature_source_changed Event = green
backup -> preferred primary recovery = green
full existing regression suite = green
Climate-App-only backup/restore = green
final clean baseline = green
runtime acceptance = PASS
```

## Release status

Runtime acceptance and immutable publication are complete.

Published release:

- tag: `digitalhouses_climate_app-v0.1.20`;
- release commit: `50f6ed7cc72cc3b01f8f12b05325d1eb9469a14b`;
- image: `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.20`;
- manifest digest: `sha256:1405f6b91adddc1325047bcdebcee23af0da401b6df4ffd742450d23a0f1476c`;
- release workflow run: `36280643923`.

No published immutable image version may be overwritten with different content.
