# Climate App machine events

## Purpose

DigitalHouses Climate App exposes one Home Assistant MQTT Event entity:

```text
event.dh_climate_app_event
```

It is the single public transition stream for the App. Current facts remain in
retained climate/sensor/binary-sensor state.

## Transport contract

```text
schema_version: 2
QoS: 1
retain: false
```

Every payload contains:

```text
schema_version
event_type
observed_at
```

Additional fields are specific to each `event_type`.

The producer publishes machine data only. Notification language, title,
message, emoji and delivery destination belong to the local Home Assistant
package.

## Ordering

When a calculation changes retained current state and also creates an Event:

```text
1. calculate truth
2. publish retained state
3. publish retained Problem state
4. emit transient machine Event
```

This guarantees that an automation triggered by the Event can read current
entities and see the same truth represented by the Event.

## Baseline / reconnect rule

Startup and Home Assistant reconnect establish a new baseline and emit no
transition Event.

Events that happened while the App or Home Assistant was unavailable are not
reconstructed. If recovery logic is needed, it must read retained current
state separately.

## Event catalog

### season_changed

Emitted when global season changes between `heat`, `cool` and `off`.

Fields:

```text
previous_season
current_season
avg_24h_temperature
current_temperature
heat_threshold
cool_threshold
hysteresis
```

### precipitation_started

Dry/non-precipitating condition becomes rain, snow, mixed precipitation or
hail.

Fields:

```text
previous_type
current_type
condition
precipitation_mm
forecast_at
source_entity
```

`precipitation_mm` is the normalized amount from the current hourly forecast
bucket, not a physical rain-gauge measurement.

### precipitation_stopped

Active precipitation becomes a normal non-precipitating condition.

Uses the same weather fields.

### precipitation_type_changed

Active precipitation changes class, for example:

```text
rain -> snow
snow -> rain
rain -> mixed
mixed -> snow
```

Uses the same weather fields.

### window_opened / window_closed

Fields:

```text
room_id
room_name
previous_state
current_state
season
```

Unknown window truth is not duplicated here. It is represented by
`problem_started` / `problem_recovered` with
`problem_code=room_window_state_unknown`.

### problem_started / problem_recovered

Generic transition contract for App-owned Problems.

Fields are the machine Problem identity/context:

```text
code
scope
severity
room_id      (when applicable)
entity_id    (when applicable)
details      (when applicable)
```

This keeps the Event contract extensible when new actuator or sensor Problem
codes are added.

## What is deliberately not an Event

Normal thermostat hysteresis cycles are state, not events:

```text
heating -> idle -> heating
cooling -> idle -> cooling
```

Humidity controller cycling and FAST/SLOW reconciliation are also not Events
unless a future product requirement defines a semantic transition worth
notifying about.

A new event type must satisfy all of these:

1. something meaningful happened, rather than a value merely being current;
2. the same fact is not already emitted as another event type;
3. the payload has a documented machine schema;
4. Discovery `event_types`, tests and this document are updated together.

## Local notification pattern

The intended Home Assistant path is:

```text
event.dh_climate_app_event
-> event.received trigger
-> trigger.id
-> choose
-> direct local action
```

The public App does not depend on any local notification service.
