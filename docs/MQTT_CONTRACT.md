# DH Climate App — MQTT / Home Assistant contract

## 1. Goals

MQTT is the Home Assistant facade, not climate compute truth.

Requirements:

- stable unique IDs;
- retained discovery/state;
- non-retained commands;
- no retained command replay;
- minimal entity count;
- one MQTT Device per room;
- one global App device.

Recommended namespace:

```text
DigitalHouses/Global/dh_climate_app
```

## 2. Global device

Device:

```text
identifier: dh_climate_app
name: DH Climate
manufacturer: DigitalHouses
model: DH Climate App
sw_version: <APP_VERSION>
```

### 2.1 Season thermostat

Proposed identity:

```text
unique_id: dh_climate_season
object_id: dh_climate_season
domain: climate
```

Capabilities:

- `modes: [heat_cool]`;
- low target;
- high target;
- current temperature;
- current humidity when available;
- action;
- availability;
- JSON attributes.

State source:

- current temp = rolling outdoor avg24;
- action = season projection.

Commands:

- set low threshold;
- set high threshold.

HVAC mode command does not select season; `heat_cool` is facade mode.

### 2.2 Mandatory diagnostics

On global device:

```text
sensor.dh_climate_app_version
sensor.dh_climate_app_started_at
sensor.dh_climate_app_health
```

Semantics:

- Version: diagnostic;
- Started at: diagnostic + timestamp;
- Health: diagnostic, concise state with problem attributes.

No continuously changing uptime sensor is needed.

## 3. Room device

For room id `living_room`:

```text
identifier: dh_climate_room_living_room
name: DH Climate Living room
manufacturer: DigitalHouses
model: DH Climate Room
via_device: dh_climate_app   # use only if HA discovery support/behavior is suitable
```

Each room device can then be assigned by the user to a Home Assistant Area.

Room device identity is independent of Area assignment.

## 4. Room climate entity

Proposed identity:

```text
unique_id: dh_climate_living_room
object_id: dh_climate_living_room
domain: climate
```

State:

- current_temperature;
- target_temperature;
- hvac_mode;
- hvac_action;
- profile;
- attributes/reason;
- availability.

Commands:

- target temperature;
- room control mode on/off semantics;
- profile edit context if retained in final UI contract.

Allowed mode is constrained by global season:

```text
HEAT -> heat/off
COOL -> cool/off
OFF  -> off
```

Changing room target changes persisted room/profile target. It does not directly command a device.

## 5. Optional room humidity entity

Created only when configured.

Domain:

```text
humidifier
```

Contract:

- current humidity;
- target humidity;
- on/off;
- action/state attributes;
- device class indicates humidifier/dehumidifier semantics.

No duplicate room humidity sensor by default.

## 6. Entity minimization

Do not publish by default:

- source temperature sensor copies;
- source humidity sensor copies;
- heat-demand binary sensor if room `climate.hvac_action` already carries the same user information;
- cool-demand binary sensor for the same reason;
- per-room version/start sensors.

Add entities only when they provide a separate user/automation contract.

## 7. Topics

Logical form:

```text
DigitalHouses/Global/dh_climate_app/state/...
DigitalHouses/Global/dh_climate_app/command/...
DigitalHouses/Global/dh_climate_app/rooms/<room_id>/state/...
DigitalHouses/Global/dh_climate_app/rooms/<room_id>/command/...
```

Discovery:

```text
homeassistant/<domain>/<object_id>/config
```

Exact topic strings become compatibility interfaces at first release and must receive regression tests.

## 8. Retain policy

Retain:

- discovery config;
- availability;
- current facade state;
- version;
- started_at.

Do not retain:

- command topics.

On incoming MQTT command, App should also protect against retained/stale command delivery.

## 9. Availability

Global App availability reflects App/MQTT runtime.

Room climate availability additionally reflects whether required controlling room temperature fact is valid.

Humidity entity availability reflects whether configured humidity fact is valid.

A physical actuator being offline does not falsify room temperature; it creates a room/system problem and execution degradation.

## 10. Attributes

Attributes may expose concise explainability without creating more entities:

Room climate example:

```json
{
  "season": "heat",
  "effective_profile": "night",
  "reason": "below_target_minus_hysteresis",
  "temperature_source": "sensor.room_temperature",
  "fast_devices_active": 1,
  "slow_devices_active": 1
}
```

Never put credentials/tokens into MQTT payloads.

## 11. Recorder load

Design for low Recorder churn:

- publish state only on semantic change;
- do not republish unchanged JSON every second;
- version/start diagnostics are stable;
- source-level diagnostic details should prefer attributes and on-demand diagnostics over high-frequency entities.
