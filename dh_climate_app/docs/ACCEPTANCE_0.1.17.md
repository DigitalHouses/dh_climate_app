# DigitalHouses Climate App 0.1.17 — HAOS acceptance

Date: 2026-09-27

## Scope

Version `0.1.17` was validated on a real Home Assistant OS installation using
the bundled acceptance harness and deterministic MQTT fixtures for physical
actuators.

The live gate covered the native room Climate UI introduced after 0.1.15 and
re-ran the existing actuator/safety/durability acceptance set.

## Native room Climate result

The room thermostat passed the complete native Climate sequence:

- HEAT season publishes room state `heat`;
- actual heating demand reports `hvac_action=heating`;
- effective profile is exposed through native Climate presets;
- selecting `night` exposes the Night target for editing;
- selecting Home Assistant's reserved `none` returns to the automatically
  effective profile;
- COOL season publishes room state `cool` and `hvac_action=cooling`;
- interseason publishes room state `off`;
- MQTT Climate capabilities remain stable as `off / heat / cool` across the
  season transitions so Home Assistant does not rebuild the Climate entity.

## Safety and actuator result

The same run passed:

- `device_target_out_of_range` start and recovery;
- bounded `device_no_confirmation` retry through RETRY 2/3, RETRY 3/3 and
  COOLDOWN 300s, followed by recovery;
- SLOW heat floor behavior and shutdown outside HEAT season;
- window context with selective `window_off_devices` inhibition;
- reversible climate low-temperature heating protection without blocking COOL;
- humidity active control, range-problem reproduction and safe power-off while
  the stored target is outside the physical humidifier range.

## Durability result

A Climate-App-only Supervisor backup was created before the test configuration
was applied. The backup was restored successfully after all behavioral gates.

The restore preserved:

- App options;
- persisted room targets;
- season thresholds;
- App version `0.1.17`.

The final runtime returned to a clean baseline with:

- room state `heat`;
- room control action `idle`;
- aggregate Problem `off`;
- Problem count `0`.

## Runtime acceptance result

```text
repository CI = green
container build = green
real HAOS update/start = green
room native HEAT/COOL/OFF semantics = green
room day/night/away presets = green
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

Runtime acceptance is complete.

Immutable publication is performed by the reviewed repository release marker:

- tag: `digitalhouses_climate_app-v0.1.17`;
- image: `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.17`.

The published manifest digest and release workflow run are recorded after the
release workflow completes.

No published immutable image version may be overwritten with different content.
