# DH Climate App — implementation plan

## Goal

Build the new App incrementally from deterministic business logic outward.

Rule:

> No integration layer is allowed to invent climate behavior that is missing from Core tests.

## Phase 0 — architecture baseline

Deliverables:

- `ARCHITECTURE.md`;
- `BEHAVIOR_CONTRACT.md`;
- `CONFIGURATION.md`;
- `MQTT_CONTRACT.md`;
- this plan.

Review against:

- current product conversation decisions;
- DH Climate 5 functional contract;
- `DigitalHouses/dh_climate_1` behavior;
- applicable DigitalHouses shared App/release/telemetry contracts.

## Phase 1 — repository / HA App skeleton

Create:

```text
digitalhouses.app
config.yaml
Dockerfile
CHANGELOG.md
DOCS.md
translations/en.yaml
translations/ru.yaml
rootfs/run.sh
rootfs/app/
tests/
```

Initial version source:

```text
config.yaml
```

Required common diagnostics from the beginning:

- version;
- started_at.

Do not add telemetry yet unless canonical product ID is admitted to shared server allowlist.

## Phase 2 — pure Python climate core

Modules:

```text
core/models.py
core/source_selector.py
core/rolling_average.py
core/season.py
core/profiles.py
core/thermostat.py
core/humidity.py
core/device_plan.py
```

No HA, MQTT or SQLite imports inside pure decision functions where avoidable.

Mandatory tests:

### Source selection

- first source valid;
- first stale -> second used;
- first unavailable -> second used;
- higher-priority source recovery;
- temp and humidity select independently;
- no source -> unknown, never zero.

### Avg24

- irregular sample spacing;
- exact 24h clipping;
- restart-restored samples;
- one sample fallback semantics;
- stale gap handling.

### Season

- below lower boundary;
- exactly boundary;
- neutral band;
- above upper boundary;
- hysteresis;
- unknown outdoor fact.

### Profile

- day;
- night;
- away;
- HEAT + control off -> antifreeze;
- precedence tests.

### Thermostat

- HEAT enter heating;
- HEAT exit heating;
- inside hysteresis retains prior state;
- COOL symmetric cases;
- missing temperature -> off/unavailable;
- season OFF;
- persisted previous action continuity.

### Humidity

- humidifier demand;
- dehumidifier demand;
- hysteresis;
- missing humidity.

### Device Plan

- FAST switch;
- FAST climate passthrough;
- FAST fixed-active target;
- SLOW switch in/out HEAT;
- SLOW climate independent floor target;
- room target reached stops FAST but does not stop SLOW.

## Phase 3 — SQLite continuity store

Module:

```text
persistence.py
```

Initial tables, conceptually:

```text
schema_meta
system_state
season_settings
outdoor_samples
room_targets
room_runtime_state
humidity_targets
actuator_runtime_state
problems
```

Tests:

- migrations from empty DB;
- WAL;
- FULL synchronous;
- foreign keys;
- reopen continuity;
- target persistence;
- stateful hysteresis continuity;
- avg24 sample continuity;
- integrity check.

SQLite must never grow a jobs/dispatcher schema.

## Phase 4 — configuration parser/validator

Module:

```text
config.py
```

Read:

```text
/data/options.json
```

Validate:

- unique IDs;
- supported entity domains;
- source definitions;
- threshold order;
- FAST/SLOW required fields;
- humidity contour;
- no self-reference;
- no duplicate actuator ownership unless explicitly supported.

Tests use real-shaped options JSON.

## Phase 5 — Home Assistant adapter

Modules:

```text
ha/client.py
ha/snapshot.py
ha/services.py
```

Implement:

- Supervisor REST;
- Supervisor WebSocket;
- subscribe-before-snapshot buffering;
- full snapshot;
- state_changed;
- reconnect;
- service calls;
- observed state normalization.

No long-lived HA token in config.

## Phase 6 — coordinator

Module:

```text
coordinator.py
```

Pipeline:

```text
HA fact change
-> normalize
-> source selection
-> derived outdoor/room facts
-> recompute only affected decisions
-> persist semantic state
-> build Device Plan
-> publish facade
-> reconcile actuators
```

Coordinator owns sequencing; modules own calculations.

Avoid periodic 1-second full-system polling when event-driven recomputation is sufficient.

## Phase 7 — MQTT facade

Module:

```text
mqtt_facade.py
```

Implement:

- global device;
- two-slider season climate;
- separate room devices;
- room climate;
- optional humidity entity;
- version/start/health;
- retained state;
- command adapters.

Contract tests freeze:

- unique IDs;
- device IDs;
- topics;
- discovery payload keys;
- minimal entity count.

## Phase 8 — actuator executor/reconciliation

Modules:

```text
execution/base.py
execution/switch.py
execution/climate.py
execution/humidifier.py
execution/reconciler.py
```

Flow:

```text
Device Plan
-> compare desired vs observed
-> HA service call only if mismatch
-> observe fresh state
-> bounded retry
-> problem on unresolved mismatch
```

No decision rules in adapters.

Tests:

- no-op suppression;
- switch ON/OFF;
- climate mode/target ordering;
- SLOW thermostat target;
- unavailable device;
- recovery;
- bounded retry;
- duplicate event resilience.

## Phase 9 — runtime safety and observability

Add:

- concise problems;
- startup checks;
- source stale diagnostics;
- actuator mismatch diagnostics;
- structured Russian logs;
- graceful shutdown.

No high-frequency diagnostic entity spam.

## Phase 10 — real HAOS validation

Test on a non-critical room first.

Sequence:

1. observe-only mode;
2. season facade;
3. one room facade;
4. one FAST switch;
5. one FAST climate device;
6. one SLOW physical thermostat;
7. humidity contour;
8. HA restart;
9. App restart;
10. source failover;
11. device unavailable/recovery.

Only after behavior is verified expand to the full house.

## Phase 11 — telemetry/release

Before telemetry:

- assign canonical telemetry product ID;
- update shared server allowlist/protocol docs;
- implement shared client;
- default OFF;
- release-build gating.

Before first public release:

- freeze MQTT IDs/topics;
- freeze room/device config identifiers;
- full test suite;
- version contract;
- immutable image/release contract;
- changelog;
- backup/restore test.

## Definition of done for first useful release

A release is useful when it can:

1. calculate reliable outdoor avg24 from priority/fallback sources;
2. determine HEAT/COOL/OFF;
3. expose two-slider season thermostat;
4. create one MQTT Device + climate entity per room;
5. resolve room profile/target/hysteresis;
6. directly control FAST switch/climate;
7. keep SLOW floor thermostat at separate floor target during HEAT;
8. optionally control humidifier/dehumidifier;
9. survive restart without losing targets or hysteresis state;
10. fail explicitly and safely when source/device data is unavailable.
