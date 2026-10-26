# GAP-анализ: текущая реализация 0.1.31 → целевая модель климатических комнат

**Статус:** архитектурный аудит (read-only по runtime, без изменения работающей Climate App).
**Цель:** [TARGET_ROOM_CLIMATE_MODEL.md](TARGET_ROOM_CLIMATE_MODEL.md).
**База сравнения:** исходники `main` релиза 0.1.31, tag `digitalhouses_climate_app-v0.1.31`, source `7df9daa3410e89ec70cedd08f149cbdce7470583`.
**Термин GAP:** функциональное несовпадение с целевой моделью; не означает автоматически баг в ранее согласованной модели v0.1.

## 1. Текущее состояние, которое сохраняем

- Home Assistant App с MQTT Discovery system/season/room, SQLite для durable state, season HEAT/COOL/OFF, night/away/antifreeze, наружный EMA/avg24, humidity, window inhibition.
- Прямой desired-state reconciliation для `switch`, `climate`, `humidifier` с bounded retry/cooldown, mismatch/drift и `VERIFIED_HA` (только HA).
- Реверсивный FAST climate с auto physical setpoint; для SmartIR прямое управление и оптимизация сервисных команд.
- `StartupActuatorGate` v0.1.31 защищает актуаторы при первоначальном появлении sensor truth; реальный рестарт HA 2026-10-26 показал `DEFER → READY` без ложного `bedroom_ac OFF`.
- LAB FAST HEAT, SLOW floor fixture, humidifier/dehumidifier и restore были проверены в рабочих сценариях. **Это не доказывает** все новые ROLE/CONTROL-пути или физическое переключение NO/NC клапана.
- Существующий `event.dh_climate_app_event` с problem transitions, climate binary Problem, machine event semantics QoS1/no retain; **не заменять новым event bus**.

## 2. Матрица GAP

| ID | Область | Что есть в 0.1.31 | Что требует TARGET | Приоритет |
| --- | --- | --- | --- | --- |
| G01 | Декларативная топология | Плоские `fast_heat`, `fast_cool`, `slow_heat`; в `DeviceConfig` нет `control` | Явный `role` + `entity` + `control: app/device` по каждому устройству | **P0** |
| G02 | SLOW-реле | `compile_room_devices` создаёт `hvac_mode=heat/off` для **любого** SLOW; у switch исполнитель сопоставляет только `power` | `slow_heat + switch + app` должен порождать `power` из логического OPEN/CLOSED | **P0 (дефект пути)** |
| G03 | Полярность клапана | Нет `actuator: normal_open/normal_closed`; нет valve-open abstraction | Тип термоэлектрического привода, явная инверсия и проверки, что `switch.on` означает питание | **P0** |
| G04 | SLOW без стяжки | `slow_target` обязателен для всякого `slow_heat`; не различается наличие датчика | Если floor sensor **не указан**, HEAT = OPEN постоянно, OFF/COOL = CLOSED, target не нужен | **P0** |
| G05 | SLOW + APP с датчиком | Нет per-device `temperature_sensor` стяжки и локальной SLOW температурной политики | Регулирование по стяжке, отдельный hysteresis и min ON/OFF | **P1** |
| G06 | SLOW деградация | При потере floor sensor нет описанного `OPEN + DEGRADED` | Явная потеря датчика → OPEN при HEAT, Problem и room health, восстановление | **P0 safety contract** |
| G07 | SLOW + DEVICE профили | Постоянный `slow_target` берётся из YAML | `slow_heat_day/night/away` из SQLite/MQTT, смена профиля передаёт новую температуру стяжки, без internal presets | **P1** |
| G08 | FAST + DEVICE | FAST независимо от автономности следует `room.control_action`, при room idle → HVAC OFF; `control=device` не существует | Автономный термостат получает сезонный режим и комнатный численный target; App не циклирует локальную работу | **P0** |
| G09 | FAST + APP | Есть комнатный гистерезис и `switch/climate` исполнитель, auto-bias для reversible `climate`; нет явного control flag | Сохранить прямую модель, явно отделить от `device`, не ломая SmartIR/AC | **P0 compatibility** |
| G10 | Гистерезисы | Один `temperature_hysteresis` управляет сезоном и температурой комнаты | Отдельные `fast_heat_hysteresis`, `fast_cool_hysteresis`, `slow_heat_hysteresis` и независимый сезонный гистерезис | **P1** |
| G11 | Выдержки SLOW | Нет `slow_heat_min_on_time/min_off_time` и durable времени переключения клапана | Seeds 5/5 минут; корректность через reconcile, рестарты и обход на safety | **P1** |
| G12 | Множественные устройства | FAST несколько entities уже возможны; одно reversible устройство объединяется в текущем parser | Mixed `APP/DEVICE` в комнате и одно physical reversible device без конкурирующих commands | **P1** |
| G13 | Room health FSM | Есть коллекция Problems, но нет retained status по комнатам и device-details health | `healthy/degraded/critical/unknown` по комнате, причина/устройство/fallback | **P1** |
| G14 | Global / climate health | Есть только aggregate `binary_sensor.dh_climate_app_problem`; наружный climate Problem уже есть, котлы/насосы нет | Разделённые `global_health` и климатический агрегат `health`, не house-wide smart-home health | **P1** |
| G15 | Room/global FSM Events | Есть `problem_started/recovered`; нет `room_health_changed`, `climate_health_changed` | Переходы именно комнатного и общеклиматического FSM; избежать дублирования | **P1** |
| G16 | Event payload | `schema_version=2` обязателен; `room_name` есть в window events, отсутствует в Problem events | Без поля версии; `room_id + room_name` во всех комнатных событиях; миграция потребителей | **P1 compatibility** |
| G17 | MQTT config entities | Есть room FAST heat/cool targets, humidity target и season thresholds | Отдельные SLOW profile targets, FAST/SLOW hysteresis и SLOW min timers с seed→SQLite→MQTT | **P1** |
| G18 | Конфигурация Supervisor | `config.yaml` принимает плоские room entries, не вложенный `devices` список | Выбрать представление target declarations с учётом ограничений Supervisor; безопасная migration из старого YAML | **P0 migration** |
| G19 | Startup/sensor-loss semantics | Стартовая задержка FAST зависит от первого outdoor+room-air; SLOW только от наружной температуры; после timeout — прежний fail-safe | Отличать device-local temperature, room-air и floor sensor, initial UNKNOWN и стабильную деградацию | **P1** |
| G20 | Уведомления | События уже машинные; локальный HA package формирует сообщения | Добавить маршрутизацию room/climate FSM events, отображение room_name, startup reconciliation | **P2 (HA local)** |
| G21 | Влажность | Реализован отдельный humidity controller; домены switch/humidifier, runtime target в SQLite | Сохранить как самостоятельную климатическую функцию комнаты и учитывать в room health; не ломать | **P1 regression** |
| G22 | Документация/acceptance | `HAOS_TEST_PLAN.md`, README и аудиты содержат исторические версии/acceptance | Документировать новый target, миграцию, результаты per-role E2E и обновить release gates | **P2** |

### Критичный технический GAP G02

В `src/dh_climate_app/devices.py::compile_room_devices` ветка `DeviceClass.SLOW` создаёт `DesiredDeviceState(hvac_mode=...)` независимо от `domain`. В `src/dh_climate_app/executor.py` сопоставление и отправка `switch` используют `desired.power`, а не `desired.hvac_mode`. Следовательно, путь для SLOW-реле не реализует нужную семантику «сезонный клапан»; при некоторых actual состояниях может считать OFF желаемым состоянием. Этот путь **не принимать** по тестам SLOW `climate`: отдельный unit + LAB + физический NO/NC E2E обязателен.

### Что уже покрывается существующим кодом без переписывания

1. HA client и state cache; MQTT Discovery, event bus, SQLite, Problem/Executor, bounded retries, logs и reconnect.
2. Профиль day/night/away и независимые FAST room targets уже существуют; изменится только конечный desired для `CONTROL=DEVICE`.
3. Отдельное удержание при room hysteresis уже реализовано, но его нельзя использовать для SLOW без уточнения таймеров и гистерезиса.
4. Реальная runtime semantics `VERIFIED_HA` и source-known vs unavailable сохраняется.
5. Глобальный `HEAT/COOL/OFF` и сезонный outdoor pipeline сохраняются.

## 3. Архитектурные инварианты миграции

- **Никаких автоматических команд реальным реле/кондиционерам при редактировании схемы.** Переход target → implementation делается новой версией с CI и тестовой конфигурацией.
- Старые `fast_heat/fast_cool/slow_heat` можно читать через временный совместимый parser, но **только при однозначной семантике**, с явным migration report; не угадывать `control` по домену для реальных устройств, когда это может поменять поведение.
- Сохранить стабильные `room_id`, MQTT unique IDs, existing setpoints и SQLite; не переименовывать установленные сущности косметически.
- Для `slow_heat + switch` запретить невалидные схемы без явно известного physical actuator type / wiring в целевом строгом режиме. Не считать `normal_open` / `normal_closed` автоматически доказательством контактов.
- Для `control=device` проверять capabilities (разрешённый режим, численный temperature target), факт sensor authority должен быть характеристикой реального термостата; `switch + device` — ошибка конфигурации.
- Нельзя трактовать `unavailable` как фактически OPEN/CLOSED или объявлять физическую безопасность на основании optimistic HA state.
- **Потеря наружного источника** и неизвестный сезон требуют явного решения по защите от замерзания; до утверждения не изменять текущую сезонную safety-модель молча.
- Seed `slow_heat_hysteresis=0.5 °C`, `slow_heat_min_on_time=5 min`, `slow_heat_min_off_time=5 min`; дополнительные параметры/targets seeded **только** при отсутствии persisted state. Разделить сезонный и температурные hysteresis при миграции.
- В проде не подключать новую схему к настоящему 32-канальному реле до отдельной read-only сверки mapping каналов и верификации ON→energized на стенде.

## 4. Последовательность реализации — без расширения климатических функций

| Фаза | Содержание | Gate |
| --- | --- | --- |
| A — Model / validation | Структуры Role/Control/Actuator, совместимый parser, строгий ownership, invalid-combination unit tests | Разбор старого и target config, **0 изменённых физических команд** |
| B — SLOW relay | Logical valve open/closed, NO/NC mapping, сезон, floor sensor present/absent | LAB и физический dry-run; отсутствие команд OFF в HEAT без датчика |
| C — SLOW regulator | Floor sensor, hysteresis, 5/5 min timers, durable state, loss→OPEN+DEGRADED | Е2Е потери/возврата датчика, safety override, restart |
| D — DEVICE mode | SLOW floor thermostat + FAST air thermostat, profile-based targets, idempotent reconciliation, capabilities | Night/away profile и season E2E, запрет вмешательства в локальную автоматику |
| E — Health & Events | Problems → room/global/climate retained FSM, versionless event contract, room_name, transition-only events | Unit/event tests, RECORDER no-churn, HA local notification package |
| F — Acceptance / docs | Полная регрессия LAB, no-restart regression, HAOS backup/restore, deployment audit | RELEASE gate отдельной новой версии |

Эти фазы **план**, не разрешение менять работающий код. Сначала матрица/тесты, затем поэтапная реализация.

## 5. Открытые решения, которые нельзя молча подменять

1. **Неизвестен глобальный HEAT/OFF сезон** при длительной потере наружного источника — что делать с сезонным SLOW клапаном, чтобы не заморозить трубы? Это отдельный safety decision, не тот же случай, что пропавший датчик стяжки.
2. **Минимальные времена ON/OFF после рестарта** без достоверного последнего физического switch time — уточнить сохранение/причины восстановления и безопасный приоритет действий.
3. **Единое представление reversible FAST** в Supervisor-constrained YAML, исключающее двойные команды одной entity.
4. **SLOW ROOM targets**: начальные Day/Night/Away значения стяжки и migration старого `slow_target` в профильную матрицу; пользователь их пока не утверждал.
5. **Глобальные weather/boiler/pump bindings**: статус относится к климатической инфраструктуре, но котёл и насосы не объявлены существующей реализацией; допуск новых диагностических входов отдельным решением.
6. **События без `schema_version`** меняют существующий контракт; прежде чем выпускать, найти и обновить всех известных потребителей `event.dh_climate_app_event`.

## 6. Источники анализа

- `dh_climate_app/config.yaml`
- `dh_climate_app/src/dh_climate_app/{config,core,rooms,devices,executor,persistence,humidity,problems,events,discovery,app}.py`
- `dh_climate_app/docs/{PRODUCT_CONFIGURATION_MANIFEST,ARCHITECTURE,EVENTS,STANDARDS_ALIGNMENT_AUDIT_2026-09-30}.md`
- `dh_climate_app/HAOS_TEST_PLAN.md`
- [DigitalHouses Application Standard](https://github.com/DigitalHouses/home-assistant-apps/blob/main/docs/standards/DIGITALHOUSES_APP_STANDARD.md)
- [DigitalHouses Contract Data Policy](https://github.com/DigitalHouses/home-assistant-apps/blob/main/docs/standards/CONTRACT_DATA_POLICY.md)
- [DigitalHouses Events & Notifications Standard](https://github.com/DigitalHouses/home-assistant-apps/blob/main/docs/standards/EVENTS_AND_NOTIFICATIONS_STANDARD.md)

**Результат аудита:** основной GAP находится не в новых features, а в классификации актуаторов, разделении `app/device`, корректной SLOW-релейной команде, контроле стяжки и наблюдаемости по комнатам.
