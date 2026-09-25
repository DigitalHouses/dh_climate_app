# Implementation plan

Status: implementation-complete for the first HAOS acceptance cycle.

## Phase 0 — architecture baseline ✅

- behavior contract extracted from the legacy PostgreSQL project;
- current product decisions separated from legacy implementation detail;
- pure Python domain core;
- automated coverage for season, profiles, hysteresis, source priority and FAST/SLOW rules.

## Phase 1 — configuration + persistence ✅

- flat Supervisor-compatible App options;
- stable room IDs and entity-domain validation;
- SQLite state under `/data`;
- persisted season thresholds;
- persisted room target matrix;
- persisted thermostat action for hysteresis continuity;
- persisted humidity targets/control;
- rolling outdoor sample persistence and pruning with left-edge baseline preservation.

## Phase 2 — Home Assistant input adapter ✅

- Supervisor REST client;
- Home Assistant WebSocket client;
- subscribe-before-snapshot reconnect;
- configured-entity allowlist;
- timestamp-protected state cache;
- current snapshot before control resumes after reconnect.

## Phase 3 — outdoor + season facade ✅

- independent priority/fallback chains for temperature and humidity;
- time-weighted rolling avg24;
- live-source fail-safe;
- periodic rolling-window recalculation;
- global `HEAT / COOL / OFF`;
- MQTT two-threshold `heat_cool` climate facade;
- persisted lower/upper season threshold commands.

## Phase 4 — room thermostat facade ✅

- room temperature/humidity canonicalization;
- `day / night / away / antifreeze` profile resolution;
- target matrix;
- stateful room hysteresis;
- one MQTT Device per room;
- room climate entity;
- target/profile/mode commands;
- short-lived legacy profile editing overlay.

## Phase 5 — direct equipment execution ✅

- desired-state compiler;
- FAST heat/cool execution;
- SLOW local-thermostat season execution;
- switch/climate service adapters;
- idempotent reconciliation;
- capability/range validation;
- bounded retry/cooldown;
- aggregate problems;
- optional open-window per-device inhibition;
- legacy low-outdoor-temperature protection for reversible climate heating.

## Phase 6 — humidity ✅

- optional humidifier/dehumidifier entity;
- humidity target persistence;
- stateful humidity hysteresis;
- switch/humidifier actuator execution.

## Phase 7 — product shell ✅

- HAOS App packaging;
- system/season/room MQTT device topology;
- Version + Started at + Problem diagnostics;
- opt-in DigitalHouses telemetry with authenticated deletion;
- English/Russian translations;
- immutable GHCR release workflow;
- unit/contract/compile/shell/container CI;
- product and architecture documentation.

## Phase 8 — real HAOS acceptance ⏳

This is the remaining release gate and cannot be proven only inside repository CI.

Execute [HAOS_TEST_PLAN.md](../HAOS_TEST_PLAN.md) against a real Home Assistant OS installation and real configured entities.

Required minimum before calling `0.1.0` a completed release:

- versioned image installed successfully;
- MQTT season facade verified;
- one real room MQTT Device verified;
- FAST heating and cooling paths verified;
- SLOW physical thermostat path verified;
- restart/reconnect verified;
- backup/restore verified.

Any defect found in this phase is fixed with a new immutable version once a version has already been published.
