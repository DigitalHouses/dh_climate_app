# DH Climate 5 → DH Climate App migration matrix

Status: architecture audit  
Legacy source: `DigitalHouses/dh_climate_1`  
New source: `DigitalHouses/dh_climate_app`

The migration rule is **behavioral compatibility at the Home Assistant boundary**, not source-code or database compatibility.

## Architectural mapping

| Legacy PostgreSQL Climate 5 | New Climate App | Decision |
| --- | --- | --- |
| PostgreSQL business engine | Python domain core | Replace |
| `t_system_settings` business/UI settings | App options + small SQLite runtime state | Simplify |
| append-only room/outdoor truth tables | current HA state cache + only required rolling/persistent state | Simplify |
| system jobs | direct event-driven recomputation | Remove |
| handlers | Python domain methods | Replace |
| Matrix | deterministic device-policy compiler | Replace |
| Firewall | explicit device safety predicates | Replace |
| Decision plan/history | desired device state | Replace |
| Dispatcher | direct reconcile loop | Replace |
| UC command queue | bounded idempotent service calls | Remove |
| Universal Controller | `DeviceExecutor` | Replace |
| Confirmator | HA state reconciliation + retry/cooldown | Replace |
| UC Supervisor | runtime health + Problem diagnostic | Replace |
| SQL runtime sessions/component status | Version / Started at / Problem | Simplify |
| PostgreSQL admin/business procedures | App configuration + native HA controls | Remove |
| HA MQTT facade workers | MQTT Discovery facade | Preserve behavior |

## Outdoor contour

| Legacy behavior | New implementation |
| --- | --- |
| provider priority | ordered `outdoor_temperature_sources` / `outdoor_humidity_sources` |
| temperature/humidity selection | independent first-valid-source selection |
| current outdoor truth | selected live source |
| avg24 | time-weighted rolling 24h stored in SQLite |
| season | `HEAT / COOL / OFF` |
| season thresholds | persisted lower/upper targets |
| outdoor thermostat | MQTT `climate` `heat_cool` facade |
| source unavailable | fallback; if all live temperature sources fail, force season OFF |

The new App intentionally makes the rolling average time-weighted so sensor update frequency cannot bias the result.

## Room contour

| Legacy behavior | New implementation |
| --- | --- |
| latest values from enabled room sensors | latest HA state of configured sensors |
| room temperature | mean of currently valid configured temperature sensors |
| room humidity | mean of currently valid configured humidity sensors |
| global season constrains room mode | retained |
| day/night/away/antifreeze | retained |
| room target by season/profile | retained in SQLite |
| HEAT + room off → internal antifreeze | retained |
| COOL + room off → true off | retained |
| profile-edit overlay | retained with idle timeout |
| thermostat facade | one MQTT `climate` entity per room |
| all rooms under one legacy device | changed: one MQTT Device per room for HA Area assignment |

## Hysteresis

Legacy storage contained separate room and outdoor hysteresis settings. Current product decision intentionally replaces them with one house-wide temperature hysteresis.

Room thermostat behavior is stateful and symmetric:

```text
HEAT
T <= target - h  -> heating
T >= target + h  -> idle
inside band       -> keep previous state

COOL
T >= target + h  -> cooling
T <= target - h  -> idle
inside band       -> keep previous state
```

The previous room action is persisted so restart does not collapse the deadband state.

## Window context

Legacy room window truth:

```text
any configured contact open             -> open
else any configured contact unavailable -> unknown
otherwise                                -> closed
```

Legacy Matrix applied device-type window policies. The new App keeps the useful `turn_off` behavior without a Matrix subsystem:

```text
room window=open
+ actuator listed in window_off_devices
-> actuator desired state=off
```

Window state does not rewrite room thermostat demand.

## Device execution

### FAST

Legacy Matrix/Decision/Dispatcher/UC selection and command lifecycle becomes:

```text
room action
-> device function match
-> safety predicates
-> desired state
-> compare with actual HA state
-> service call only when different
```

Supported domains: `switch`, `climate`.

A climate entity present in both `fast_heat` and `fast_cool` is a reversible heat/cool device.

### SLOW

The new product requirement adds an explicit high-inertia class.

SLOW v0.1 accepts only local physical `climate` thermostats:

```text
HEAT -> mode=heat, target=slow_target
COOL/OFF -> mode=off
```

The local thermostat and its own floor/slab probe remain the final cycling and safety loop. SLOW does not follow room-air thermostat cycling.

## Cold-weather AC heating protection

Legacy Firewall prohibited AC heating below `ac_min_outdoor_temperature`, default `-10 °C`.

New mapping:

- reversible FAST `climate` = same entity in both `fast_heat` and `fast_cool`;
- during heating, if live outdoor temperature is below `ac_min_outdoor_temperature`, that device is held off;
- other eligible heat sources are unaffected.

## Humidity

Humidity control in the new App is intentionally simpler and native to HA:

- optional per room;
- `humidifier` or `dehumidifier`;
- native MQTT `humidifier` facade;
- persisted target;
- separate RH hysteresis;
- direct `switch` or `humidifier` actuator execution.

## Persistence boundary

SQLite stores only state that must survive restart:

- season thresholds;
- rolling outdoor samples;
- room target matrix;
- room climate enable state;
- previous room HVAC action;
- humidity target/control state.

It does **not** contain jobs, dispatcher queues, command lifecycle tables, Matrix candidates, Firewall results, SQL procedures, or business orchestration.

## Reliability mapping

| Legacy mechanism | New mechanism |
| --- | --- |
| event/job append chain | HA websocket state events |
| current SQL views | timestamp-protected state cache |
| UC retries | bounded executor retry |
| Confirmator | desired-vs-actual reconciliation |
| Supervisor | reconnect loop + Problem diagnostic |
| runtime session reconstruction | fresh HA snapshot after reconnect |
| historical command replay | explicitly not performed |

Reconnect invariant:

```text
subscribe first
-> obtain current snapshot
-> reject older buffered events by timestamp
-> resume decisions
```

## HA facade compatibility boundary

The migration is accepted when the same user intent produces equivalent externally meaningful behavior:

```text
season thresholds
room target/profile
room on/off
room temperature response
device eligibility
window safety
cold-weather safety
humidity target
```

Internal SQL table shape, worker count and command-history topology are explicitly **not** compatibility requirements.

## Deliberate non-ports

The following legacy infrastructure must not reappear unless a future requirement proves a concrete need:

- PostgreSQL orchestration;
- Matrix as a subsystem;
- Firewall as a subsystem;
- Dispatcher;
- UC queue;
- Universal Controller lifecycle;
- Confirmator lifecycle;
- SQL jobs/handlers;
- runtime session tables;
- append-only operational history for every state transition.

The compact App should add complexity only where it protects a defined user-visible behavior or safety invariant.
