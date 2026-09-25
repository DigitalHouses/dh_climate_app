# DH Climate App — design decisions

This file separates **accepted product decisions** from points that still require implementation-level confirmation.

## Accepted

### D-001 — Behavior port, not code port

Legacy DH Climate 5 is a behavioral reference. PostgreSQL implementation structure is not retained.

### D-002 — Python Core owns climate logic

All season/profile/room/humidity/device-class behavior is implemented in deterministic Python.

### D-003 — SQLite only for persistence

SQLite provides restart continuity. It is not an orchestration engine.

### D-004 — One global temperature hysteresis

House-level temperature hysteresis is configured once in App config.

### D-005 — Outdoor provider priority is list order

Temperature and humidity each have their own ordered list and independent fallback.

### D-006 — Time-weighted avg24

New App corrects the old sample-count AVG behavior.

### D-007 — Season facade is a two-slider climate entity

Low = heat threshold, high = cool threshold.

### D-008 — Room mode follows global season

Room cannot independently choose heat versus cool.

### D-009 — Each room is a separate MQTT Device

The user assigns that device to a Home Assistant Area.

### D-010 — Minimal room entity surface

Default room device contains climate plus optional humidity controller, not copies of raw source sensors.

### D-011 — Humidity type is per room

A room is configured as humidifier, dehumidifier, or none.

### D-012 — FAST and SLOW are first-class device classes

FAST follows room thermostat demand. SLOW follows seasonal comfort semantics.

### D-013 — SLOW floor target differs from air target

A physical floor thermostat receives its own floor/slab target and performs local control.

### D-014 — Direct HA execution belongs to App

Current design supersedes the earlier prototype where HA scripts owned equipment mapping.

### D-015 — Executor cannot invent decisions

Target transforms, participation and mode are explicit in Device Plan.

## Proposed implementation choices

These are compatible with accepted architecture but can be adjusted before first release.

### P-001 — Room sensor policy

Use ordered priority/fallback for room temperature/humidity initially.

Reason: current spoken product requirement describes ordered sources; old PostgreSQL implementation averaged all enabled room sensors. If averaging is needed, add explicit `aggregation: average` rather than silently restoring legacy behavior.

### P-002 — Humidity hysteresis

Use separate `hysteresis_percent` because temperature hysteresis is in °C and cannot correctly represent humidity deadband.

### P-003 — FAST climate target policy

Require explicit `target_policy`:

- passthrough;
- fixed_active_target.

This preserves the old distinction between target passthrough and allowed transforms without rebuilding the old device matrix.

### P-004 — SLOW target location

Store SLOW target in App configuration first. Do not create a separate HA number entity until there is a real UI need.

### P-005 — Simple reconciliation

Use bounded in-process retry based on fresh HA state; do not persist a command queue.

## Explicitly unresolved before coding final adapters

### O-001 — Room source aggregation

Confirm whether a room with two valid temperature sensors should:

- take first by priority; or
- average them.

Architecture currently chooses priority/fallback to avoid hidden averaging.

### O-002 — Humidity actuator coverage

Confirm which initial physical domains are required in production beyond `switch` and `humidifier`.

### O-003 — FAST physical climate target transform

For the first real radiator/TRV/AC device, confirm whether passthrough room target is sufficient or fixed-active target is needed.

These points do not block pure core, persistence, HA adapter, season facade, or MQTT room-device implementation.
