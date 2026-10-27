# DH Climate App · ручной переход на TARGET · рабочий runbook

**Версия 0.1.32 готовится к пользовательским испытаниям через штатный магазин Home Assistant.** Полная HAOS-приёмка ещё не выполнена. Перед обновлением штатный backup App с `/data` и исходный YAML обязательны. Последняя известная установленная версия — `0.1.31`, slug `8d59ce70_dh_climate_app`.

## 1. Что реализовано в изолированной ветке

- Только одна новая модель Supervisor options. Существующие строковые `fast_heat/fast_cool/slow_heat`, `slow_target`, CSV-датчики и глобальные operational settings **не принимаются** новым runtime.
- Настоящие списки `rooms[].temperature_sensors[]`, `humidity_sensors[]`, `window_sensors[]`, `rooms[].devices[]` и отдельно `outdoor.temperature_sources[]` / `humidity_sources[]`.
- Один `devices[]` на комнату; `role`, `control`, физический `actuator` обязательный для SLOW-реле, опциональный датчик стяжки. Реверсивный `climate`: **одна** запись с `role: fast_heat` и `reversible: true`; никакого второго конкурирующего heat/cool ownership.
- SLOW `switch` регистрирует логическое состояние клапана и физическое питание NO/NC; SLOW `climate + device` получает численную профильную уставку; FAST `device` не циклирует по room idle; FAST `app` сохраняет прямое управление, в том числе SmartIR.
- SQLite `global_tuning`, `slow_room_targets`, `slow_valve_runtime` созданы расширением без удаления прежних таблиц. SLOW числа **не придумываются**: при отсутствии seed такой контур не вводится в нормальный температурный режим.
- Outdoor last-known сохраняет достоверный сезон и timestamp; отсутствие всех live-источников не создаёт новых минутных EMA samples. Stale-маркер отражается в Problems/health.
- Retained room/global/climate health, MQTT Numbers для global tuning и SLOW профилей, существующий единый MQTT Event с machine-only событийной моделью.

## 2. Непреодолённые gates

1. Реальный **read-only** экспорт сохранённых options из конкретной рабочей установки, версий Supervisor, App и HAOS. Не принимать иллюстративный YAML из TARGET за конфигурацию объекта.
2. Подтверждение всех физически подключённых `actuator` NO/NC и mapping ON→energized, каждого `control=app/device`, способностей `climate`, наличия датчиков стяжки, запрета пересекающихся owners. Для LAB и реальных помещений составить точную сравнительную таблицу old→new.
3. Test App с другим slug и **без** доступа к реальным HVAC, MQTT актуаторам: Supervisor `render → edit → save → reopen`, вложенные повторяемые поля, порядок источников, ошибка валидации, русский UI.
4. На test App доказать поведение Supervisor при **несовместимости ранее сохранённых options с новой schema**. Не считать, что `ha apps update` автоматически или безопасно мигрирует прежние значения. Последовательность stop/update/options/start должна быть измерена, а не угадана.
5. Исчерпывающая приёмка HAOS/CI и симуляция NO/NC/SLOW датчиков с недоступными сенсорами, без реального оборудования; отдельно согласовать live acceptance.
6. Проверить downstream потребителей machine Event: убрано поле `schema_version`; для room events обязательно `room_id + room_name`.

Пока хотя бы один gate не пройден, **не создавать GitHub Release и не запускать новую версию** на рабочем HAOS.

## 3. Только read-only preflight на HAOS

Из HAOS Terminal (ничего не перезапускает):

```bash
ha apps info 8d59ce70_dh_climate_app --raw-json
ha supervisor info --raw-json
```

По официальному API также доступны `GET /addons/<app>/info` для текущих options и `POST /addons/<app>/options/validate` для проверки **только** без записи; второй путь допустим **лишь в изолированном тестовом App** на этапе schema smoke. Сохранять исходные options **локально, в приватной папке** без публикации чувствительных данных в репозитории.

Подготовить инвентаризацию:

| Room ID | Фактические old sensors / humidity / windows | Старые FAST / SLOW / slow_target | Новая role / control / actuator | SQLite targets | Решение |
| --- | --- | --- | --- | --- | --- |
| `livingroom` | **ждём live options** | **ждём** | **не угадывать** | **снять snapshot** | HOLD |
| `bedroom` | **ждём live options** | **ждём** | **не угадывать** | **снять snapshot** | HOLD |
| `lab_cool` | **ждём live options** | **ждём** | LAB-верификация | **снять snapshot** | HOLD |
| `lab_heat` | **ждём live options** | **ждём** | LAB-верификация | **снять snapshot** | HOLD |
| `lab_humidifier` | **ждём live options** | **ждём** | LAB-верификация | **снять snapshot** | HOLD |
| `lab_dehumidifier` | **ждём live options** | **ждём** | LAB-верификация | **снять snapshot** | HOLD |
| `lab_ventilation` | **ждём live options** | **ждём** | НЕ добавлять CO₂/вентиляцию | **снять snapshot** | HOLD |

Фактические семь комнат и устройства предоставлены пользователем 2026-10-27; полный TARGET YAML уже подготовлен и проверен парсером. Идентификаторы всех комнат, MQTT unique ID и накопленные значения сохраняются.

## 4. SQLite и однократный старый slow_target

- Сделать штатную резервную копию **App с `/data`**, резервную копию существующих options, отдельно проверить возможность отката.
- Перед изменениями остановить App; зафиксировать его состояние и убедиться, что SQLite не используется процессом.
- Сохранить SQLite консистентным backup API, не копировать только `.db` при наличии неподхваченного WAL. Проверить `PRAGMA integrity_check`.
- Новый `tools/seed_slow_profiles.py` выполняет по умолчанию только **DRY-RUN**, проверяет существующий SQLite и вводимые подтверждённые прежние значения. Пример синтаксиса с **тестовыми** значениями, НЕ команда для рабочей БД:

```bash
python3 tools/seed_slow_profiles.py --db /tmp/STAGING_COPY.db --room test_room=27
```

- После подтверждения истинного `slow_target` по каждой комнате, когда App **остановлен** и есть отдельный backup, `--apply --confirm-offline STOPPED_BACKED_UP` создаёт ещё один консистентный SQLite backup, добавляет `slow_room_targets` и делает `INSERT OR IGNORE` для `day/night/away`. **Ни одна уже существующая уставка не перезаписывается**.
- Для ранее неизвестной SLOW комнаты без old `slow_target` никакого скрытого seed нет. Значение вносится явно после технического согласования.

## 5. Целевой options YAML — форма, не live-конфигурация

```yaml
night_mode: input_boolean.example_night
we_at_home: input_boolean.example_presence
outdoor:
  temperature_sources:
    - sensor.example_outdoor
    - weather.example_fallback
  humidity_sources:
    - sensor.example_outdoor_humidity
rooms:
  - id: example
    name: Пример
    temperature_sensors:
      - sensor.example_room_air
    humidity_sensors: []
    window_sensors: []
    devices:
      - entity: switch.example_floor_valve
        role: slow_heat
        control: app
        actuator: normal_closed
telemetry_enabled: false
log_level: info
```

**Запрещено вставлять этот пример в production Supervisor:** `example_*` — вымышленные тестовые имена. Пользовательский YAML для `livingroom/bedroom/LAB` подготовлен отдельно на основе предоставленных фактических options.

## 6. Контролируемая установка — только ПОСЛЕ Gates

1. После live inventory подготовить **весь новый YAML целиком** и сравнение old→new для каждого room, зафиксировать текущие SQLite FAST/HUM/SLOW/seasons и backup.
2. На отдельном тестовом App проверить несовместимые старые options и точный порядок Supervisor **stop → update → replace complete options → validate → start**. Проверить обработку неудачного update/rollback. На этом шаге нет связи с рабочими реле.
3. Представить результаты test App GUI, CI, unit, offline SQLite seed, лабораторных dry-run; только после отдельного разрешения пользователя проводить изменения `8d59ce70_dh_climate_app`.
4. После контролируемого старта наблюдать `StartupActuatorGate DEFER→READY`, SQL integrity, retained room/global/climate health, machine events, room ownership и командный trace. Не допускать критических неизвестных фактов.
5. Команды физическому кондиционеру, насосам, сервоприводам — **отдельный** согласованный E2E. Терминал оставить открытым для логов.

## 7. Стандарты

- [DigitalHouses Application Standard](https://github.com/DigitalHouses/home-assistant-apps/blob/main/docs/standards/DIGITALHOUSES_APP_STANDARD.md)
- [Events & Notifications Standard](https://github.com/DigitalHouses/home-assistant-apps/blob/main/docs/standards/EVENTS_AND_NOTIFICATIONS_STANDARD.md)
- [Contract Data Policy](https://github.com/DigitalHouses/home-assistant-apps/blob/main/docs/standards/CONTRACT_DATA_POLICY.md)
- [Home Assistant Supervisor Installed Apps API](https://contributors.home-assistant.io/apps/supervisor-api/apps/)

Документ служит контрольным списком работ по реализации, **не инструкцией немедленно запускать команду обновления**.
