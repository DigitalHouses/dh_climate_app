# DH Climate App — Architecture v0.1

**Status:** implementation baseline  
**Date:** 2026-09-25  
**Source of behavior:** current product decisions + `DigitalHouses/dh_climate_1` PostgreSQL implementation.

## 1. Goal

`dh_climate_app` is a Home Assistant App that owns climate decision logic for the house and exposes native Home Assistant entities through MQTT Discovery.

The new App preserves the useful **behavior** of DH Climate 5, not its PostgreSQL implementation.

```text
Home Assistant states
        ↓
HA input adapter
        ↓
Climate Core
 ├─ Outdoor / avg24 / season
 ├─ Room thermostat
 ├─ Humidity controller
 └─ Device policy (FAST / SLOW)
        ↓
Desired device state
        ↓
HA service executor
        ↓
climate / switch / humidifier devices

Climate Core
        ↓
MQTT Discovery facade
        ↓
Home Assistant UI
```

PostgreSQL, SQL jobs, Dispatcher, Matrix, UC queue, Confirmator and Supervisor are not ported.

## 2. Architectural rules

1. **Python owns business logic.** SQL is never a business execution engine.
2. **State is truth; events are hints.** HA events trigger recomputation, but reconnect always starts from a current-state snapshot.
3. **Idempotent execution.** The App computes desired state and only sends a HA service command when actual state differs.
4. **Minimal HA entity count.** Values already represented by a functional entity are not duplicated as separate room sensors.
5. **One room = one MQTT Device.** Every room receives a stable MQTT device identifier and can be assigned by the user to a Home Assistant Area.
6. **One global season.** Rooms do not choose HEAT/COOL independently.
7. **One house-wide temperature hysteresis.** The compact App intentionally collapses the legacy room and outdoor hysteresis settings into one configured value.
8. **Persistent configuration vs runtime settings are separate.**
   - App options bind external HA entities and device topology.
   - User-adjusted thermostat targets and season thresholds are runtime state persisted under `/data`.
9. **No site-specific entity names in source code.** All HA bindings are configuration.
10. **Machine events only.** If notifications are added later, the App publishes machine events; local HA owns text and delivery.

## 3. Inputs

### 3.1 Global HA facts

Optional global profile inputs:

- `night_mode`
- `we_at_home`

Legacy effective profile precedence is retained:

```text
HEAT + climate control OFF → antifreeze
else not at home           → away
else night mode            → night
else                       → day
```

### 3.2 Outdoor sources

The App configuration contains two independent ordered lists:

- `outdoor_temperature_sources`;
- `outdoor_humidity_sources`.

The first currently valid numeric entity in each list is selected. Temperature and humidity therefore fail over independently.

`unknown`, `unavailable`, empty and non-numeric states are invalid and cause fallback to the next entity.

Temperature is required for live season control. If every live outdoor temperature source is unavailable, the App forces season to `OFF` even if historical avg24 data still exists.

### 3.3 Room sensors

Each room may define one or more:

- temperature sensors;
- humidity sensors.

For room temperature/humidity the legacy room behavior is retained: use the mean of the latest valid readings from all configured available sensors of that kind.

If no valid room temperature exists, FAST thermostat demand is inhibited and the room thermostat facade becomes unavailable.

## 4. Outdoor calculation

The App stores outdoor samples required for a rolling 24-hour calculation.

`avg_outdoor_24` is a **time-weighted** rolling average, so irregular HA update frequency does not bias the result.

The global season is:

```text
avg24 < heat_threshold - hysteresis → HEAT
avg24 > cool_threshold + hysteresis → COOL
otherwise                           → OFF
```

`OFF` is interseason.

The season facade repeats DH Climate 5 behavior:

- Home Assistant domain: `climate`;
- mode: `heat_cool`;
- current temperature: `avg_outdoor_24`;
- current humidity: rolling 24h humidity when available;
- lower target: heating-season threshold;
- upper target: cooling-season threshold;
- action:
  - HEAT → `heating`
  - COOL → `cooling`
  - OFF → `idle`

The two threshold sliders are writable and persisted.

## 5. Room thermostat

Each configured room exposes one MQTT `climate` entity.

The room thermostat contains:

- current room temperature;
- target room temperature;
- HVAC mode determined by global season;
- HVAC action determined by room demand;
- profile presented through the same user-facing behavior as legacy DH Climate.

Allowed HVAC modes follow the global season:

```text
HEAT → off, heat
COOL → off, cool
OFF  → off
```

The target matrix remains:

```text
room × season × profile → target temperature
```

Profiles:

- `day`
- `night`
- `away`
- `antifreeze`

Changing target temperature in the room thermostat updates the target for the currently selected/effective profile in the current season.

### 5.1 Stateful thermostat hysteresis

The new App uses real stateful symmetric hysteresis:

HEAT:

```text
T <= target - h → heating
T >= target + h → idle
inside band      → retain previous heating/idle state
```

COOL:

```text
T >= target + h → cooling
T <= target - h → idle
inside band      → retain previous cooling/idle state
```

This state is persisted so an App restart does not collapse the hysteresis band.

## 6. Room MQTT device model

Every room is a separate MQTT Device.

Stable identifier:

```text
dh_climate_app_room_<room_id>
```

Example:

```text
dh_climate_app_room_living_room
```

The user assigns this device to the appropriate Home Assistant Area after discovery.

Default entities on the room device are intentionally minimal:

1. `climate` — room thermostat.
2. optional `humidifier` — only when humidity control is configured.

No duplicate room `sensor.temperature` or `sensor.humidity` entities are created merely to repeat values already visible in these functional entities.

## 7. Humidity control

Humidity control is optional per room.

Room configuration chooses exactly one controller type:

```text
humidifier
dehumidifier
```

The entity is published in the Home Assistant `humidifier` domain.

- humidifier: normal humidifier device class/behavior;
- dehumidifier: `device_class: dehumidifier`.

The entity contains:

- current humidity;
- target humidity.

If humidity control is not configured, no humidity-control entity is published.

Humidity control is independent of HEAT/COOL season.

A separate global humidity hysteresis will be used by the humidity controller because percent RH and °C cannot share one numeric deadband.

## 8. Device classes

Room actuator configuration introduces two thermal classes.

### 8.1 FAST

Examples:

- radiator;
- convector;
- fan-coil;
- air conditioner.

FAST devices follow room thermostat demand.

```text
room heating → configured FAST heat devices active
room cooling → configured FAST cool devices active
room idle/off → FAST devices inactive
```

Supported HA execution domains in the first implementation:

- `switch`;
- `climate`.

For a FAST climate device, the App sets the required HVAC mode and room target temperature. For a FAST switch, the App uses `turn_on` / `turn_off`.

### 8.2 SLOW

Primary case: underfloor heating with its own local physical thermostat and floor probe.

SLOW devices do **not** follow room thermostat cycling.

```text
season HEAT → SLOW device enabled
season COOL/OFF → SLOW device disabled
```

For a SLOW `climate` device:

```text
HEAT:
  hvac_mode = heat
  target_temperature = slow target configured for that device
```

The local physical thermostat then cycles the heating locally using its own probe.

The SLOW target is deliberately separate from room air target. A floor probe measures floor/screed temperature, not room air temperature.

A SLOW plain `switch` is rejected in v0.1. SLOW control requires a local HA `climate` thermostat so the physical floor/slab probe remains the final local safety and cycling loop.

## 9. Device capability binding

Every configured actuator declares what it can do.

External App configuration is intentionally flatter than the internal model:

```text
fast_heat = comma-separated switch/climate entities
fast_cool = comma-separated switch/climate entities
slow_heat = comma-separated climate entities
slow_target = one floor/comfort target for SLOW thermostats in the room
```

If the same `climate` entity is listed in both FAST lists, the internal model compiles it as `heat_cool`. A `switch` may appear in only one thermal list. An entity may have only one owner across the complete configuration.

## 10. Persistence

Use SQLite only as lightweight persistent state under:

```text
/data/dh_climate.db
```

SQLite is **not** an orchestration engine.

It stores only data that must survive restart:

- schema version;
- season heat/cool thresholds;
- rolling outdoor samples needed for avg24;
- room target matrix;
- humidity targets;
- previous room thermostat action for stateful hysteresis;
- last known selected profile overlay only if required for facade continuity;
- compact execution/retry state if needed;
- product state metadata.

No:

- jobs;
- handlers;
- dispatcher tables;
- UC command queue;
- SQL procedures;
- SQL business rules.

## 11. HA connection model

Use Supervisor internal Home Assistant API.

Startup/reconnect order:

```text
1. connect HA WebSocket
2. subscribe to state_changed
3. buffer relevant events
4. read current snapshot of every configured entity
5. apply snapshot
6. replay only buffered events newer than the snapshot boundary
7. enter live event processing
8. calculate all climate state
9. reconcile physical devices
10. publish MQTT facade
```

Historical HA events are never replayed.

A periodic lightweight tick recalculates rolling 24h averages even when no outdoor sensor emitted a new state change.

## 12. Execution model

The new App directly controls configured devices through Home Assistant services.

There is no replacement for the old Universal Controller as a general subsystem.

Instead each actuator has a simple reconcile loop:

```text
desired state
vs
current HA state
→ equal: no action
→ different: issue one appropriate HA service call
→ observe resulting state
→ bounded retry on failure
```

This preserves reliability without recreating the PostgreSQL command lifecycle.

## 13. MQTT topology

System device:

```text
identifier: dh_climate_app
name: DigitalHouses Climate
```

System device owns:

- season `climate` facade;
- outdoor current/avg24 state that is genuinely useful;
- global problems/health;
- Version diagnostic;
- Started at diagnostic.

Room devices:

```text
dh_climate_app_room_<room_id>
```

Each room device owns only its room-facing functional entities.

MQTT Discovery and current state are retained. Transient machine events are not retained.

## 14. Legacy behavior retained

From `DigitalHouses/dh_climate_1`:

- outdoor source priority/fallback;
- outdoor current + 24h derived concept;
- global `HEAT / COOL / OFF`;
- two-slider `heat_cool` season thermostat;
- room-as-thermostat abstraction;
- room target matrix by season/profile;
- `day/night/away/antifreeze`;
- season-restricted room HVAC modes;
- profile editing through thermostat facade;
- temperature/humidity normalization;
- fallback/unavailable semantics;
- MQTT Discovery facade concepts.

## 15. Legacy architecture intentionally removed

Not ported:

- PostgreSQL as business engine;
- append-only SQL runtime architecture;
- system job queue;
- handlers;
- Matrix;
- Firewall as a separate engine;
- Dispatcher;
- UC queue;
- Universal Controller;
- Confirmator;
- UC Supervisor;
- SQL component status;
- SQL runtime sessions;
- PostgreSQL-specific system facade diagnostics.

Equivalent useful behavior is implemented directly in Python where still required.

## 16. Implementation modules

Target Python layout:

```text
src/dh_climate_app/
├── app.py
├── config.py
├── core.py
├── persistence.py
├── ha_client.py
├── outdoor.py
├── rooms.py
├── humidity.py
├── devices.py
├── executor.py
├── mqtt.py
├── discovery.py
├── telemetry.py
└── problems.py
```

Dependency direction:

```text
config / models
      ↓
pure core
      ↓
domain services
      ↓
HA + MQTT adapters
      ↓
app runtime
```

`core.py` must remain testable without Home Assistant, MQTT or SQLite.

## 17. First implementation slice

The first executable slice is intentionally vertical:

```text
configured outdoor sources
→ priority selection
→ rolling avg24
→ season
→ season facade

configured room temperature sensors
→ room temperature
→ profile/target
→ thermostat action
→ FAST/SLOW desired state
```

These deterministic rules are now wired to the Home Assistant WebSocket/REST adapters, MQTT facade and direct device reconciliation. The remaining release gate is real HAOS integration testing against configured entities.
