# DH Climate App — HAOS acceptance plan

Status: release gate for the first experimental `0.1.0` image.

The unit test suite proves deterministic business rules. This plan proves the boundaries that only a real Home Assistant OS installation can verify: Supervisor configuration, MQTT Discovery, entity UI behavior, service execution, persistence, backup and restore.

For Experimental source-build installation/update problems, use [docs/EXPERIMENTAL_UPDATE_RUNBOOK.md](docs/EXPERIMENTAL_UPDATE_RUNBOOK.md). In particular, if HAOS can fetch the new GitHub `main` version directly but Supervisor Store still reports the previous `version_latest`, treat it as stale Supervisor Store state and restart Supervisor before doing broader diagnostics.

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

- first valid temperature source wins;
- first valid humidity source wins independently;
- primary unavailable -> fallback source is selected;
- primary restored -> primary becomes current source again;
- current source/value is visible in season attributes;
- rolling avg24 survives App restart;
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
- room climate advertises stable `off/auto` capabilities;
- HEAT/COOL + enabled room publishes `auto`;
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
- unavailable physical entity produces a Problem diagnostic instead of a tight retry loop.

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

Acceptance:

- default `telemetry_enabled=false` sends no request;
- enabling telemetry triggers one immediate best-effort heartbeat;
- ordinary restart does not trigger another heartbeat before cadence is due;
- version change is eligible for an immediate heartbeat;
- telemetry-server failure does not affect climate runtime or Problem health;
- telemetry payload contains no room, entity, device, climate or network-inventory data;
- Delete telemetry removes this installation from the telemetry service using its installation credential.

## 12. Backup and immutable delivery

Acceptance:

- Full Backup contains persistent `/data` state;
- restored App preserves season thresholds, room targets, humidity targets and telemetry installation identity;
- backup does not embed a locally built application image;
- after a newer version exists, a backup from the older released version can still restore by retrieving its historical versioned GHCR image.

## 13. Release decision

The first release is accepted only when:

```text
repository CI = green
container build = green
real HAOS install/start = green
season facade = green
one FAST heat path = green
one FAST cool path = green
one SLOW thermostat path = green
restart/reconnect = green
backup/restore = green
```

Failures found in HAOS acceptance are fixed in a new commit/version. A published immutable image version is never overwritten with different content.
