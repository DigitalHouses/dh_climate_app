# DigitalHouses Climate App 0.1.18 — HAOS acceptance

Date: 2026-09-27

## Scope

Version `0.1.18` was validated on a real Home Assistant OS installation using
the bundled acceptance harness and deterministic MQTT fixtures.

This release specifically corrects the room thermostat capability list so the
user sees only modes valid for the current global season.

## Native room Climate result

The live run passed the exact seasonal capability contract:

- HEAT season: `hvac_modes = [off, heat]`;
- COOL season: `hvac_modes = [off, cool]`;
- interseason/OFF: `hvac_modes = [off]`;
- room state follows the same season contract: `heat / cool / off`;
- `hvac_action` remains independent and exposes actual activity;
- native `day / night / away` presets survived the HEAT → COOL → OFF
  Discovery updates;
- selecting `night` exposed the Night target;
- selecting Home Assistant's reserved `none` returned to the automatically
  effective profile.

Preset preservation is implemented without timing delays. The App publishes the
authoritative retained preset to a season-scoped preset state topic before the
season-specific MQTT Discovery payload, forcing Home Assistant to resubscribe
and immediately consume the retained preset.

## Safety and actuator result

The same run passed:

- `device_target_out_of_range` start and recovery;
- bounded `device_no_confirmation` retry through RETRY 2/3, RETRY 3/3 and
  COOLDOWN 300s, followed by recovery;
- SLOW heat floor behavior and shutdown outside HEAT season;
- selective window inhibition through `window_off_devices`;
- reversible climate cold-weather heating protection without blocking COOL;
- humidity active control and safe shutdown when the stored target is outside
  the physical humidifier range.

## Durability result

A Climate-App-only Supervisor backup was created before the acceptance
configuration was applied and restored successfully afterwards.

The final runtime returned to the clean baseline with:

- App version `0.1.18`;
- room state `heat`;
- room control action `idle`;
- aggregate Problem `off`;
- Problem count `0`.

## Runtime acceptance result

```text
repository CI = green
container build = green
real HAOS update/start = green
HEAT modes off/heat only = green
COOL modes off/cool only = green
OFF modes off only = green
day/night/away preset preservation = green
preset reset to automatic profile = green
target_out_of_range safety = green
no_confirmation/retry/cooldown = green
SLOW thermostat path = green
window context = green
cold-weather reversible climate protection = green
humidity safe shutdown = green
Climate-App-only backup/restore = green
final clean baseline = green
runtime acceptance = PASS
```

## Release status

Runtime acceptance and immutable publication are complete.

Published release:

- tag: `digitalhouses_climate_app-v0.1.18`;
- release commit: `744c0cb479305f508ffd4b709d5e96c8623e5357`;
- image: `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.18`;
- manifest digest: `sha256:386b4890f893ba5c87f755a9b2f56267bba700618b870bb0dc8b875860be5e95`;
- release workflow run: `36276954342`.

No published immutable image version may be overwritten with different content.
