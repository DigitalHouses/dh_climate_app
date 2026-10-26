# Передача в реализацию: новая матрица DH Climate App без автоматической миграции YAML

**Решение:** согласовано 2026-10-27.
**Статус:** NEXT IMPLEMENTATION / пока не реализовано.
**Текущая установленная версия для сравнения:** 0.1.31; текущий runtime и действующие options не изменяются этим решением.

## 1. Принятый способ перехода

**Автоматической миграции Supervisor YAML/options из 0.1.31 в новую модель не будет.** Инсталлятор сознательно заменит старый конфиг **целиком** на новый подготовленный YAML и запустит новую версию App. Не вводить два независимых runtime-контракта «старый/новый» ради legacy YAML. Это экспериментальная версия, и здесь выбран ручной контролируемый переход.

Это **не означает**:
- удаление или повторную инициализацию `/data` и SQLite;
- сброс сезонных порогов, комнатных Day/Night/Away/Antifreeze уставок, влажности и хранимых runtime настроек;
- обнуление Recorder / MQTT entity unique IDs, slug, привязок Area или восстановлений после рестарта;
- отказ от **аддитивного обновления схемы самой SQLite**, необходимого для новых persisted-настроек;
- разрешение запускать новую несовместимую схему, пока реальные актуаторы подключены, без preflight.

**ВАЖНО:** Supervisor хранит options и может сверять их с новой schema *ещё до запуска App*. Нельзя слепо менять `config.yaml` и надеяться, что Python-parser распознает старые строки. Последовательность upgrade/полной ручной замены YAML нужно проверить на стенде и оформить одним точным runbook для этой версии.

## 2. Что разрабатываем в новом чате

См. [TARGET_ROOM_CLIMATE_MODEL.md](TARGET_ROOM_CLIMATE_MODEL.md) и [TARGET_ROOM_CLIMATE_GAP.md](TARGET_ROOM_CLIMATE_GAP.md). Это источник истины предметной модели. Сначала свериться с текущими исходниками, чтобы не переписывать работающие части.

### Supervisor GUI и options

- Сохранить основной GUI-список **«Комнаты» → «Изменить» → всё оборудование комнаты**, без второго пользовательского списка `devices`.
- В целевом YAML все множественные поля — настоящие YAML-списки, **в том числе из одного элемента**: `rooms[].temperature_sensors`, `humidity_sensors`, `window_sensors`, `rooms[].devices`, `outdoor.temperature_sources`, `outdoor.humidity_sources`.
- Каждый device описывается как `entity`, `role` (`slow_heat`/`fast_heat`/`fast_cool`), `control` (`app`/`device`), опциональные `actuator: normal_open|normal_closed`, `temperature_sensor` (датчик стяжки SLOW APP), применимые безопасности/окна.
- Отдельный GUI-раздел **Outdoor**, с упорядоченными fallback-цепочками `sensor.*` и `weather.*` для температуры и отдельно для влажности. Нынешнюю приоритетную механику и EMA/avg24 сохранить.
- Отдельно оставить лишь **ключевые установочные bindings / опции** (ночной флаг, признак присутствия, уровень логирования и т.п.). Никаких оперативных уставок и hysteresis/min-timers в Supervisor YAML.
- [SUPERVISOR_NESTED_SCHEMA_PROBE.md](SUPERVISOR_NESTED_SCHEMA_PROBE.md): isolated test Supervisor 2026.10.4 **PASS** для nested lists и UI schema. **Реальная GUI-проверка render/edit/save/reopen на HAOS ещё не пройдена** и обязательна до релиза.

### Матрица температурных устройств

| ROLE | CONTROL | Техническая сущность | Поведение |
| --- | --- | --- | --- |
| `slow_heat` | `app` | `switch.*`, без стяжечного sensor | Всё время сезона HEAT логический клапан OPEN; другой сезон CLOSED |
| `slow_heat` | `app` | `switch.*`, со стяжечным sensor | Регулирование по стяжке, SLOW hysteresis и min ON/OFF; потеря sensor в HEAT → OPEN + DEGRADED |
| `slow_heat` | `device` | `climate.*`, внутренний датчик стяжки | App дирижирует heat/off и численной уставкой стяжки, локальный термостат регулирует сам |
| `fast_heat` / `fast_cool` | `app` | `switch.*` либо `climate.*` | App регулирует по датчику воздуха HA; рабочий SmartIR/AC — прямой FAST, не автономный thermostat |
| `fast_heat` / `fast_cool` | `device` | `climate.*` с собственным датчиком воздуха | App устанавливает сезонный mode и **численную** цель Day/Night/Away и контролирует соответствие; не трогает внутренние profiles/PWM |

- `slow_heat` — только комфорт тёплого пола, **не** отопление воздуха. Релейный сезонный SLOW без датчика **не требует** температуры стяжки или target.
- `actuator: normal_open|normal_closed` — физический тип **сервопривода**, не контакт реле. Проверить mapping energized→OPEN/CLOSED на стенде.
- Для SLOW APP с датчиком: глобальные SQLite/MQTT seeds `slow_heat_hysteresis=0.5 °C`, `slow_heat_min_on_time=5 min`, `slow_heat_min_off_time=5 min`. Safety override вне таймеров.
- Глобальные FAST HEAT и FAST COOL hysteresis отдельные от SLOW и от сезонного hysteresis.
- Профили SLOW стяжки — **отдельные** от профилей комнатного FAST воздуха. Day/Night/Away цели стяжки — SQLite/MQTT, не YAML.
- Несколько устройств одного типа в комнате допускаются; один реверсивный `climate` имеет один actuator owner и **единственный** итоговый desired state.

### Outdoor continuity и health/events

- При **полной потере** наружных источников после того, как в системе уже была валидная температура, продолжать по последнему достоверному значению / последнему рассчитанному сезону, global/climate FSM → `degraded`. Сохранять значение, timestamp, источник, season в SQLite, не выдавать кэш за свежие данные и не добавлять фиктивные EMA/avg24 samples.
- Failover по очереди источников; восстановление live-источника снимает конкретную Problem. Первый запуск без baseline — `unknown`, не сочинять температуру.
- `health` — **климат всей системы дома**, а не статус умного дома: room/device facts → room FSM, global outdoor/boiler/pumps (по мере реальной поддержки) → общий climate FSM. `healthy/degraded/critical/unknown`.
- Retained state + transient `event.dh_climate_app_event`: `problem_started/problem_recovered`, `room_health_changed`, `climate_health_changed`. Во всех room events обязательны `room_id` + **`room_name`**. Event payload без `schema_version` по целевому контракту; проверить изменение контрактов у потребителей.
- Машиночитаемый факт выпускает App; человеческий текст/emoji/уведомление делает локальный HA package (Events & Notifications Standard DigitalHouses), не второй event bus.
- Никаких transient FSM events для обычных переключений реле/гистерезиса.

## 3. Данные, не подлежащие потере

Перед обновлением прочитать **фактические** Supervisor options установленной версии, snapshot SQLite/backup App и текущие MQTT room targets. Предыдущий пример YAML в TARGET — **иллюстрация**, а не готовая конфигурация для реального дома.

Известные room IDs из UI последней установки:
- `livingroom` (real, увлажнитель `switch.socket_humidifier`);
- `bedroom` (real, `climate.bedroom_ac` использовался FAST HEAT/COOL по действующей конфигурации, точный target control проверить);
- `lab_cool`, `lab_heat`, `lab_humidifier`, `lab_dehumidifier`, `lab_ventilation` (LAB rooms).
Их **точные bindings надо извлечь из живого options**, не угадывать по имени и не скрывать реальные устройства за LAB.

`slow_target` старого формата — YAML уставка стяжки, не hardware binding. В новом YAML её **нет**. Сохранять новые persisted SLOW уставки в SQLite; при ручном переходе прочитать действующее `slow_target` и использовать в seed только **при отсутствии persisted SLOW targets**. Конкретные новые Day/Night/Away defaults не были отдельно утверждены: старые значения не перезаписывать, новые не придумывать молча.

`/data` / SQLite сохраняется; можно эволюционно добавлять таблицы/настройки. Не делать разрушительную миграцию схемы БД и не сбрасывать пользовательские targets.

## 4. Протокол разработки и релиза

1. **Только read-only preflight**: проверить HEAD, действующие options/schema, `config.py`, `devices.py`, `executor.py`, `rooms.py`, `persistence.py`, `discovery.py`, `events.py`, `problems.py`, существующие unit/LAB tests. Зафиксировать список сохранённых room IDs и actuator ownership.
2. На отдельной git branch реализовать **единый** новый options contract, валидацию, компилятор `role/control`, NO/NC, SLOW sensorless/sensored, DEVICE reconciliation. Не выпускать production upgrade, пока не покрыты все варианты новой YAML-схемы.
3. Persist/MQTT numbers (новые global hyst/min times и SLOW профильные targets) c seed только по отсутствию; health FSM, events, outdoor last-known. Не ломать humidity, FAST SmartIR startup gate, window inhibition.
4. Unit / static tests всей матрицы + negative validation, SQLite preservation, startup/offline/restart, idempotency, actuator conflicts. **Сначала LAB без реальных команд** и включения физических клапанов.
5. Отдельный безвредный Supervisor GUI smoke: `rooms[].temperature_sensors[]`, `rooms[].devices[]`, `outdoor.*_sources[]`; реальный render → edit → save → reopen. Изменение options тестового App не должно менять options `8d59ce70_dh_climate_app`.
6. Подготовить **готовый полный YAML** на основании actual options и явных новых control/actuator bindings; пользователь вставляет его вручную. Перед любым обновлением production App дать проверенный **точный порядок** остановки App, резервного копирования, обновления binaries/schema, полной замены options, валидации и запуска. Отдельно проверить риск того, что Supervisor отклонит старые сохранённые options до замены.
7. Только после CI PASS и разрешения пользователя — release новой экспериментальной версии, controlled update и live acceptance. Наблюдать Logs, problem events, комнатные/общеклиматические FSM; проверять физическое положение реле только при отдельно разрешённом E2E. **Terminal остаётся открытым для логов**.

Ключевой gate: **manual options replacement — допустима; слепой запуск неверных options или сброс SQLite — нет**.

## 5. Что не делаем

Не расширяем функциональность CO₂/вентиляции/памп, не начинаем новый UI dashboard, не добавляем стороннюю оркестрацию, не переписываем уже работающий outdoor/season/EMA/Humidity/Recorder без функционального GAP. Не переключаем реальный кондиционер для тестирования нового пути без согласованного безопасного сценария.

## 6. Ссылки

- [Модель TARGET](TARGET_ROOM_CLIMATE_MODEL.md)
- [GAP 0.1.31 → TARGET](TARGET_ROOM_CLIMATE_GAP.md)
- [Проверка Supervisor GUI schema](SUPERVISOR_NESTED_SCHEMA_PROBE.md)
- [Текущий план HAOS тестов](../HAOS_TEST_PLAN.md)
- [Существующий runbook обновления experimental](EXPERIMENTAL_UPDATE_RUNBOOK.md)
- [DigitalHouses Home Assistant Apps Standards](https://github.com/DigitalHouses/home-assistant-apps/tree/main/docs/standards)

**Этот документ фиксирует следующий инженерный этап. Ни config.yaml, ни исходники управления, ни версия установленного 0.1.31 не менялись.**
