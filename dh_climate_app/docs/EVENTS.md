# Машинные события Climate App

## Назначение

DigitalHouses Climate App публикует одну MQTT Event-сущность Home Assistant:

```text
event.dh_climate_app_event
```

Это единый публичный поток переходов состояния App. Текущие факты остаются в retained-состояниях climate/sensor/binary_sensor.

## Транспортный контракт

```text
schema_version: 2
QoS: 1
retain: false
```

Каждый payload содержит:

```text
schema_version
event_type
observed_at
```

Дополнительные поля зависят от конкретного `event_type`.

Производитель публикует только машинные данные. Язык уведомления, заголовок, текст, emoji и канал доставки принадлежат локальному пакету Home Assistant.

## Порядок публикации

Если один расчёт одновременно изменяет retained current state и создаёт Event:

```text
1. рассчитать truth
2. опубликовать retained state
3. опубликовать retained Problem state
4. отправить transient machine Event
```

Это гарантирует, что автоматизация, сработавшая по Event, прочитает текущие сущности и увидит ту же truth, которая представлена событием.

## Правило baseline / reconnect

При startup и reconnect Home Assistant создаётся новый baseline без transition Event.

События, произошедшие пока App или Home Assistant были недоступны, не реконструируются. Если логике восстановления нужен контекст, она должна отдельно читать retained current state.

## Каталог событий

### outdoor_temperature_source_changed

Отправляется при изменении активного источника в упорядоченной priority-цепочке наружной температуры.

Поля:

```text
previous_source
current_source
previous_temperature
current_temperature
```

Первое полное наблюдение после startup/reconnect только устанавливает baseline и не создаёт Event. Обычное изменение значения температуры от того же источника журналируется, но не публикуется как machine Event.

### season_changed

Отправляется при изменении глобального сезона между `heat`, `cool` и `off`.

Поля:

```text
previous_season
current_season
avg_24h_temperature
current_temperature
heat_threshold
cool_threshold
hysteresis
```

### precipitation_started

Сухое/без осадков состояние меняется на дождь, снег, смешанные осадки или град.

Поля:

```text
previous_type
current_type
condition
precipitation_mm
forecast_at
source_entity
```

`precipitation_mm` — нормализованное количество из текущего hourly forecast bucket, а не измерение физического дождемера.

### precipitation_stopped

Активные осадки сменяются нормальным состоянием без осадков.

Используются те же weather-поля.

### precipitation_type_changed

Меняется тип активных осадков, например:

```text
rain -> snow
snow -> rain
rain -> mixed
mixed -> snow
```

Используются те же weather-поля.

### window_opened / window_closed

Поля:

```text
room_id
room_name
previous_state
current_state
season
```

Неопределённое состояние окна здесь не дублируется. Оно представлено через `problem_started` / `problem_recovered` с `problem_id=room_window_state_unknown`.

### problem_started / problem_recovered

Общий transition contract для Problems, которыми владеет App.

Поля описывают машинную идентичность/контекст Problem:

```text
problem_id
category
severity
room_id      (when applicable)
entity_id    (when applicable)
details      (when applicable)
```

Такой контракт остаётся расширяемым при добавлении новых кодов Problems исполнительных устройств или сенсоров.

## Что намеренно не является Event

Обычные циклы гистерезиса термостата — это состояние, а не события:

```text
heating -> idle -> heating
cooling -> idle -> cooling
```

Циклы humidity controller и FAST/SLOW reconciliation также не являются Events, пока отдельное продуктовое требование не определит действительно значимый переход, о котором нужно уведомлять.

Новый тип события должен удовлетворять всем условиям:

1. произошло что-то семантически значимое, а не просто существует текущее значение;
2. тот же факт уже не публикуется другим event type;
3. payload имеет документированную машинную схему;
4. Discovery `event_types`, тесты и этот документ обновляются одновременно.

## Локальный шаблон уведомлений

Предполагаемый путь в Home Assistant:

```text
event.dh_climate_app_event
-> trigger event.received
-> trigger.id
-> choose
-> прямое локальное действие
```

Публичный App не зависит от конкретного локального notification service.

## Логи отделены от Events

Подробный диагностический logging не входит в Event contract. App всегда пишет собственный Python log и может best-effort зеркалировать выбранные управляющие traces в локальный сервис `script.write2climatelog`.

Ошибка зеркалирования изолирована от climate control и слоя Problem/Event. Обычные FAST/SLOW-команды и циклы гистерезиса не становятся events. Ошибки исполнительных устройств используют существующие `problem_started` / `problem_recovered`; если actuator принадлежит комнате, события содержат и `room_id`, и `entity_id`.
