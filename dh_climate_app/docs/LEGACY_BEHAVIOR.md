# Legacy DH Climate 5 — извлечение контракта поведения

Этот документ фиксирует поведение, которое новый `dh_climate_app` должен сохранить из `DigitalHouses/dh_climate_1`.

Это контракт миграции, а не требование переносить код PostgreSQL.

## Проверенный источник

Текущий legacy-репозиторий:

```text
DigitalHouses/dh_climate_1
```

Ключевая реализация:

```text
src/dh_climate_pg/workers/ha_thermostat_facade_worker.py      v5.12
src/dh_climate_pg/workers/ha_outdoor_thermostat_facade_worker.py
src/dh_climate_pg/workers/ha_system_facade_worker.py
_db_dump.sql
```

## Наружный контур

Legacy-логика наружного контура:

- провайдеры имеют явный приоритет;
- меньшее числовое значение приоритета побеждает;
- выбранные наружные температура/влажность используются для производных значений;
- среди текущих/скользящих производных есть avg24;
- сезон глобальный;
- пороги сезона можно менять через наружный термостат;
- состояния сезона: `HEAT`, `COOL`, `OFF`.

Формула сезона в PostgreSQL-реализации:

```text
avg24 < heat_threshold - hysteresis → HEAT
avg24 > cool_threshold + hysteresis → COOL
otherwise                           → OFF
```

Фасад наружного термостата:

```text
domain              climate
mode                heat_cool
current_temperature avg24 when available
current_humidity    avg24 when available
target_temp_low     heat threshold
target_temp_high    cool threshold
hvac_action         heating / cooling / idle
```

## Поведение комнаты

Legacy-входы комнаты:

- температура;
- влажность;
- target;
- профиль;
- climate control;
- глобальный сезон;
- глобальные факты home/night.

Канонизация комнатных сенсоров усредняла последние показания всех включённых сенсоров одного типа.

Приоритет effective profile:

```text
HEAT + climate_control=false → antifreeze
not at home                  → away
night mode                   → night
otherwise                    → day
```

Идентичность target:

```text
room × season × profile
```

Фасад комнатного термостата:

- одна climate-сущность на комнату;
- текущая температура;
- выбранная/effective целевая температура;
- режимы, ограниченные сезоном;
- HVAC action;
- профиль представлен через `fan_mode` термостата;
- варианты профиля: day/night/away/antifreeze.

В legacy v5.12 выбор профиля работает как временный overlay редактирования фасада: пользователь выбирает профиль, редактирует его target, после idle timeout overlay сбрасывается.

## Важная неоднозначность legacy

В legacy-репозитории PostgreSQL одновременно присутствуют:

1. room facade view с поведением, похожим на односторонний threshold/deadband;
2. проектные климатические контракты с настоящим stateful симметричным гистерезисом.

Компактный App намеренно принимает stateful симметричную модель, потому что текущий продукт явно требует общий гистерезис и это предотвращает частое переключение выходов.

Это осознанная очистка поведения, а не случайный эффект переноса кода.

## Осознанные изменения в новом App

Следующие продуктовые решения имеют приоритет над деталями legacy-реализации:

- PostgreSQL отсутствует;
- SQL не содержит бизнес-логику;
- отсутствует lifecycle jobs/Matrix/Dispatcher/UC;
- каждая комната — отдельный MQTT Device;
- App напрямую управляет настроенными `climate` / `switch` устройствами;
- классы исполнительных устройств `FAST` и `SLOW` входят в базовую архитектуру;
- SLOW target тёплого пола отделён от target температуры воздуха комнаты;
- опциональное управление влажностью комнаты публикуется как нативная HA-сущность `humidifier`;
- room devices по умолчанию не публикуют дублирующие temperature/humidity sensors;
- настроенный гистерезис температуры дома — одно глобальное значение;
- наружный avg24 рассчитывается новым App по текущему утверждённому алгоритму.

## Принцип совместимости

Миграция проверяется на границе поведения Home Assistant:

```text
тот же пользовательский intent
→ эквивалентное поведение сущностей
→ эквивалентные переходы состояния
→ эквивалентный смысл target/profile/season
```

Внутренняя Python-реализация нового App не обязана быть похожа на старую Python/SQL-реализацию.
