# DH Climate App — proposed configuration contract

**Статус:** проектируемый контракт.  
Идентификаторы после первого public release должны считаться compatibility surface.

## 1. Design goals

Конфигурация должна быть:

- читаемой человеком;
- явной;
- без site-specific hardcode в коде;
- без SQL/passports;
- без скрытых defaults на critical device behavior;
- достаточно компактной для Home Assistant App options.

## 2. Proposed shape

Ниже canonical logical schema. Финальный `config.yaml -> schema` должен повторить его настолько близко, насколько позволяет Home Assistant App options schema.

```yaml
global:
  hysteresis_c: 0.5

profile_inputs:
  night_mode: input_boolean.night_time
  we_at_home: input_boolean.we_at_home

outdoor:
  temperature_sources:
    - entity_id: sensor.outdoor_temperature
    - entity_id: weather.home
      attribute: temperature

  humidity_sources:
    - entity_id: sensor.outdoor_humidity
    - entity_id: weather.home
      attribute: humidity

  stale_after_seconds: 1800

  initial_thresholds:
    heat_c: 12.0
    cool_c: 20.0

rooms:
  - id: living_room
    name: Living room

    temperature_sources:
      - entity_id: sensor.living_room_temperature

    humidity_sources:
      - entity_id: sensor.living_room_humidity

    initial_targets:
      heat:
        day: 23.0
        night: 22.0
        away: 18.0
        antifreeze: 10.0
      cool:
        day: 25.0
        night: 24.0
        away: 28.0

    devices:
      - id: radiator
        class: fast
        entity_id: climate.living_room_radiator
        target_policy: passthrough

      - id: floor
        class: slow
        entity_id: climate.living_room_floor
        slow_target_c: 27.0

    humidity_control:
      type: dehumidifier
      target_percent: 55
      hysteresis_percent: 3
      entity_id: humidifier.living_room_dehumidifier
```

Example values are illustrative; installation-specific values belong only in App options.

## 3. Stable room identity

`rooms[].id` is required and immutable after installation unless a migration is performed.

It is used for:

- SQLite keys;
- MQTT topics;
- MQTT Device identifier;
- entity unique IDs.

Room identity must **not** be derived from Home Assistant Area name.

The user assigns the discovered room MQTT Device to an Area in Home Assistant.

## 4. Source specification

Each source:

```yaml
- entity_id: sensor.example
  attribute: optional_attribute
```

If `attribute` is omitted, numeric entity state is read.

If `attribute` is present, numeric value is read from that attribute.

Source lists are ordered.

For outdoor sources, order is strict priority/fallback.

For room sources, first implementation will use ordered priority/fallback as the simplest current contract. If multi-sensor averaging is reintroduced, it must be an explicit `aggregation` option rather than a silent behavior change.

## 5. Staleness

A source is invalid if:

- entity unavailable;
- entity unknown;
- numeric parse fails;
- configured attribute absent;
- last valid observation older than the applicable stale timeout.

Critical facts must never silently become `0`.

## 6. Global hysteresis

```yaml
global:
  hysteresis_c: 0.5
```

One temperature hysteresis parameter is used by:

- global season threshold comparison;
- room air thermostat comparison.

It is canonical from config, not editable as a separate HA entity.

Humidity uses a percent-scale hysteresis because its unit differs from °C.

## 7. Season thresholds

Heat/cool thresholds are user-adjustable through the global two-slider season thermostat.

`outdoor.initial_thresholds` are used only to seed a new database.

After first initialization, persisted threshold values are authoritative until changed through facade/reset/migration.

Validation:

```text
heat_c < cool_c
```

## 8. Room targets

`initial_targets` seed only missing target keys.

They never overwrite a user-modified persisted target during normal restart/update.

Key:

```text
room_id × season × profile
```

Antifreeze target exists only for heating behavior.

## 9. Temperature devices

Common keys:

```yaml
- id: stable_device_id
  class: fast|slow
  entity_id: switch.foo|climate.foo
```

### 9.1 FAST switch

No additional target settings.

Desired state is room thermostat active/idle.

### 9.2 FAST climate

Required target policy:

```yaml
target_policy: passthrough
```

or:

```yaml
target_policy: fixed_active_target
active_heat_target_c: 30.0
active_cool_target_c: 18.0
```

`passthrough` means device target equals effective room target.

`fixed_active_target` is explicit target transformation and must never be invented by executor.

### 9.3 SLOW switch

```text
HEAT season -> on
other season -> off
```

### 9.4 SLOW climate

Requires:

```yaml
slow_target_c: 27.0
```

In HEAT App sets heat mode and this setpoint. The physical thermostat performs its local control loop.

SLOW target is independent from room air target.

## 10. Humidity control

Optional per room:

```yaml
humidity_control:
  type: humidifier|dehumidifier
  target_percent: 50
  hysteresis_percent: 3
  entity_id: ...
```

If absent or `type: none`, no room humidifier entity is published.

The percent hysteresis is intentionally separate from temperature hysteresis because the units are different.

Initial actuator domains:

- `humidifier`;
- `switch`.

Additional domains require an explicit adapter contract.

## 11. Unsupported self-reference

Config validation must reject use of DH Climate facade entities as its own raw sensors or actuators.

Examples of forbidden loops:

```text
room temperature source = climate entity published by same room
FAST actuator = room facade climate entity itself
outdoor source = season facade entity
```

## 12. Validation philosophy

Startup validation distinguishes:

### Fatal configuration error

Examples:

- duplicate room id;
- duplicate device id inside room;
- invalid class;
- `heat_c >= cool_c`;
- missing required SLOW target for climate device;
- unsupported entity domain declared as actuator.

App does not start control until fixed.

### Runtime degradation

Examples:

- source entity temporarily unavailable;
- physical actuator offline;
- MQTT temporarily disconnected.

App remains running, publishes problems, and applies fail-safe behavior.

## 13. Config evolution

After public release:

- room/device IDs are compatibility identifiers;
- renamed fields require migration/compatibility handling;
- user-persisted targets must not be reset by adding new config defaults;
- schema changes require migration tests.
