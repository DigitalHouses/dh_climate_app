# DigitalHouses Climate App — манифест продукта и конфигурации

**Версия:** 0.1  
**Дата:** 2026-09-30  
**Статус:** первая нормативная база  
**Область:** границы продукта, владение конфигурацией, контракт UI Home Assistant и тепловая модель FAST/SLOW.

Этот документ фиксирует продуктовые принципы дальнейшей разработки `dh_climate_app`. Он намеренно компактнее полной архитектурной спецификации. Здесь определяется **где должна находиться конфигурация и что должен видеть пользователь**, а не каждая деталь алгоритма управления.

Если детали реализации меняются, они должны сохранять этот контракт, пока сам манифест явно не пересмотрен.

---

## 1. Модель продукта

Пользовательская абстракция — **комнатный термостат**.

Комната владеет желаемой температурой воздуха и представлена одной нативной Home Assistant entity домена `climate`. Физические устройства являются исполнителями за этой абстракцией.

Основной тепловой путь:

```text
глобальный сезон
    ↓
эффективный профиль комнаты
    ↓
target комнаты
    ↓
stateful комнатный термостат
    ↓
demand устройств FAST
    ↓
device-specific desired state
    ↓
reconciliation через сервисы Home Assistant
```

SLOW heating идёт отдельным сезонным путём:

```text
глобальный сезон
    ↓
включение / выключение SLOW heating
    ↓
локальный физический термостат
```

Компактный App должен сохранять полезное климатическое поведение без воссоздания прежней PostgreSQL-оркестрации.

---

## 2. Владение конфигурацией

В системе три разных слоя конфигурации/состояния.

### 2.1 YAML/App options = топология установки

App options Home Assistant описывают **что установлено и к чему подключено**.

Типичные факты, которыми владеет YAML:

- bindings глобальных HA-фактов, например `night_mode` и `we_at_home`;
- bindings источников наружной температуры/влажности;
- идентификатор и отображаемое имя комнаты;
- bindings комнатных датчиков температуры/влажности;
- bindings оконных контактов;
- bindings исполнительных устройств FAST heating;
- bindings исполнительных устройств FAST cooling;
- bindings исполнительных устройств SLOW heating;
- исключительная аппаратная привязка/политика, которую нельзя безопасно определить из capabilities Home Assistant.

YAML не должен становиться базой оперативных параметров.

Нормальная запись комнаты должна оставаться примерно такой:

```yaml
rooms:
  - id: living_room
    name: Living Room
    temperature_sensors: sensor.living_room_temperature
    fast_heat: switch.living_room_convector
    fast_cool: climate.living_room_ac
    slow_heat: climate.living_room_floor
```

Опциональные bindings добавляются только если конкретная установка действительно их требует.

### 2.2 Сущности Home Assistant = изменяемая климатическая политика

Параметры, которые владелец/инсталлятор может менять после пусконаладки, должны публиковаться нативными сущностями Home Assistant, обычно через MQTT Discovery.

Используется нативный domain, соответствующий значению:

- `number` — числовые настройки;
- `select` — перечисляемые политики;
- `switch` — только настоящие boolean policy choices;
- `climate` — нормальная работа с комнатным термостатом;
- `sensor` / `binary_sensor` — состояние и диагностика.

Примеры изменяемых параметров:

- Heat Day / Night / Away targets;
- Heat Antifreeze target;
- Cool Day / Night / Away targets;
- SLOW heating target;
- offsets целевой температуры конкретного устройства;
- ограничения/политика вентилятора;
- будущая реакция на открытое окно;
- глобальный climate tuning, имеющий смысл для инсталлятора.

Для штатной пусконаладки и дальнейшей настройки этих параметров не должно требоваться редактирование YAML.

### 2.3 SQLite = сохраняемая истина

SQLite в `/data` хранит долговременное состояние App.

Для настроек, представленных MQTT configuration entities:

```text
HA command
→ валидация App
→ SQLite
→ пересчёт Climate Core
→ публикация MQTT state
```

После restart:

```text
SQLite
→ runtime App
→ retained MQTT state
→ UI Home Assistant
```

**SQLite имеет приоритет над retained MQTT command/state history.**

Retained MQTT — механизм транспорта и непрерывности UI, а не конкурирующий источник persistence.

---

## 3. Defaults и первое создание

Встроенные продуктовые defaults используются только при первичном создании отсутствующей настройки.

Пример:

```text
комната появилась впервые
→ настройки нет в SQLite
→ seed продуктового default
→ persist
→ публикация configuration entity в HA
```

После создания upgrade или reload конфигурации App не должны молча заменять сохранённую пользовательскую настройку новым default.

Новая настройка, появившаяся в следующей версии, может быть один раз seeded во время migration.

Defaults не должны повторяться в YAML каждой комнаты.

---

## 4. Контракт комнатного термостата

Каждая настроенная комната публикует одну основную MQTT entity `climate`.

Комнатный термостат — основной клиентский интерфейс.

Он содержит:

- текущую температуру комнаты;
- текущую влажность, если это полезно;
- текущий сезонно-допустимый target;
- HVAC modes, допустимые для сезона;
- HVAC action;
- обычную регулировку target.

Сезонные capabilities остаются нативными:

```text
HEAT → off / heat
COOL → off / cool
OFF  → off
```

Тепловые действия противоположного сезона запрещены.

Внутренние targets профилей Day / Night / Away остаются частью модели управления, но **не являются обычными клиентскими controls**.

Antifreeze — внутренний защитный профиль HEAT и не является обычным клиентским preset.

---

## 5. Тепловые устройства FAST

FAST означает достаточно малую тепловую инерцию, чтобы устройство участвовало в активном регулировании температуры комнаты.

Типичные примеры:

- радиатор;
- конвектор;
- fan-coil;
- кондиционер;
- другое быстро реагирующее комнатное отопительное/охлаждающее оборудование.

FAST следует demand комнатного термостата:

```text
room heating → FAST heat devices active
room cooling → FAST cool devices active
room idle/off → соответствующие FAST devices inactive
```

Demand определяет комнатный термостат. FAST device не должно самостоятельно превращать room temperature во второй конкурирующий алгоритм термостата.

Для smart `climate` исполнителей device-specific transformation может включать:

- target-temperature offset;
- нормализацию min/max/step;
- fan policy;
- mapping поддерживаемых режимов.

Это детали исполнения устройством, а не причина переносить room target в YAML.

---

## 6. Тепловые устройства SLOW

SLOW означает высокоинерционную систему отопления, которую в нормальном режиме не следует циклировать комнатным термостатом по температуре воздуха.

Основной пример — **водяной тёплый пол** со своим локальным термостатом/датчиком.

Каноническое поведение:

```text
season == HEAT  → SLOW heating enabled
season != HEAT  → SLOW heating disabled
```

Локальный SLOW `climate` thermostat получает собственный SLOW target. Физический локальный термостат выполняет реальное циклирование.

SLOW target отделён от room-air target.

Room hysteresis не должен постоянно включать/выключать SLOW heating.

Разделение FAST/SLOW описывает тепловое поведение, а не универсальный framework, который нужно преждевременно обобщать.

---

## 7. Граница TRV

TRV **не входят в core нового Climate App**.

Они не должны порождать дополнительные core device classes, специальную синхронизацию или PostgreSQL-era abstractions.

Если TRV нужны на конкретном объекте, ими следует управлять отдельно, например автоматизацией Home Assistant на основании глобального сезона HEAT.

Это решение можно пересмотреть только при наличии конкретного устройства/use case, который действительно оправдывает включение TRV в App.

---

## 8. Контракт клиентского UI

Клиентский UI комнаты должен намеренно оставаться минимальным.

Поверхность комнаты по умолчанию:

1. комнатный термостат;
2. только небольшое число дополнительных controls с понятным бытовым смыслом.

Возможные клиентские параметры:

- максимальная скорость вентилятора;
- реакция на открытое окно.

Параметр является клиентским только если он отвечает на понятный бытовой вопрос без знания внутренней архитектуры климатической системы.

Следующее **не является обычными клиентскими controls**:

- внутренние targets Heat Day / Night / Away;
- внутренние targets Cool Day / Night / Away;
- antifreeze target;
- hysteresis;
- EMA/filter parameters;
- device target offsets;
- инженерный SLOW target, если он специально не включён в продуктовый UX конкретного объекта;
- fan boost threshold;
- device capability mappings;
- низкоуровневые safety thresholds.

Пользователь в основном работает с термостатом. Автоматические профили остаются под капотом.

---

## 9. Контракт административного UI

Инженерные/системные параметры остаются доступны в Home Assistant для пусконаладки, отладки и обслуживания.

Они отображаются на отдельном dashboard **DH Climate Admin**.

Configuration entities обычно должны иметь:

```text
entity_category = config
```

и принадлежать наиболее подходящему MQTT Device:

- system-wide setting → системный Device DigitalHouses Climate;
- room setting → MQTT Device комнаты;
- device-specific setting → Device соответствующей комнаты, пока более сильная модель устройства реально не понадобится.

Admin dashboard должен собираться максимально автоматически, например через Auto-Entities, чтобы появление новых configuration entities не требовало ручного изменения dashboard.

Не следует добавлять metadata только ради построения сложного UI framework. Сначала использовать нативные свойства Home Assistant и добавлять лишь минимальную стабильную metadata при доказанной необходимости фильтрации/сортировки.

---

## 10. Metadata для обнаружения сущностей в UI

Начальное правило:

- нативное владение Home Assistant Device;
- нативный `entity_category: config`;
- стабильные DigitalHouses entity IDs / unique IDs.

Если client/admin filtering нельзя надёжно выразить нативными metadata Home Assistant, добавляется **один минимальный стабильный UI classification attribute**, а не большая presentation schema.

Возможный будущий атрибут:

```text
dh_climate_ui = client | admin
```

Не добавлять section/order/device metadata, пока реализация dashboard не покажет реальную необходимость.

---

## 11. Дисциплина Recorder

Operational configuration entities не являются высокочастотной телеметрией.

Time-series sensor entities должны оставаться компактными и не создавать динамический attribute churn.

Configuration metadata может содержать небольшое число стабильных attributes, если это нужно для UI discovery, поскольку эти сущности не предназначены для высокочастотных измерений.

Не прикреплять к configuration entities быстро меняющиеся diagnostic payloads.

---

## 12. Capabilities устройств

App должен использовать capabilities сущностей Home Assistant там, где они надёжны, включая:

- supported HVAC modes;
- min/max target temperature;
- target temperature step;
- supported fan modes.

Не дублировать обнаруживаемые capabilities в YAML без доказанной необходимости совместимости.

Hardware-specific overrides допустимы, если Home Assistant не может надёжно предоставить требуемую истину.

---

## 13. Политика окна

Window state — контекст устройства, а не truth комнатного термостата.

Открытие окна не должно переписывать room target или придумывать другое thermostat state.

Конкретное устройство может быть inhibited явной window policy.

Точная клиентская настройка реакции на окно пока остаётся продуктовым вопросом. Исходный принцип:

- внутренняя policy настраиваема;
- клиенту, если вообще нужно, показывается только простая понятная реакция;
- детальная policy остаётся на стороне Admin.

---

## 14. Политика вентилятора

Точный динамический fan algorithm этим манифестом пока не фиксируется.

Текущее направление:

```text
ошибка температуры комнаты
→ requested fan level
→ ограничение максимума по profile/client
→ mapping на fan modes устройства
→ desired device command
```

Большая температурная ошибка может запрашивать maximum fan, но Night или client maximum могут ограничить результат.

Итоговая policy должна оставаться компактной и не создавать повторяющиеся per-room YAML fields.

---

## 15. Преобразование device target

Room target и target физического устройства — разные понятия.

Пример:

```text
room target = 24 °C
device cool offset = -3 °C
→ raw device target = 21 °C
```

После этого device target нормализуется по физическим capabilities устройства.

Target offsets относятся к commissioning/device settings и обычно должны редактироваться через HA configuration entities и сохраняться в SQLite, а не повторяться как operational YAML values.

---

## 16. Безопасность и нерешённый HEAT fallback

В HEAT season действует защитное требование: здание не должно замёрзнуть только потому, что обычное комнатное управление отключено.

Однако потеря достоверной room temperature не должна приводить к небезопасной безусловной команде ON для простого actuator.

Точная fail-safe policy при отсутствии room temperature намеренно оставлена открытой и должна зависеть от control authority/capability исполнителя.

Примеры, которые нужно отдельно рассмотреть:

- локальное thermostatic `climate` device с собственной валидной регулировкой;
- простой binary relay без независимой температурной защиты;
- fallback room sensor;
- отдельно настроенный safety thermostat.

Этот вопрос должен быть явно решён до признания HEAT fail-safe завершённым.

---

## 17. Обобщённая модель логического устройства

Существующий архитектурный документ исследует будущие свойства:

- roles;
- inertia;
- control source;
- control profile;
- scope;
- equipment ID.

Эти концепции могут пригодиться для будущей вентиляции или сложных объектов, но **не являются требованием текущего thermal App**.

Текущая реализация должна предпочитать минимальную модель, которая правильно выражает:

```text
FAST heat
FAST cool
SLOW heat
```

Не вводить generic device framework только потому, что его можно спроектировать.

---

## 18. Явные non-goals

Через этот рефактор не должны вернуться:

- PostgreSQL как business engine;
- SQL job orchestration;
- Matrix/Firewall/Dispatcher/UC/Confirmator как буквальные runtime layers;
- per-room YAML-копии operational targets;
- TRV-specific core complexity;
- UI, показывающий клиенту каждый внутренний параметр;
- конкурирующие sources of truth между YAML, MQTT retained state и SQLite;
- generic abstraction layers без доказанного текущего use case.

---

## 19. Сводка владения

| Область | Владелец |
| --- | --- |
| Привязка физических сущностей | App YAML/options |
| Привязка room sensors | App YAML/options |
| Принадлежность FAST/SLOW | App YAML/options |
| Day/Night/Away/Antifreeze targets | SQLite + HA config entities |
| SLOW target | SQLite + HA config entity |
| Device target offset | SQLite + HA config entity |
| Fan tuning/policy | SQLite + HA config entities |
| Работа с room thermostat target | HA climate facade → SQLite |
| Persistent runtime truth | SQLite |
| MQTT retained state | непрерывность UI/transport |
| Client dashboard | thermostat + минимальные понятные controls |
| Admin dashboard | полные commissioning/system controls |

---

## 20. Правило изменения

Перед добавлением нового поля в YAML нужно ответить:

> Описывает ли это поле **что физически установлено или как оно привязано к Home Assistant**?

Если нет — обычно это должна быть persisted Home Assistant configuration entity.

Перед добавлением новой клиентской entity нужно ответить:

> Отвечает ли этот control на обычный бытовой вопрос без раскрытия деталей реализации?

Если нет — он относится к Admin UI.

Эти два теста являются базовой защитой от разрастания конфигурации и UI.
