# Legacy DH Climate 5 audit

**Source repository:** `DigitalHouses/dh_climate_1`  
**Purpose:** extract behavior, not implementation architecture.

## 1. Reviewed implementation surfaces

The legacy repository was reviewed at the actual implementation level, including:

- `_db_dump.sql`;
- `src/dh_climate_pg/main.py`;
- `src/dh_climate_pg/workers/ha_thermostat_facade_worker.py` (v5.12);
- `src/dh_climate_pg/workers/ha_outdoor_thermostat_facade_worker.py` (v4.2);
- `src/dh_climate_pg/workers/ha_system_facade_worker.py`;
- room/outdoor procedures and views in the database dump.

No credentials from the old repository are part of the new design.

## 2. Legacy room facade

The room facade worker was explicitly an IO/MQTT adapter over PostgreSQL truth.

Important behavior found:

- reads `v_facade_room_thermostat_state`;
- publishes current temperature;
- publishes target temperature;
- publishes `hvac_mode`;
- publishes `hvac_action`;
- exposes profile as climate `fan_mode`;
- profile values: day/night/away/antifreeze;
- target edit is debounced and committed for selected profile/current season;
- room mode command is constrained by active season;
- retained MQTT commands are intentionally ignored.

This behavior is retained semantically, not structurally.

## 3. Legacy profile model

Actual `v_room_effective_profile` order:

```text
HEAT + climate_control=false -> antifreeze
else we_at_home != on        -> away
else night_mode == on        -> night
else                         -> day
```

The new Python Profile Resolver must reproduce this order.

## 4. Legacy target model

Legacy target key:

```text
room × season × profile
```

`sp_room_set_target` changes one target key and triggers room action recalculation.

This remains the new contract.

## 5. Legacy room temperature/humidity truth

Legacy PostgreSQL room recalculation:

- stored latest raw value per enabled sensor;
- took the latest value from every enabled sensor;
- calculated arithmetic mean across those latest values.

This is **not silently copied**.

Current product discussion describes ordered sensors and fallback. New design therefore proposes priority/fallback for room sources until an explicit averaging decision is made.

This difference is recorded in `DESIGN_DECISIONS.md`.

## 6. Legacy hysteresis

Legacy room facade used setting:

```text
room_thermostat_temperature_hysteresis
```

The database projection compared room temperature against target ± hysteresis.

Earlier DH Climate functional behavior also defined symmetric stateful hysteresis.

New App keeps the stronger stateful contract:

```text
inside hysteresis band -> retain previous action
```

## 7. Legacy antifreeze

Actual legacy semantics:

- room thermostat OFF during HEAT sets `climate_control=false`;
- effective profile becomes antifreeze;
- antifreeze uses normal target storage;
- COOL + off is a real no-demand state.

This is retained.

## 8. Legacy outdoor provider model

The database contained independent temperature/humidity providers with numeric priority.

Actual selection ordered providers by lower `provider_priority` first.

The new config list order replaces the provider table:

```text
first config entry = highest priority
```

Temperature and humidity remain independent.

## 9. Legacy outdoor averaging

Legacy `sp_outdoor_recalculate_temperature` and humidity equivalent calculated:

- current value;
- avg1h;
- avg24;

using SQL `AVG` over observations inside each time window.

Because Home Assistant state events are irregularly spaced, this sample-count average can bias the result.

New App deliberately changes avg24 to time-weighted rolling average.

## 10. Legacy season decision

Actual PostgreSQL procedure:

```text
avg24 < heat_threshold - hysteresis -> HEAT
avg24 > cool_threshold + hysteresis -> COOL
else                                -> OFF
```

It stored:

- season;
- avg24;
- heat threshold;
- cool threshold;
- hysteresis;
- reason.

New Python Season Controller retains this behavior.

The old implementation had a dedicated outdoor season hysteresis. Current product decision simplifies this to one global house temperature hysteresis.

## 11. Legacy outdoor thermostat facade

The facade published a Home Assistant `climate` entity with:

- only `heat_cool` mode;
- current temperature from avg24, fallback current;
- current humidity from avg24, fallback current;
- low slider = heat threshold;
- high slider = cool threshold;
- action heating/cooling/idle by season.

This is a direct behavioral source for the new season facade.

## 12. Legacy room thermostat device placement

Legacy room climate entities were attached to the shared DH Climate MQTT device.

This is intentionally changed.

New contract:

```text
one room -> one MQTT Device
```

Reason: the user must be able to assign the whole room thermostat device to a Home Assistant Area.

## 13. Legacy device pipeline

The old repository contains substantial device/execution machinery:

- device registry/capability layer;
- Matrix/Firewall;
- dispatcher;
- Universal Controller;
- confirmation/supervision;
- retry lifecycle.

None of these components is ported.

Useful semantics extracted from it are reduced to:

```text
Room Decision
-> Device Plan
-> small HA domain adapter
-> observed-state reconciliation
```

## 14. Legacy target transformation concept

Old functional specifications distinguished:

- target passthrough;
- target transform allowed.

New App keeps the concept only where required for FAST `climate` devices:

- `passthrough`;
- `fixed_active_target`.

Transformation must be explicit in configuration/device plan.

## 15. New behavior not present as first-class legacy model

The current product design adds:

- FAST/SLOW as simple explicit room device classes;
- direct App-owned actuator bindings;
- SLOW physical thermostat with separate floor/slab target;
- optional per-room humidifier/dehumidifier facade;
- one room MQTT device per room;
- entity minimization.

These are current product decisions and override older deferred-v1 documents.

## 16. Migration rule

For every legacy function encountered during implementation, classify it as one of:

```text
A. business behavior to retain
B. facade behavior to retain
C. persistence detail to redesign
D. execution machinery to delete
E. legacy feature requiring explicit product decision
```

Never port code merely because it exists.
