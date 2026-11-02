# DH Climate App — read-only гидравлическое дерево ресурсов (этап 1)

**Статус:** реализована модель конфигурации + диагностика, без редактора и без команд на оборудование.  
**Документ решения:** [HEATING_ACTUATION_AND_AGGREGATOR_DECISION_2026-11-02.md](HEATING_ACTUATION_AND_AGGREGATOR_DECISION_2026-11-02.md)

## Что реализовано

Новый необязательный раздел `hydraulics` в **каноническом** манифесте `/data/dh_climate_manifest.json`, внутри `options`. При отсутствии раздела старые конфигурации не меняются. Гидравлическая модель не участвует в отопительном Demand Engine, физической коммутации и сезоне.

Семь независимых коллекций: `separators` (гидрострелки), `groups` (температурные группы), `circuits` (физические контуры), `pumps`, `actuators` (сервоприводы), `valves` и `aggregators` (аппаратные или виртуальные).

**Объект объявляется только один раз.** Группы и контуры связываются с насосами, сервоприводами и клапанами массивами `*_ids`. Один насос может обслуживать одновременно несколько групп. Контуры связываются с группой, комнатой и конечными устройствами `terminals`. Объекты без группы/гидрострелки допустимы.

При наличии гидрострелки дерево показывает две навигационные ветки: высокотемпературные и низкотемпературные группы. Существование этих категорий **не создаёт** приборы или показания.

Каждый объект принимает `signals` — словарь «роль измерения/состояния → реальная HA entity_id». Допустимы роли `supply_temperature`, `return_temperature`, `supply_pressure`, `return_pressure`, `state`, `rpm`, `powered`, `position` и другие snake_case идентификаторы. Роль не определяет физическую размерность: измерение и единицы всегда поступают от Home Assistant. Отсутствующее состояние — `unknown/unavailable`, **не OFF и не 0**.

Переключение и редактирование оборудования на этом этапе отсутствуют. Explorer показывает только сигналы и инженерные связи. Настройка через UI и сохранение Draft/Validate/Apply — следующий этап.

## Пример структуры (НЕ реальная схема Армана)

Внутри `options` существующего манифеста, рядом с `rooms`, `resources` и другими полями:

```yaml
hydraulics:
  aggregators:
    - id: heating_logic
      name: "Агрегатор отопления"
      device_type: hardware
      signals:
        heat_request: binary_sensor.heating_aggregator_request

  separators:
    - id: header_1
      name: "Гидрострелка"
      signals:
        supply_temperature: sensor.header_supply_temperature

  pumps:
    - id: shared_pump
      name: "Общий насос"
      signals:
        state: binary_sensor.common_pump_active

  actuators:
    - id: valve_1
      name: "Сервопривод петли"
      signals:
        powered: binary_sensor.floor_actuator_power

  groups:
    - id: floor_group
      name: "Группа тёплого пола"
      temperature_class: low
      separator_id: header_1
      aggregator_id: heating_logic
      pump_ids: [shared_pump]
      signals:
        supply_temperature: sensor.floor_supply
        return_temperature: sensor.floor_return

  circuits:
    - id: floor_loop_1
      name: "Петля тёплого пола"
      group_id: floor_group
      room_id: hall
      actuator_ids: [valve_1]
      signals:
        return_temperature: sensor.floor_loop_return
      terminals:
        - id: floor_emitter
          name: "Тёплый пол"
          room_id: hall
```

Здесь `hall` должна быть настоящей комнатой из `rooms`. Все `entity_id` **только примеры синтаксиса**, ни одна сущность не создаётся; их нельзя применять на объекте без существующих HA entity. Можно вовсе не указывать `signals`, когда нет датчика: название и физическая связь сохраняются в дереве.

## Валидация

- У каждого узла нужны уникальные в пределах типа `id` (snake_case) и `name`. Проверяются неизвестные поля.
- `groups.temperature_class` строго `high` либо `low`, `aggregators.device_type` — `hardware` либо `virtual`.
- `separator_id`, `group_id`, `aggregator_id`, `pump_ids`, `actuator_ids`, `valve_ids`, `room_id` должны ссылаться на существующие объекты/комнаты. Пропуски ссылок вызывают ошибку валидации, а не вымышленные узлы.
- Сигналы и конечные HA-entity берутся исключительно из Home Assistant. Одно зарегистрированное физическое устройство может иметь несколько **ссылок**, но не дублируется в манифесте.

## Границы этапа

- Работающие `resources[]`, `pumps[]`, `circuits[]` старого Supervisor-контракта оставлены без изменений и продолжат отображаться в старой части дерева. Автоматической миграции **нет**.
- Внешние сезонные команды `OFF` термостатам, логика Siemens LOGO!, программы насосов и реальные электрические подключения **не изменены**.
- Нельзя выдавать пример Армана за фактический монтаж: ждём схему сантехника.
- Входящий read-model не доказывает фактического положения клапана или циркуляции; отображается только то, что отдаёт HA.
