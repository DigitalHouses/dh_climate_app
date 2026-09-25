# DH Climate App — архитектура

**Статус:** проектная baseline-архитектура  
**Дата:** 2026-09-25  
**Репозиторий:** `DigitalHouses/dh_climate_app`

## 1. Назначение

DH Climate App — Home Assistant App для управления климатом дома по модели **room-as-thermostat**.

Пользователь управляет комнатой как климатической зоной. Физические радиаторы, конвекторы, тёплые полы, кондиционеры, увлажнители и осушители являются исполнительными устройствами комнаты и не должны становиться пользовательской моделью системы.

Новая реализация сохраняет бизнес-поведение DH Climate 5 на уровне контрактов, но не переносит PostgreSQL execution architecture.

## 2. Главный принцип миграции

Переносится:

- поведение room thermostat;
- profiles;
- season semantics;
- hysteresis semantics;
- target semantics;
- antifreeze semantics;
- outdoor provider priority/fallback;
- MQTT facade behavior;
- explainable `reason`;
- разделение room goal и device execution.

Не переносится:

- PostgreSQL как orchestration engine;
- job engine;
- handlers / database trigger routing;
- Matrix;
- Firewall;
- Dispatcher;
- UC command queue;
- Universal Controller;
- Confirmator;
- Supervisor;
- persistent command lifecycle;
- отдельные SQL read-model/view цепочки.

Иными словами:

```text
старый DH Climate 5:
HA -> Python IO -> PostgreSQL business engine -> jobs -> device pipeline -> HA/MQTT

новый DH Climate App:
HA state -> Python Core -> desired state -> HA services
                    |
                    +-> SQLite persistence
                    |
                    +-> MQTT Discovery facade
```

## 3. Архитектурные слои

```text
Home Assistant
  | REST snapshot / WebSocket state_changed
  v
HA Adapter
  |
  v
Observed Facts
  |- outdoor source facts
  |- room temperature/humidity facts
  |- profile-context facts
  |- actual actuator states
  |
  +--> Outdoor Selector --> Rolling 24h --> Season Controller
  |
  +--> Room Fact Selector/Aggregator
              |
              v
         Climate Core
         |- Profile Resolver
         |- Room Thermostat
         |- Humidity Controller
         |- FAST/SLOW Device Planner
              |
              v
        Desired Device State
              |
              v
        HA Executor/Reconciler
              |
              v
        physical devices

Climate Core / persistence
  |
  +--> MQTT Discovery + retained state
       |- global system/season device
       |- one MQTT Device per room
```

### 3.1 Правило причинности

Core определяет **что должно быть**. Executor определяет только **как выдать уже вычисленную команду**.

Executor не имеет права самостоятельно решать:

- нужен ли нагрев;
- какой сейчас сезон;
- какой профиль активен;
- какая целевая температура комнаты;
- является ли устройство FAST или SLOW;
- какая политика должна применяться при target reached.

Это сохраняет важный принцип старого DH Climate: decision logic не живёт в executor.

## 4. Configuration vs runtime state vs persistence

### 4.1 App configuration — installation contract

Конфигурация задаёт:

- внешние Home Assistant bindings;
- ordered source lists;
- rooms;
- global temperature hysteresis;
- device classes и bindings;
- SLOW target температуры;
- humidity contour type;
- исходные/default targets;
- safety/timing parameters, если они включены.

Конфигурация не является журналом runtime-состояния.

### 4.2 Python memory — current truth

В памяти живут:

- актуальный HA snapshot;
- выбранные outdoor sources;
- current room facts;
- rolling derived values;
- текущий season;
- effective profile;
- room decisions;
- desired actuator state;
- actual actuator state.

### 4.3 SQLite — continuity, а не orchestration

Файл:

```text
/data/dh_climate.db
```

SQLite хранит только то, что должно пережить рестарт:

- schema version;
- user-modified room targets;
- season thresholds, изменяемые через facade;
- outdoor samples, необходимые для rolling avg24;
- последнее room thermostat state для stateful hysteresis;
- humidity targets;
- last desired/applied actuator state, если требуется для безопасной reconciliation;
- timing/anti-cycle continuity state;
- problems/diagnostic state, если требуется;
- migration metadata.

SQLite **не содержит** job queue, dispatcher queue или execution workflow.

Режим:

- WAL;
- `synchronous=FULL`;
- foreign keys ON;
- migrations;
- integrity check при старте;
- данные только под `/data`.

## 5. Home Assistant connectivity

App использует Supervisor/Core proxy:

- `homeassistant_api: true`;
- `SUPERVISOR_TOKEN`;
- REST: `http://supervisor/core/api/`;
- WebSocket: `ws://supervisor/core/websocket`.

### 5.1 Startup / reconnect

Канонический порядок:

```text
connect WS
-> subscribe state_changed
-> start buffering events
-> fetch full current-state snapshot
-> build observed facts
-> replay only events received during snapshot
-> switch to live processing
```

Старые historical events не replay-ятся.

Правило:

```text
state is truth; events are hints
```

После reconnect App обязан заново получить полный snapshot прежде чем считать состояние достоверным.

## 6. Outdoor model

### 6.1 Sources

Temperature и humidity имеют независимые ordered source lists.

Для каждого источника поддерживается:

- numeric HA state;
- numeric entity attribute, включая weather-like entities.

Первый **валидный, available и не stale** источник в списке становится current source.

Temperature и humidity могут быть выбраны от разных providers.

### 6.2 Fallback

```text
source[0] valid -> use source[0]
source[0] invalid/stale -> source[1]
...
no valid source -> outdoor fact unavailable
```

Никаких скрытых `0`, fabricated values или silent fallback.

### 6.3 Rolling average

`avg_outdoor_24` рассчитывается как **time-weighted rolling average**, а не среднее по количеству HA событий.

Это намеренное улучшение старой PostgreSQL реализации, где использовался простой AVG по samples.

SQLite хранит минимальный sample horizon, достаточный для корректного восстановления 24h окна после restart.

## 7. Season controller

Внутреннее состояние:

```text
HEAT
COOL
OFF
UNKNOWN
```

`UNKNOWN` означает недостаточность/недостоверность outdoor data. Это не нормальное межсезонье.

Пользовательский facade:

```text
heat / cool / off
```

Season вычисляется по `avg_outdoor_24`.

Новый App использует **один глобальный temperature hysteresis из App config** как house-level параметр.

```text
avg24 < heat_threshold - hysteresis -> HEAT
avg24 > cool_threshold + hysteresis -> COOL
otherwise                           -> OFF
```

При `UNKNOWN` новые heating/cooling decisions блокируются и публикуется diagnostic problem.

### 7.1 Season thermostat facade

Глобальная MQTT `climate` entity:

- mode: `heat_cool`;
- `target_temp_low` = heat threshold;
- `target_temp_high` = cool threshold;
- `current_temperature` = avg24 outdoor temperature;
- `current_humidity` = avg24 outdoor humidity, если доступна;
- `hvac_action=heating` при HEAT;
- `hvac_action=cooling` при COOL;
- `hvac_action=idle` при OFF;
- unavailable/problem state при недостаточных данных.

Изменение low/high slider меняет persisted season thresholds, а не командует физическим оборудованием напрямую.

## 8. Profiles and room target model

Профили:

- `day`;
- `night`;
- `away`;
- `antifreeze`.

Effective profile:

```text
if season == HEAT and climate_control == off -> antifreeze
else if we_at_home != on                     -> away
else if night_mode == on                     -> night
else                                          -> day
```

Канонический room target:

```text
room × season × profile -> target_temperature
```

Изменение target пользователем через room thermostat означает:

> изменить target выбранного/активного профиля текущего сезона.

Это **не** прямая команда физическому climate device.

## 9. Room temperature thermostat

Каждая configured room — отдельный business thermostat.

State:

- current_temperature;
- target_temperature;
- season;
- effective_profile;
- climate_control;
- hvac_mode;
- hvac_action;
- reason.

### 9.1 Mode

Room не выбирает heat/cool самостоятельно.

```text
season HEAT -> room mode heat
season COOL -> room mode cool
season OFF  -> room mode off
```

### 9.2 Stateful hysteresis

HEAT:

```text
T <= target - h -> HEATING
T >= target + h -> IDLE
inside band      -> retain previous HEATING/IDLE
```

COOL:

```text
T >= target + h -> COOLING
T <= target - h -> IDLE
inside band      -> retain previous COOLING/IDLE
```

`h` — глобальный temperature hysteresis дома.

Missing/stale controlling temperature является hard inhibit для FAST room demand.

### 9.3 Antifreeze

`climate_control=off` в HEAT не означает полное отключение.

```text
HEAT + climate_control=off
-> effective_profile=antifreeze
-> antifreeze target remains active
```

В COOL/OFF выключенный room control не создаёт normal demand.

## 10. Humidity contour

Humidity control задаётся **на уровне комнаты**.

Тип:

- `humidifier`;
- `dehumidifier`.

Это не season-level setting.

Если humidity control в комнате не настроен:

- отдельная humidity control entity не создаётся;
- humidity может оставаться внутренним fact.

Если настроен:

- в MQTT Device комнаты появляется одна HA `humidifier` entity;
- она содержит current humidity;
- target humidity;
- action/state;
- для осушения используется соответствующий dehumidifier device class.

Отдельный дублирующий `sensor.*_humidity` по умолчанию не создаётся.

Humidity demand вычисляется Core, а executor только исполняет result.

## 11. Device classes

Минимально обязательные классы:

```text
FAST
SLOW
```

### 11.1 FAST

Примеры:

- радиатор;
- конвектор;
- быстро реагирующий electric heater;
- room AC/fast cooling device.

FAST полностью следует room thermostat demand.

HEAT:

```text
room hvac_action=heating -> FAST active
room hvac_action=idle    -> FAST inactive
```

COOL:

```text
room hvac_action=cooling -> FAST active
room hvac_action=idle    -> FAST inactive
```

Исполнитель может быть:

- `switch`;
- `climate`.

Для `climate` device planning должен явно определить mode и target policy. Executor не имеет права самостоятельно трансформировать target.

### 11.2 SLOW

Основной пример — тёплый пол.

SLOW — comfort contour, а не быстрый room-demand actuator.

#### SLOW switch

```text
season HEAT -> ON
otherwise   -> OFF
```

#### SLOW physical climate thermostat

Пример: настенный Aqara thermostat с floor/slab probe.

```text
season HEAT:
  set hvac_mode=heat
  set target = slow_target_temperature
  physical thermostat locally cycles heating by its own floor probe

season != HEAT:
  set off/safe mode
```

Важно:

```text
slow_target_temperature != room air target_temperature
```

Room target — температура воздуха. SLOW target для floor-probe thermostat — температура пола/стяжки.

SLOW не выключается только потому, что FAST room thermostat достиг room target.

## 12. Device Plan

Core формирует явный desired state для каждого actuator.

Минимальная структура:

```text
device_id
room_id
class: fast|slow
desired_enabled
desired_hvac_mode
desired_target_temperature
reason
generation
```

Для FAST climate device target policy должна быть explicit:

- `passthrough` — передать room target;
- `fixed_active_target` — использовать configured active target.

Никаких скрытых offsets в executor.

## 13. HA Executor / reconciliation

Executor поддерживает domain adapters.

Initial domains:

- `switch`;
- `climate`;
- `humidifier`.

Принцип:

```text
desired == actual -> no action
desired != actual -> issue HA service call
                  -> wait for fresh state
                  -> bounded retry if needed
```

Это лёгкая in-process reconciliation, а не восстановление старых Dispatcher/UC/Confirmator слоёв.

Commands должны быть idempotent.

Repeated normal loops не должны создавать command spam.

## 14. Failure policy

### 14.1 Invalid room temperature

- room FAST demand -> OFF;
- room thermostat facade -> unavailable/degraded;
- SLOW contour не зависит от room air demand, но продолжает подчиняться валидному global season.

### 14.2 Invalid outdoor temperature

- season -> UNKNOWN;
- новые FAST heat/cool demands blocked;
- SLOW не должен включаться без валидного HEAT season;
- problem публикуется явно.

### 14.3 HA WebSocket disconnect

- не считать старые observed facts свежими;
- reconnect выполняет полный snapshot;
- не выдавать новые control decisions из устаревшего snapshot.

Physical thermostats с локальным control loop сохраняют последнюю уже принятую локальную уставку до следующей достоверной reconciliation; App не изображает confirmation, которого не получил.

## 15. MQTT Device model

### 15.1 Global device

Один system device:

```text
identifier: dh_climate_app
name: DH Climate
```

На нём:

- season thermostat;
- version diagnostic;
- started-at diagnostic;
- system health/problems;
- только действительно необходимые global diagnostics.

### 15.2 Room devices

**Каждая комната — отдельный MQTT Device.**

Stable identifier:

```text
dh_climate_room_<room_id>
```

На устройстве комнаты:

- одна `climate` entity;
- optional одна `humidifier` entity.

Temperature/humidity source sensors не дублируются в room device по умолчанию.

Пользователь назначает найденное MQTT Device в нужную Home Assistant Area. App не должен зависеть от имени Area как от internal identity.

## 16. Entity minimization

Правило проекта:

> Не публиковать отдельную entity, если то же пользовательски значимое значение уже доступно внутри функциональной entity и отдельная entity не нужна для automation/diagnostics contract.

Особенно для room devices:

- current temperature живёт в `climate`;
- current humidity живёт в optional `humidifier`;
- source entity IDs остаются внутренними diagnostics/attributes, а не размножаются как HA entities.

## 17. Diagnostics

Обязательные runtime diagnostics на global device:

- Version;
- Started at;
- Health/Problems.

Version берётся из canonical App version.

Started at — ISO 8601 timestamp процесса, не continuously changing uptime sensor.

Problems должны описывать конкретный contract failure:

- no valid outdoor temperature source;
- no valid room temperature source;
- invalid threshold order;
- actuator unavailable;
- unsupported actuator mode;
- reconciliation failed.

## 18. Logging

Логи:

- человекочитаемые;
- без credentials/tokens;
- без spam на каждом неизменившемся sample;
- state transition и failure — loggable;
- normal no-op — debug/none.

Log не является business truth и не используется для управления.

## 19. Telemetry

Product telemetry не входит в critical climate path.

До включения production telemetry необходимо:

- определить canonical product identifier;
- добавить его в shared telemetry server allowlist;
- реализовать shared protocol v1;
- default `telemetry_enabled=false`;
- хранить identity только в `/data`;
- не отправлять entity IDs, configuration, device inventory или climate values.

Telemetry failure никогда не влияет на climate runtime.

## 20. Security

Новый App:

- не хранит HA long-lived token в repository/config;
- использует `SUPERVISOR_TOKEN`;
- получает MQTT credentials через Supervisor service;
- не содержит site IPs/credentials;
- не логирует secrets.

Старый repository используется как specification/evidence source, а не как источник credentials.

## 21. Неподдерживаемые функции первой реализации

Не входят без отдельного решения:

- TPI/PWM;
- proportional valve control;
- predictive/AI control;
- thermal model learning;
- weather forecast prediction;
- generic arbitrary-domain executor;
- старый SQL orchestration stack.

Архитектура оставляет для них extension points, но не строит инфраструктуру заранее.
