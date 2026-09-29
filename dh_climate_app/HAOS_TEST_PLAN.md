# DH Climate App — HAOS acceptance plan

Status: historical bundled runtime acceptance for `0.1.21` passed on real HAOS on 2026-09-27 and its canonical GHCR artifact provenance is recorded. Current `main` (`0.1.26` development) requires fresh HAOS acceptance. Registry-backed Supervisor delivery is still pending because the App package does not yet declare `image:`.

The unit test suite proves deterministic business rules. This plan proves the boundaries that only a real Home Assistant OS installation can verify: Supervisor configuration, MQTT Discovery, entity UI behavior, service execution, persistence, backup and restore.

For Experimental source-build installation/update problems, use [docs/EXPERIMENTAL_UPDATE_RUNBOOK.md](docs/EXPERIMENTAL_UPDATE_RUNBOOK.md). Routine updates use `ha store reload`; repository repair is reserved for an explicitly corrupt Supervisor git checkout and must not be used as a refresh command.

## 1. Installation and startup

Acceptance:

- App installs from the versioned GHCR image for the target architecture.
- Empty first-start configuration is allowed.
- App starts without PostgreSQL or any external database.
- System MQTT Device appears as `DigitalHouses Climate`.
- `Version`, `Started at`, `Problem` and telemetry-delete diagnostics are attached to the system device.
- With no outdoor source configured, climate control remains safely unavailable/OFF rather than generating commands.

## 2. Outdoor sources and season facade

Configure at least two temperature sources and, if available, two humidity sources.

Acceptance:

- `outdoor_temperature_sources` accepts an ordered mixed chain of
  `sensor.*` and `weather.*` entities;
- first valid temperature source wins;
- first valid humidity source wins independently;
- every public one-decimal outdoor temperature change is logged with the active
  source;
- primary unavailable -> fallback source is selected;
- source selection emits `outdoor_temperature_source_changed` with
  previous/current source and temperature values;
- primary restored -> primary becomes current source again and emits the reverse
  source transition;
- startup/reconnect establishes a baseline and does not emit a false source
  transition;
- current source/value is visible in season attributes;
- MQTT facade attributes do not expose a per-recalculation `observed_at` timestamp;
- with stable outdoor temperature/humidity values and sources, their Home Assistant `last_updated` values remain unchanged across at least one 10-second runtime tick;
- `sensor.dh_climate_app_outdoor_temperature_raw` exposes the selected RAW source value but publishes no more than once per minute;
- hard low-temperature safety still uses the immediate selected RAW value internally and is not delayed by the Recorder-facing RAW publication cadence;
- `sensor.dh_climate_app_outdoor_temperature` exposes the one-minute EMA-filtered outdoor temperature;
- `sensor.dh_climate_app_outdoor_temperature_avg24` exposes the arithmetic mean of persisted one-minute filtered samples inside the rolling 24-hour window;
- `sensor.dh_climate_app_outdoor_humidity` exposes the current selected outdoor humidity;
- RAW, filtered and avg24 temperature remain separate state-only UI entities without dynamic custom attributes;
- rolling avg24 survives App restart from the App's persistent SQLite sample window and does not depend on Recorder history for climate calculation;
- when `sensor.avg_outdoor_temperature_24_temp` exists, it may be used as an observation oracle, but Recorder/Statistics is not the App's source of truth;
- no live outdoor temperature -> season becomes OFF even if old avg24 exists;
- lower/red slider persists the heating-season threshold;
- upper/blue slider persists the cooling-season threshold;
- avg24 below lower threshold minus hysteresis -> HEAT;
- avg24 above upper threshold plus hysteresis -> COOL;
- between thresholds -> OFF.

## 2.1 Weather precipitation and events

When a `weather.*` source is configured:

- current condition classifies rain/snow/mixed/hail/none correctly;
- hourly forecast precipitation is exposed in millimetres;
- rain → snow (and snow → rain) emits `precipitation_type_changed`;
- dry → precipitation emits `precipitation_started`;
- precipitation → dry emits `precipitation_stopped`;
- the MQTT Event payload is QoS 1 and non-retained;
- initial startup/reconnect establishes a baseline and does not replay a false
  transition;
- season, window and Problem transitions use the same
  `event.dh_climate_app_event` contract.

## 3. Room MQTT device

Create one test room.

Acceptance:

- room appears as a separate MQTT Device;
- device can be assigned manually to the correct Home Assistant Area;
- room exposes one `climate` entity;
- no redundant temperature/humidity sensor entities are created merely to duplicate thermostat values;
- multiple configured room temperature sensors are averaged;
- unavailable room temperature makes the room climate facade unavailable;
- room climate capabilities follow the global season exactly:
  HEAT -> `off/heat`, COOL -> `off/cool`, OFF -> `off`;
- changing season updates MQTT Discovery without losing the native
  `day/night/away` preset; the new season-scoped retained preset topic is
  consumed when Home Assistant resubscribes after the Discovery update;
- an enabled room publishes state `heat` in HEAT season and state `cool`
  in COOL season; interseason publishes state `off`;
- HVAC action independently exposes the current room action:
  `heating / cooling / idle / off`;
- OFF season keeps the climate entity available when room temperature is valid,
  publishes HVAC mode `off`, exposes current temperature, and no seasonal
  target;
- target/HVAC commands sent to the room thermostat during OFF season do not
  modify persisted room control state.

## 4. Room profiles and hysteresis

Acceptance:

- day target is used normally;
- `night_mode=on` selects night;
- `we_at_home=off` selects away;
- unavailable configured presence input resolves to away;
- turning room climate off during HEAT exposes HVAC off but internally uses antifreeze target;
- turning room climate off during COOL produces true off;
- profile selection in the thermostat is a temporary edit overlay;
- changing the target while another profile is selected writes that profile's target;
- profile edit overlay returns to the effective profile after its idle timeout;
- targets survive App restart;
- inside the hysteresis band the previous active/idle action survives both recalculation and App restart.

## 5. FAST execution

Test both a switch and a climate actuator where available.

Acceptance:

- heating demand turns on a FAST heat switch;
- idle/off turns it off;
- cooling demand activates only configured FAST cooling devices;
- FAST climate receives the correct HVAC mode and room air target;
- an already-correct physical state produces no duplicate service call;
- unsupported HVAC mode or out-of-range target is not blindly sent;
- unavailable physical entity produces a Problem diagnostic instead of a tight retry loop;
- App log shows FAST desired/actual, CALL, SENT, retry/cooldown, VERIFIED_HA and delayed DRIFT transitions; no executor CONFIRMED line is emitted;
- local `climate.log` receives the same selected traces through `script.write2climatelog` in App decision order;
- repeated already-correct reconciles do not create log spam;
- failure of the local climate-log mirror does not change actuator control or Problem state.

## 6. SLOW floor execution

Use a physical wall/floor thermostat with its own local floor or slab probe.

Acceptance:

- HEAT season sets the physical thermostat to `heat`;
- App sends the configured `slow_target`, not the room air target;
- room thermostat cycling does not repeatedly switch SLOW heat on/off;
- physical thermostat locally cycles its relay using its own probe;
- COOL/OFF season sets the SLOW thermostat to `off`;
- loss/restart of the App leaves the physical thermostat able to regulate at its last local setpoint until Home Assistant control resumes.

## 7. Window context

Configure at least two window contacts if available.

Acceptance:

- any open contact -> room `window_state=open`;
- all contacts closed -> `closed`;
- none open and one unavailable -> `unknown`;
- window state does not change room thermostat HVAC demand;
- only actuators listed in `window_off_devices` are forced off while a window is open;
- other actuators continue their normal policy;
- unknown configured window state produces a warning Problem.

## 8. Cold-weather reversible climate protection

Use a reversible `climate` entity in both `fast_heat` and `fast_cool`.

Acceptance:

- above `ac_min_outdoor_temperature`, heating demand may use the reversible climate device;
- below the threshold, that device is held off for heating;
- another allowed heat source can continue;
- cooling behavior is not blocked by the heating-only low-temperature rule.

## 9. Humidity

For a room with humidity control:

- MQTT `humidifier` entity appears on the same room Device;
- current and target humidity are correct;
- humidifier/dehumidifier direction follows configuration;
- humidity hysteresis prevents chatter;
- target changes survive restart;
- humidity control can be turned off independently of thermal season;
- no humidity-control entity is created for rooms where it is not configured.

## 10. Disconnect and recovery

Acceptance:

- stopping Home Assistant connectivity marks climate facades unavailable;
- cached sensor truth is discarded;
- no physical commands are issued while HA truth is disconnected;
- reconnect performs a fresh snapshot before normal control resumes;
- old buffered events cannot overwrite newer snapshot state;
- MQTT reconnect restores subscriptions and retained facade state;
- stale retained command messages do not alter runtime settings after restart.

## 11. Telemetry

Current `0.1.26` development code is still the policy-v1 baseline. Do not
declare policy v2 release-ready until the production
`telemetry.digitalhouses.vip` deployment is independently confirmed as
DigitalHouses Stats `0.4.1+`.

Final policy-v2 acceptance must verify:

- there is no user-facing `telemetry_enabled` opt-out;
- wire schema remains `1` and `telemetry_policy_version=2`;
- payload contains only schema, policy version, persistent UUIDv4,
  `digitalhouses_climate_app` and the released App version;
- country is absent from the client payload and derived only server-side;
- UUID/token survive restart, upgrade and supported backup/restore;
- normal cadence is about 24h ±30 minutes, with non-aggressive failure retry;
- a fresh install and a new released version may send one immediate best-effort heartbeat;
- development/local builds never contribute production statistics;
- telemetry-server/DNS/firewall failure never affects climate runtime or Problem health;
- authenticated Delete removes server history, rotates the local UUID/token,
  and continued product use later resumes reporting under the new identity.

## 12. Backup and immutable delivery

Acceptance after registry-backed App delivery is wired into `config.yaml`:

- the installed App uses `ghcr.io/digitalhouses/digitalhouses_climate_app:<version>`;
- a Supervisor backup containing the Climate App (full or App-only partial) contains persistent `/data` state;
- restored App preserves season thresholds, room targets, humidity targets and telemetry installation identity;
- backup does not embed a locally built application image;
- restore of the supported current production release retrieves the required published registry image.

Historical-version restore after a newer release exists is not a general
immutable-delivery acceptance requirement; test downgrade/rollback only when a
specific migration or recovery plan requires it.

## 13. Release decision

The block below is the historical acceptance record for released `0.1.21`; it must not be interpreted as acceptance of current `0.1.26` development code.

Last completed released runtime acceptance (`0.1.21`):

```text
repository CI = green
container build = green
real HAOS update/start = green
recorder churn guard = green
stable outdoor last_updated across runtime tick = green
outdoor temperature avg24 sensor = green
outdoor temperature change log = green
outdoor primary -> backup failover = green
outdoor source-switch Event = green
outdoor preferred-source recovery = green
HEAT modes off/heat only = green
COOL modes off/cool only = green
OFF modes off only = green
room day/night/away presets = green
preset reset to automatic profile = green
FAST heat/cool execution = green
target_out_of_range safety = green
no_confirmation/retry/cooldown = green
SLOW thermostat path = green
window context = green
cold-weather reversible climate protection = green
humidity safe shutdown = green
restart/reconnect = green
Climate-App-only backup/restore = green
final clean baseline = green
immutable release publication = green
```

See [docs/ACCEPTANCE_0.1.21.md](docs/ACCEPTANCE_0.1.21.md) for the recorded live acceptance result.

Published artifact: `digitalhouses_climate_app-v0.1.21` / `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.21` / `sha256:5870a9e2791fadc76165f2a5c604cf7d1f84d7448de5e5401721be2a63045349`.

This record does not waive the remaining registry-delivery gap: `config.yaml` still omits `image:`. Current `0.1.26` development changes require a new full HAOS acceptance before any release. Failures found in HAOS acceptance are fixed in a new commit/version; a published immutable image version is never overwritten with different content.
