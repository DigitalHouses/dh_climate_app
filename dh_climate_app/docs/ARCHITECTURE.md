# DH Climate App — архитектура v0.1

**Статус:** базовая реализация  
**Дата:** 2026-09-25  
**Источник поведения:** текущие продуктовые решения + PostgreSQL-реализация `DigitalHouses/dh_climate_1`.

## 1. Цель

`dh_climate_app` — приложение Home Assistant, которое владеет климатическими решениями для дома и публикует нативные сущности Home Assistant через MQTT Discovery.

Новый App сохраняет полезное **поведение** DH Climate 5, а не его PostgreSQL-реализацию.

```text
Состояния Home Assistant
        ↓
входной адаптер HA
        ↓
Climate Core
 ├─ Outdoor / avg24 / season
 ├─ Room thermostat
 ├─ Humidity controller
 └─ Device policy (FAST / SLOW)
        ↓
Desired device state
        ↓
HA service executor
        ↓
climate / switch / humidifier devices

Climate Core
        ↓
MQTT Discovery facade
        ↓
Home Assistant UI
```

PostgreSQL, SQL jobs, Dispatcher, Matrix, UC queue, Confirmator и Supervisor не переносятся.

## 2. Архитектурные правила

1. **Бизнес-логикой владеет Python.** SQL никогда не является движком выполнения бизнес-правил.
2. **State — истина, events — подсказки.** HA events запускают пересчёт, но reconnect всегда начинается с актуального snapshot состояний.
3. **Идемпотентное выполнение.** App рассчитывает desired state и отправляет HA service command только если actual state отличается.
4. **Минимальное число HA entities.** Значения, уже представленные функциональной entity, не дублируются отдельными room sensors.
5. **Одна комната = один MQTT Device.** Каждая комната получает стабильный MQTT device identifier и может быть назначена пользователем соответствующей Home Assistant Area.
6. **Один глобальный season.** Комнаты не выбирают HEAT/COOL независимо.
7. **Один общий температурный hysteresis дома.** Компактный App намеренно объединяет legacy-настройки room/outdoor hysteresis в одно настроенное значение.
8. **Persistent configuration отделена от runtime settings.**
   - App options задают bindings внешних HA entities и device topology.
   - Изменяемые пользователем targets термостатов и thresholds сезона являются runtime state и сохраняются в `/data`.
9. **В исходном коде нет site-specific entity names.** Все HA bindings задаются конфигурацией.
10. **Только machine events.** Если позже появятся notifications, App публикует машинные события; текстом и доставкой владеет локальный HA.

## 3. Входные данные

### 3.1 Глобальные HA-факты

Опциональные глобальные входы профилей:

- `night_mode`
- `we_at_home`

Сохраняется legacy-приоритет effective profile:

```text
HEAT + climate control OFF → antifreeze
иначе not at home          → away
иначе night mode           → night
иначе                      → day
```

### 3.2 Наружные источники

Конфигурация App содержит два независимых упорядоченных списка:

- `outdoor_temperature_sources`;
- `outdoor_humidity_sources`.

В каждом списке выбирается первая текущая валидная numeric entity. Поэтому temperature и humidity переключаются на fallback независимо.

`unknown`, `unavailable`, пустые и non-numeric states считаются невалидными и приводят к переходу к следующему источнику.

Для live season control требуется температура. Если все live sources наружной температуры unavailable, App принудительно переводит season в `OFF`, даже если исторический avg24 ещё существует.

### 3.3 Комнатные sensors

Для каждой комнаты можно определить один или несколько:

- temperature sensors;
- humidity sensors;
- опциональных window contact sensors.

Window contacts агрегируются по legacy-семантике: любой open contact имеет приоритет; если открытых нет, но хотя бы один contact unavailable/unknown, state комнаты становится `unknown`; иначе — `closed`. Window state является device context и не меняет room `hvac_action`.

Для room temperature/humidity сохраняется legacy-поведение: используется среднее последних валидных показаний всех настроенных доступных sensors соответствующего типа.

Если валидной room temperature нет, FAST thermostat demand блокируется, а facade комнатного термостата становится unavailable.

## 4. Расчёт наружной температуры

App использует единый pipeline нормализации температуры:

```text
prioritized source
→ выбранная RAW temperature
→ EMA low-pass filter
→ публичная filtered outdoor temperature
→ persisted samples с шагом одна минута
→ rolling 24-hour arithmetic mean
→ season
```

Постоянная времени EMA задаётся через `outdoor_temperature_ema_minutes` (по умолчанию 20 минут). EMA продвигается не чаще одного раза в минуту.

Failover provider/sensor не имеет отдельного режима smoothing: ступень при смене source проходит через ту же EMA, что и обычное изменение температуры. Внутреннее RAW value доступно немедленно для hard safety, logging и events, а его diagnostic MQTT sensor публикуется не чаще одного раза в минуту, чтобы ограничить Recorder churn.

Temperature `avg_outdoor_24` — арифметическое среднее persisted минутных filtered samples внутри rolling 24-hour window. Равномерный sample cadence не позволяет частоте обновления provider менять вес samples. Минутная history хранится в SQLite и переживает restart App. Legacy pre-EMA temperature history один раз мигрируется путём повторного пропуска через ту же EMA. Наружная humidity сохраняет существующий time-weighted rolling average.

Глобальный season:

```text
avg24 < heat_threshold - hysteresis → HEAT
avg24 > cool_threshold + hysteresis → COOL
otherwise                           → OFF
```

`OFF` — межсезонье.

Season facade повторяет поведение DH Climate 5:

- Home Assistant domain: `climate`;
- mode: `heat_cool`;
- current temperature: `avg_outdoor_24`;
- current humidity: rolling 24h humidity, когда доступна;
- lower target: threshold отопительного сезона;
- upper target: threshold сезона охлаждения;
- action:
  - HEAT → `heating`
  - COOL → `cooling`
  - OFF → `idle`

Оба threshold sliders изменяемы и сохраняются.

## 5. Комнатный термостат

Каждая настроенная комната публикует одну MQTT `climate` entity.

Комнатный термостат содержит:

- current room temperature;
- target room temperature;
- HVAC mode, определяемый глобальным season;
- HVAC action, определяемый room demand;
- profile с тем же пользовательским смыслом, что и в legacy DH Climate.

Публикуемый список capabilities MQTT Climate следует глобальному season:

```text
HEAT → off, heat
COOL → off, cool
OFF  → off
```

**Текущее HVAC state** следует тому же season contract:

```text
HEAT → heat
COOL → cool
OFF  → off
```

Команды противоположного season отклоняются runtime App.

Во время обработки Discovery update Home Assistant сбрасывает MQTT Climate `preset_mode` в `none`. Чтобы сохранить authoritative profile `day/night/away`, App использует season-scoped preset state topic (`.../climate/profile/heat|cool|off`). Retained preset публикуется до season-specific Discovery payload. Поскольку preset state topic меняется, Home Assistant переподписывается и сразу получает retained value.

Матрица targets:

```text
room × season × profile → target temperature
```

Нативные Home Assistant Climate presets:

- `day`
- `night`
- `away`

Home Assistant MQTT Climate также публикует зарезервированный preset `none`. В App выбор `none` означает «очистить временный profile-edit overlay и вернуться к автоматически effective profile».

`antifreeze` — внутренний защитный профиль HEAT и никогда не публикуется как user-selectable preset.

Изменение target temperature на room thermostat обновляет выбранный edit-overlay profile или automatically effective profile, если overlay отсутствует. Edit overlay истекает после idle timeout и не меняет автоматический source presence/night profile.

### 5.1 Stateful hysteresis термостата

Новый App использует настоящий stateful симметричный hysteresis.

HEAT:

```text
T <= target - h → heating
T >= target + h → idle
inside band      → сохранить предыдущее heating/idle state
```

COOL:

```text
T >= target + h → cooling
T <= target - h → idle
inside band      → сохранить предыдущее cooling/idle state
```

Это состояние сохраняется, поэтому restart App не схлопывает hysteresis band.

## 6. Модель MQTT Device комнаты

Каждая комната — отдельный MQTT Device.

Стабильный identifier:

```text
dh_climate_app_room_<room_id>
```

Пример:

```text
dh_climate_app_room_living_room
```

После Discovery пользователь назначает Device соответствующей Home Assistant Area.

Default entities room device намеренно минимальны:

1. `climate` — room thermostat.
2. опциональный `humidifier` — только если настроен humidity control.

Не создаются дублирующие room `sensor.temperature` или `sensor.humidity` только ради повторения значений, уже видимых в функциональных entities.

## 7. Управление влажностью

Humidity control опционален для каждой комнаты.

Room configuration выбирает ровно один controller type:

```text
humidifier
dehumidifier
```

Entity публикуется в Home Assistant domain `humidifier`.

- humidifier: обычный humidifier device class/behavior;
- dehumidifier: `device_class: dehumidifier`.

Entity содержит:

- current humidity;
- target humidity.

Если humidity control не настроен, соответствующая entity не публикуется.

Humidity control независим от season HEAT/COOL.

Для humidity controller используется отдельный глобальный humidity hysteresis, потому что %RH и °C не могут использовать один numeric deadband.

## 8. Классы устройств

Room actuator configuration вводит два тепловых класса.

### 8.1 FAST

Примеры:

- радиатор;
- конвектор;
- fan-coil;
- кондиционер.

FAST devices следуют demand комнатного термостата.

```text
room heating → настроенные FAST heat devices active
room cooling → настроенные FAST cool devices active
room idle/off → FAST devices inactive
```

Поддерживаемые HA execution domains в первой реализации:

- `switch`;
- `climate`.

Для FAST climate device App задаёт требуемый HVAC mode и room target temperature. Для FAST switch используются `turn_on` / `turn_off`.

### 8.2 SLOW

Основной случай: тёплый пол с собственным локальным физическим thermostat и floor probe.

SLOW devices **не** следуют циклам room thermostat.

```text
season HEAT → SLOW device enabled
season COOL/OFF → SLOW device disabled
```

Для SLOW `climate` device:

```text
HEAT:
  hvac_mode = heat
  target_temperature = slow target configured for that device
```

После этого локальный физический thermostat сам циклирует heating по собственному probe.

SLOW target намеренно отделён от room air target. Floor probe измеряет floor/screed temperature, а не температуру воздуха комнаты.

Обычный SLOW `switch` в v0.1 запрещён. SLOW control требует локальный HA `climate` thermostat, чтобы физический floor/slab probe оставался финальным локальным контуром safety и cycling.

### 8.3 Окна и cold-weather safety

Legacy-ограничения Firewall/Matrix представлены напрямую как deterministic device policy, а не отдельные subsystems.

Window behavior:

```text
room thermostat action остаётся неизменным
+
room window is open
+
device находится в window_off_devices
→ desired state этого device = off
```

Так сохраняется legacy-правило: окно — контекст применимости device, а не input thermostat demand.

Cold-weather protection reversible climate:

```text
FAST climate entity находится и в fast_heat, и в fast_cool
+
room requests heating
+
RAW selected outdoor temperature < ac_min_outdoor_temperature
→ reversible climate device = off
```

Default threshold — `-10 °C`, как в legacy PostgreSQL setting. Другие heat sources остаются независимо доступными.

### 8.4 Целевая модель логического устройства (план)

Текущая конфигурация v0.1 сохраняет реализованные FAST/SLOW lists. Следующая модель описана как возможное направление будущего device-policy refactor, чтобы вентиляцию, humidity и более сложное оборудование можно было добавлять без изменения базовой control architecture.

Логическое управляемое устройство описывается независимыми свойствами:

```text
DEVICE
├─ roles
├─ inertia
├─ control_source
├─ control_profile
├─ scope
└─ equipment_id (optional)
```

Эти свойства отвечают на разные вопросы и не должны схлопываться в один device type.

**roles** описывают, что логическое device может делать для climate control, а не то, как Home Assistant его публикует. Начальный словарь roles:

```text
heat
cool
ventilation_supply
ventilation_exhaust
humidify
dehumidify
```

Одно логическое device может иметь несколько roles. Поэтому reversible climate unit — одно device с `roles: [heat, cool]`, а не два конкурирующих logical owners одной HA entity.

**inertia** описывает характер отклика device:

```text
fast
medium
slow
```

Она намеренно независима от role и control source. Например, slow heating device и fast heating device могут иметь одну role `heat`, но требовать разного control behavior.

**control_source** определяет controller/demand source, управляющий device. Это не сам raw sensor. Возможные источники:

```text
season
room_thermostat
co2
humidity
```

Примеры:

- underfloor heating может следовать `season` и оставаться enabled весь HEAT, пока собственный local thermostat выполняет physical cycling;
- air conditioner может следовать `room_thermostat` и реагировать на room heating/cooling/idle demand;
- supply/exhaust ventilation может следовать CO₂ controller;
- humidifiers/dehumidifiers могут следовать humidity controller.

Controller преобразует sensor facts в normalized demand. Devices не должны независимо переинтерпретировать raw CO₂, humidity или room-temperature measurements.

**control_profile** описывает только то, как App сообщает requested state HA entity: упорядоченные наборы команд, зависимости между commands и verification requirements. Он не описывает thermal role, inertia или control source device.

Первое generic имя profile:

```text
control_standart
```

Profile можно переиспользовать для разных devices, если их HA command sequence одинаков. Например, cooling air conditioner и heating heat pump могут использовать `control_standart`.

Control Profile может компилировать один desired state в упорядоченный Command Plan, например:

```text
activate:
  1. set_hvac_mode
  2. set_temperature
  3. set_fan_mode (when required)

deactivate:
  1. set_hvac_mode(off)
```

Другой profile может требовать:

```text
activate:
  1. power_on
  2. wait/verify power
  3. set_hvac_mode
  4. set_temperature
  5. set_fan_mode
```

Общий Executor должен выполнять plan; порядок команд не должен быть глобально hard-coded.

**scope** описывает, где действует logical device:

```text
room
house
```

Это позволяет room-level и house-level ventilation использовать один execution mechanism.

**equipment_id** опционально группирует несколько logical HA control endpoints, принадлежащих одной физической установке. Принцип:

```text
one HA entity = one logical controllable device
multiple logical devices may belong to one physical equipment
```

Пример supply-air installation:

```text
equipment_id: supply_ahu

fan.supply
  roles: [ventilation_supply]
  scope: house

climate.supply_reheat
  roles: [heat]
  scope: house
```

Room supply damper может оставаться отдельным logical device:

```text
valve.livingroom_supply
  roles: [ventilation_supply]
  scope: room
  room_id: livingroom
```

Будущий CO₂ controller сможет координировать house supply/exhaust devices и room dampers, при этом каждый physical endpoint сохранит собственные command execution, verification и Problem state.

Этот раздел описывает только модель. Он не добавляет ventilation, CO₂ control, room dampers или новую nested Supervisor configuration в текущую реализацию v0.1.

## 9. Binding capabilities устройств

Каждый настроенный actuator объявляет свои возможности.

Внешняя App configuration намеренно проще внутренней модели:

```text
fast_heat = comma-separated switch/climate entities
fast_cool = comma-separated switch/climate entities
slow_heat = comma-separated climate entities
slow_target = one floor/comfort target for SLOW thermostats in the room
window_sensors = comma-separated binary_sensor entities
window_off_devices = thermal actuators to inhibit while a window is open
```

Если одна и та же `climate` entity находится в обоих FAST lists, внутренняя модель компилирует её как `heat_cool`. `switch` может присутствовать только в одном thermal list. У одной entity может быть только один owner во всей конфигурации.

## 10. Persistence

SQLite используется только как lightweight persistent state:

```text
/data/dh_climate.db
```

SQLite **не** является orchestration engine.

Хранятся только данные, которые должны переживать restart:

- schema version;
- season heat/cool thresholds;
- rolling outdoor samples для avg24;
- room target matrix;
- humidity targets;
- previous room thermostat action для stateful hysteresis;
- последний selected profile overlay, только если нужен для continuity facade;
- компактный execution/retry state при необходимости;
- metadata состояния продукта.

Не хранятся:

- jobs;
- handlers;
- dispatcher tables;
- UC command queue;
- SQL procedures;
- SQL business rules.

## 11. Модель подключения к HA

Используется внутренний Home Assistant API Supervisor.

Порядок startup/reconnect:

```text
1. connect HA WebSocket
2. subscribe to state_changed
3. buffer relevant events
4. read current snapshot of every configured entity
5. apply snapshot
6. replay only buffered events newer than the snapshot boundary
7. enter live event processing
8. calculate all climate state
9. reconcile physical devices
10. publish MQTT facade
```

Исторические HA events никогда не replay.

Периодический lightweight runtime tick поддерживает active control reconciliation. У outdoor EMA отдельная минимальная cadence одна минута; более частые recalculations не могут продвинуть EMA или создать более частые temperature samples.

## 12. Модель выполнения

Новый App напрямую управляет настроенными devices через Home Assistant services.

Отдельной универсальной подсистемы на замену старому Universal Controller нет.

Вместо этого каждый actuator имеет компактный lifecycle reconcile/verification:

```text
desired state
vs
current HA state
→ equal: установить/сохранить stable baseline
→ different: отправить требуемые HA service call(s)
→ SENT
→ post-command state_changed запускает settle window
→ delayed state check
→ matching state: VERIFIED_HA
→ persistent mismatch/no event: bounded retry
```

Успешный Home Assistant service call означает только принятие команды и никогда не считается device confirmation. После установления stable state более поздний `state_changed` actuator, уходящий от всё ещё актуального desired state, создаёт drift candidate и проверяется после settle delay до corrective execution.

Так сохраняется надёжность без воссоздания PostgreSQL command lifecycle.

### 12.1 Целевая модель Command Plan и verification (план)

Control Profiles должны компилировать desired device state в упорядоченный Command Plan из одного или нескольких steps.

Полезная legacy-идея сохраняется на уровне поведения: один desired state может требовать нескольких последовательных HA service calls. Старая реализация PostgreSQL/UC не переносится.

Plan может определять, требует ли отдельный step verification до перехода к следующему. Простые devices могут отправить несколько идемпотентных service calls и проверить только финальный desired state; devices с ordering/timing constraints могут требовать settled state перед продолжением.

Целевой lifecycle:

```text
DESIRED_CHANGED
→ PLAN_CREATED
→ STEP_SENT
→ state_changed / settle delay / step verification when required
→ NEXT_STEP
→ FINAL_VERIFY
→ PLAN_VERIFIED_HA
```

Команда никогда не считается физически подтверждённой только потому, что HA service call успешен. Успешный service result означает лишь, что Home Assistant принял вызов.

Verification event-oriented:

- релевантный HA `state_changed` может запланировать delayed state check;
- settle delay не позволяет считать мгновенный optimistic echo финальным доказательством;
- watchdog deadline покрывает случай, когда state event не пришёл;
- после verification plan более поздний state transition от всё ещё актуального desired state становится drift candidate и проверяется после settle delay;
- если desired state меняется во время выполнения plan, старый plan superseded, его pending checks становятся obsolete.

`PLAN_VERIFIED_HA` намеренно означает только, что после verification delay Home Assistant всё ещё сообщает desired state. Это не доказательство физической работы. Независимое physical evidence может быть добавлено будущим profile, если оно доступно.

## 13. MQTT topology

System device:

```text
identifier: dh_climate_app
name: DigitalHouses Climate
```

System device владеет:

- season `climate` facade;
- действительно полезным outdoor current/avg24 state;
- global problems/health;
- diagnostic Version;
- diagnostic Started at.

Room devices:

```text
dh_climate_app_room_<room_id>
```

Каждый room device владеет только функциональными room-facing entities.

MQTT Discovery и current state retained. Transient machine events не retained.

## 14. Сохранённое legacy-поведение

Из `DigitalHouses/dh_climate_1` сохранены:

- priority/fallback наружных sources;
- outdoor current + 24h derived concept;
- глобальный `HEAT / COOL / OFF`;
- сезонный thermostat `heat_cool` с двумя sliders;
- абстракция room-as-thermostat;
- room target matrix по season/profile;
- `day/night/away/antifreeze`;
- ограниченные сезоном room HVAC modes;
- редактирование profile через thermostat facade;
- normalization temperature/humidity;
- semantics fallback/unavailable;
- aggregation room windows и per-device inhibition при open window;
- защита reversible climate heating при низкой наружной температуре;
- концепции MQTT Discovery facade.

## 15. Legacy-архитектура, намеренно удалённая

Не переносится:

- PostgreSQL как business engine;
- append-only SQL runtime architecture;
- system job queue;
- handlers;
- Matrix;
- Firewall как отдельный engine;
- Dispatcher;
- UC queue;
- Universal Controller;
- Confirmator;
- UC Supervisor;
- SQL component status;
- SQL runtime sessions;
- PostgreSQL-specific system facade diagnostics.

Эквивалентное полезное поведение реализуется напрямую в Python там, где оно действительно требуется.

## 16. Модули реализации

Целевая структура Python:

```text
src/dh_climate_app/
├── app.py
├── config.py
├── core.py
├── persistence.py
├── ha_client.py
├── outdoor.py
├── rooms.py
├── humidity.py
├── devices.py
├── executor.py
├── mqtt.py
├── discovery.py
├── telemetry.py
└── problems.py
```

Направление зависимостей:

```text
config / models
      ↓
pure core
      ↓
domain services
      ↓
HA + MQTT adapters
      ↓
app runtime
```

`core.py` должен оставаться тестируемым без Home Assistant, MQTT и SQLite.

## 17. Первый implementation slice

Первый executable slice намеренно вертикальный:

```text
configured outdoor sources
→ priority selection
→ rolling avg24
→ season
→ season facade

configured room temperature sensors
→ room temperature
→ profile/target
→ thermostat action
→ FAST/SLOW desired state
```

Эти детерминированные правила уже подключены к Home Assistant WebSocket/REST adapters, MQTT facade и прямому device reconciliation. Оставшийся release gate — реальное integration testing HAOS на настроенных entities.
