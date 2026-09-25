# Implementation plan

## Phase 0 — architecture baseline

- freeze behavior contract from legacy PostgreSQL project;
- define current overrides from product discussions;
- create pure Python domain core;
- cover season, profile, hysteresis, source priority and FAST/SLOW rules with tests.

## Phase 1 — configuration + persistence

- parse HA App options;
- validate stable room IDs and entity domains;
- SQLite schema under `/data`;
- persist season thresholds;
- persist room target matrix;
- persist room previous action;
- persist rolling outdoor samples;
- migration/version handling.

## Phase 2 — Home Assistant input adapter

- Supervisor REST client;
- Home Assistant WebSocket client;
- subscribe-before-snapshot reconnect algorithm;
- configured-entity allowlist;
- normalized state cache;
- relevant-state dispatch.

## Phase 3 — outdoor + season facade

- provider priority/fallback;
- rolling current/avg24 temperature and humidity;
- periodic rolling-window recalculation;
- season decision;
- MQTT `heat_cool` two-threshold climate facade;
- persisted threshold commands.

## Phase 4 — room thermostat facade

- room temperature/humidity canonicalization;
- profile resolution;
- target matrix;
- stateful room hysteresis;
- MQTT room device per configured room;
- room climate entity;
- target/profile/mode commands.

## Phase 5 — direct equipment execution

- desired-state compiler;
- FAST device execution;
- SLOW device season execution;
- `switch` adapter;
- `climate` adapter;
- idempotent reconciliation;
- bounded retry and problems.

## Phase 6 — humidity

- optional humidifier/dehumidifier entity;
- humidity target persistence;
- humidity hysteresis;
- switch/humidifier actuator execution.

## Phase 7 — product shell

- HAOS App packaging;
- Version + Started at diagnostics;
- optional telemetry following DigitalHouses policy;
- translations;
- docs;
- release/CI validation.
