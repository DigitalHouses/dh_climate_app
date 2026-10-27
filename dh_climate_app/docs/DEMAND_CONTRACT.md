# DH Climate App · Demand: ROOM / DEVICE / ACTUAL

## Назначение

В версии 0.1.33 Demand — исключительно наблюдение. Ни один из этих сигналов
не используется для управления устройствами, сезонами, котлом или насосами.

Все значения вычисляются из одного актуального HA-снимка по существующим
событиям `state_changed` (без новых циклов опроса).

## Контракт

| Уровень | HEAT binary | COOL binary | UI Count |
|---|---|---|---|
| ROOM | `binary_sensor.dh_climate_app_heat_demand` | `binary_sensor.dh_climate_app_cool_demand` | `sensor.dh_climate_app_heat_demand_count`, `sensor.dh_climate_app_cool_demand_count` |
| DEVICE | `binary_sensor.dh_climate_app_heat_device_demand` | `binary_sensor.dh_climate_app_cool_device_demand` | `sensor.dh_climate_app_heat_device_demand_count`, `sensor.dh_climate_app_cool_device_demand_count` |
| ACTUAL | `binary_sensor.dh_climate_app_actual_heat_demand` | `binary_sensor.dh_climate_app_actual_cool_demand` | Нет |

Итого: восемь сущностей ROOM+DEVICE и до двух ACTUAL — только при указании
соответствующих источников в YAML.

### ROOM

- `hvac_mode=heat, hvac_action=heating` — запрос тепла;
  `hvac_mode=cool, hvac_action=cooling` — запрос холода.
- Учитываются **все** комнатные термостаты приложения, независимо от наличия
  и числа устройств, один голос на комнату.
- Повторно гистерезис не вычисляется; `hvac_action` уже учитывает его.
- Сведения о комнатах берутся из `rooms[].id` и `rooms[].name`.

### DEVICE

- Смотрим только записи `rooms[].devices[]` с `control: device`
  (домен `climate`).
- Состояния `hvac_action=heating/cooling` определяют запрос независимо от
  того, какую уставку отправляло приложение.
- Режим `heat/cool` без соответствующего `hvac_action` **не** даёт запрос.
- Подсчёт ведётся по аппаратным термостатам, не по комнатам.
- `control: app` и релейные устройства не учитываются.
- Роль определяет допустимые направления (`heat`, `cool`, `heat_cool`).

### ACTUAL

Источник явно задаётся пользователем в штатной конфигурации App:

```yaml
actual_demand:
  heat: binary_sensor.real_aggregator_heat_request
  cool: binary_sensor.real_aggregator_cool_request
```

Это **пример**, не реальные entity_id. При отсутствии источника соответствующая
ACTUAL-сущность не создаётся. Никакой автоматической интеграции SALUS
и вычисления Actual из Room/Device нет.

### Трёхзначная логика

- ON: есть хотя бы один достоверно запрашивающий источник.
- OFF: все рассматриваемые источники достоверны и запросов нет.
- unavailable: источники неполны/недостоверны, поэтому нельзя подтвердить OFF.
- UI Count и список доступны **только при полном наборе исходных состояний**.
  Если один термостат неизвестен, бинарный Demand может быть ON благодаря
  другому, но Count становится unavailable во избежание ложного итога.
- На потере связи с HA публикуется `availability=offline`, даже если в MQTT
  сохранено последнее ON или OFF.
- Если кандидатов соответствующего типа нет, итог OFF / count=0.

### Recorder и UI

- Все шесть бинарных сенсоров имеют только state и availability; **никаких
  динамических JSON-атрибутов**, пригодны для Recorder.
- Четыре числовых UI Count имеют `rooms` / `devices` как JSON-атрибуты.
  Из них не создаются отдельные команды или профили.
- **Важно:** приложение не имеет полномочий менять конфигурацию Recorder.
  Для исключения четырёх UI Count из истории нужна существующая политика
  `recorder.exclude.entities` на стороне HA, например:

```yaml
recorder:
  exclude:
    entities:
      - sensor.dh_climate_app_heat_demand_count
      - sensor.dh_climate_app_cool_demand_count
      - sensor.dh_climate_app_heat_device_demand_count
      - sensor.dh_climate_app_cool_device_demand_count
```

Если настроено `recorder.include`, надо согласовать с ним правила;
не дублировать корневой `recorder` в другом пакете.

## Приёмка

Проверить ROOM ON/OFF и неполные данные; DEVICE heating/idle и отсутствие
`hvac_action`; ACTUAL on/off/unavailable; публикации MQTT Discovery,
отсутствие JSON-атрибутов у бинарных сущностей, сохранение событийности
и отсутствие влияния новых наблюдателей на исполнение FAST/SLOW.
