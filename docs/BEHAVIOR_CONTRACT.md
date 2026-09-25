# DH Climate App — behavior contract

**Цель:** зафиксировать пользовательское поведение, которое должно пережить переход с DH Climate 5 на компактный Home Assistant App.

Это behavior contract. Он не требует совпадения внутреннего кода со старым проектом.

## 1. Что считается совместимостью

Совместимость означает:

- тот же смысл room thermostat;
- тот же смысл season thermostat;
- те же profile/target semantics;
- те же `hvac_action` semantics;
- тот же смысл antifreeze;
- понятные причины решений;
- predictable UI behavior.

Не требуется:

- одинаковая SQL schema;
- одинаковые workers;
- одинаковые MQTT topics старого PG проекта;
- старый job pipeline;
- старые diagnostic entities.

Новая реализация может быть существенно проще.

## 2. Season thermostat

Facade contract:

```text
domain: climate
mode: heat_cool
target_temp_low: heating season threshold
target_temp_high: cooling season threshold
current_temperature: rolling outdoor avg24
current_humidity: rolling outdoor avg24 humidity when available
```

Action:

```text
HEAT -> heating
COOL -> cooling
OFF  -> idle
```

Threshold change modifies season settings only.

## 3. Outdoor source contract

Temperature and humidity are independent.

Each has an ordered provider list.

Selection:

1. inspect sources in config order;
2. reject unavailable/unknown/non-numeric/stale source;
3. first valid source wins;
4. if current source becomes invalid, next valid source takes over;
5. return to higher-priority source when it becomes valid again.

No fabricated fallback values.

## 4. Room thermostat facade

Required user-visible fields:

- current temperature;
- target temperature;
- hvac mode;
- hvac action;
- active/effective profile;
- explanation/reason as attributes when useful.

Room `hvac_mode` follows season; it is not an independent heat/cool selector.

## 5. Profiles

Canonical profiles:

```text
day
night
away
antifreeze
```

Resolution:

```text
HEAT + room control off -> antifreeze
else not at home        -> away
else night mode         -> night
else                    -> day
```

Changing `night_mode` or `we_at_home` changes effective profile. It does not rewrite stored target temperatures.

## 6. Target edit semantics

If user changes target on room climate entity:

```text
room = living_room
season = HEAT
selected/effective profile = night
new target = 23
```

then the persisted value changed is:

```text
living_room × HEAT × night -> 23
```

This is not a direct device setpoint command.

After target changes, Core recomputes room decision and Device Plan.

## 7. Stateful temperature hysteresis

Global house hysteresis is configured once.

HEAT:

```text
<= target-h -> heating
>= target+h -> idle
inside band -> keep previous heating/idle
```

COOL:

```text
>= target+h -> cooling
<= target-h -> idle
inside band -> keep previous cooling/idle
```

This state must survive App restart sufficiently to prevent an arbitrary state flip inside the band.

## 8. Antifreeze

Room OFF in HEAT means:

```text
normal room control disabled
effective profile = antifreeze
antifreeze target remains active
```

Room OFF in COOL/OFF means no normal room demand.

Antifreeze must be visible/explainable through state attributes/reason; it must not be hidden UI-only behavior.

## 9. FAST behavior

FAST device participates only while room thermostat requests active heating/cooling.

```text
HEAT + heating -> FAST active
HEAT + idle    -> FAST inactive
COOL + cooling -> FAST active
COOL + idle    -> FAST inactive
```

Room target reached therefore stops FAST output.

## 10. SLOW behavior

SLOW is independent of room air demand.

SLOW switch:

```text
HEAT -> on
not HEAT -> off
```

SLOW climate thermostat with local floor probe:

```text
HEAT:
  mode=heat
  target=slow target
  local thermostat controls relay from floor probe

not HEAT:
  off/safe
```

SLOW target is its own value. It is not automatically equal to room air target.

## 11. Humidity behavior

Per room, contour is exactly one of:

```text
none
humidifier
dehumidifier
```

It is not derived from outdoor season.

A configured contour exposes one functional HA humidifier entity with current and target humidity.

No duplicate room humidity sensor is required by default.

## 12. Facade is projection, not truth

MQTT entities display Core state.

They do not calculate:

- season;
- room demand;
- active profile;
- device participation;
- target reached.

MQTT command handlers translate user edits into Core state changes and trigger recalculation.

## 13. Applied vs confirmed

When App issues a Home Assistant service call, this means only:

> command was issued.

It does not mean:

- physical device changed;
- relay actually closed;
- target was achieved.

Confirmation comes only from a later fresh HA state observation.

## 14. Deliberate differences from old PostgreSQL implementation

New App deliberately changes:

1. PostgreSQL removed; Python Core owns business semantics.
2. Outdoor avg24 is time-weighted instead of sample-count AVG.
3. Each room is a separate MQTT Device, assignable to a Home Assistant Area.
4. Room entity surface is minimal: no duplicate temperature/humidity sensors by default.
5. Device bindings live in App config and App performs direct HA execution.
6. FAST/SLOW are first-class behavior classes.
7. SLOW floor target is explicitly separated from room air target.
8. One global temperature hysteresis is the house-level configuration parameter.

These are product decisions, not implementation accidents.

## 15. Legacy behavior not carried forward automatically

The following old behavior requires an explicit new product decision before implementation:

- device-specific window policies;
- generic fan-mode transforms;
- arbitrary device target offsets;
- Matrix/Firewall restrictions;
- old selected-profile temporary UI overlay timeout;
- old command retry lifecycle;
- old SCADA entity inventory.

No legacy feature is kept merely because SQL/code for it exists.
