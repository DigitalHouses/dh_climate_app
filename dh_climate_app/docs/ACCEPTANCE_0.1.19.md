# DigitalHouses Climate App 0.1.19 — HAOS acceptance

Date: 2026-09-27

## Scope

Version `0.1.19` was validated on a real Home Assistant OS installation using
the bundled acceptance harness.

This release adds one dedicated UI entity for the already-existing Climate Core
24-hour outdoor temperature average:

- `sensor.dh_climate_app_outdoor_temperature_avg24`.

## Avg24 sensor result

The live run confirmed:

- the new entity was discovered after update to `0.1.19`;
- its state was numeric;
- its state matched the season facade `avg_24h_temperature` attribute;
- observed value in the acceptance run: `18.0 °C`;
- the value comes from the existing persisted time-weighted rolling average,
  not from a second Home Assistant-side calculation.

## Regression result

The same bundled run passed the complete existing Climate acceptance set:

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
outdoor temperature avg24 sensor = green
full existing regression suite = green
Climate-App-only backup/restore = green
final clean baseline = green
runtime acceptance = PASS
```

## Release status

Runtime acceptance and immutable publication are complete.

Published release:

- tag: `digitalhouses_climate_app-v0.1.19`;
- release commit: `76a91373adae33e4ceffd2d1ad6b7727d6c6841f`;
- image: `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.19`;
- manifest digest: `sha256:3d9a057b56d408fc998dbae7f15b636d9b3c1cde4caab448019585c23a988248`;
- release workflow run: `36278385669`.

No published immutable image version may be overwritten with different content.
