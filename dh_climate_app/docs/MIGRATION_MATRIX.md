# Матрица миграции DH Climate 5 → DH Climate App

Статус: архитектурный аудит  
Legacy source: `DigitalHouses/dh_climate_1`  
Новый source: `DigitalHouses/dh_climate_app`

Правило миграции — **совместимость поведения на границе Home Assistant**, а не совместимость исходного кода или базы данных.

## Архитектурное соответствие

| Legacy PostgreSQL Climate 5 | Новый Climate App | Решение |
| --- | --- | --- |
| PostgreSQL business engine | доменное ядро Python | заменить |
| `t_system_settings` business/UI settings | App options + компактное runtime state в SQLite | упростить |
| append-only room/outdoor truth tables | текущий HA state cache + только необходимое rolling/persistent state | упростить |
| system jobs | прямой event-driven пересчёт | удалить |
| handlers | доменные методы Python | заменить |
| Matrix | детерминированный компилятор device policy | заменить |
| Firewall | явные device safety predicates | заменить |
| Decision plan/history | desired device state | заменить |
| Dispatcher | прямой reconcile loop | заменить |
| UC command queue | ограниченные идемпотентные service calls | удалить |
| Universal Controller | `DeviceExecutor` | заменить |
| Confirmator | сверка HA state + retry/cooldown | заменить |
| UC Supervisor | runtime health + диагностика Problem | заменить |
| SQL runtime sessions/component status | Version / Started at / Problem | упростить |
| PostgreSQL admin/business procedures | App configuration + нативные HA controls | удалить |
| HA MQTT facade workers | MQTT Discovery facade | сохранить поведение |

## Наружный контур

| Legacy-поведение | Новая реализация |
| --- | --- |
| приоритет provider | упорядоченные `outdoor_temperature_sources` / `outdoor_humidity_sources` |
| выбор temperature/humidity | независимый выбор первого валидного источника |
| текущая наружная truth | выбранный live source |
| avg24 | текущий утверждённый rolling 24h алгоритм с сохранением состояния |
| season | `HEAT / COOL / OFF` |
| season thresholds | сохраняемые нижний/верхний targets |
| outdoor thermostat | MQTT `climate` facade `heat_cool` |
| source unavailable | fallback; если все live temperature sources недоступны — season OFF |

## Комнатный контур

| Legacy-поведение | Новая реализация |
| --- | --- |
| последние значения включённых room sensors | последние HA states настроенных sensors |
| room temperature | среднее текущих валидных настроенных temperature sensors |
| room humidity | среднее текущих валидных настроенных humidity sensors |
| global season ограничивает room mode | сохранено |
| day/night/away/antifreeze | сохранено |
| room target по season/profile | сохраняется в SQLite |
| HEAT + room off → internal antifreeze | сохранено |
| COOL + room off → настоящий off | сохранено |
| profile-edit overlay | сохранён с idle timeout |
| thermostat facade | одна MQTT `climate` entity на комнату |
| все комнаты под одним legacy device | изменено: один MQTT Device на комнату для назначения HA Area |

## Гистерезис

Legacy storage содержал отдельные room и outdoor hysteresis. Текущее продуктовое решение намеренно использует один общий гистерезис температуры дома.

Поведение комнатного термостата stateful и симметрично:

```text
HEAT
T <= target - h  -> heating
T >= target + h  -> idle
inside band       -> keep previous state

COOL
T >= target + h  -> cooling
T <= target - h  -> idle
inside band       -> keep previous state
```

Предыдущее действие комнаты сохраняется, чтобы restart не сбрасывал состояние внутри deadband.

## Контекст окна

Legacy truth окна комнаты:

```text
any configured contact open             -> open
else any configured contact unavailable -> unknown
otherwise                                -> closed
```

Legacy Matrix применяла политики окна по типам устройств. Новый App сохраняет полезное поведение `turn_off` без отдельной Matrix:

```text
room window=open
+ actuator listed in window_off_devices
-> actuator desired state=off
```

Состояние окна не переписывает demand комнатного термостата.

## Управление устройствами

### FAST

Legacy-цепочка Matrix/Decision/Dispatcher/UC заменяется:

```text
room action
-> совпадение функции устройства
-> safety predicates
-> desired state
-> сравнение с actual HA state
-> service call только при различии
```

Поддерживаемые домены: `switch`, `climate`.

Climate entity, присутствующая одновременно в `fast_heat` и `fast_cool`, считается реверсивным heat/cool устройством.

### SLOW

Новое продуктовое требование добавляет явный класс с высокой тепловой инерцией.

SLOW v0.1 принимает только локальные физические `climate`-термостаты:

```text
HEAT -> mode=heat, target=slow_target
COOL/OFF -> mode=off
```

Локальный термостат и его собственный floor/slab probe остаются финальным контуром циклирования и безопасности. SLOW не следует циклам комнатного термостата по температуре воздуха.

## Защита AC-отопления при низкой наружной температуре

Legacy Firewall запрещал AC heating ниже `ac_min_outdoor_temperature`, по умолчанию `-10 °C`.

Новое соответствие:

- reversible FAST `climate` = одна и та же entity в `fast_heat` и `fast_cool`;
- при heating, если live outdoor temperature ниже `ac_min_outdoor_temperature`, это устройство удерживается off;
- остальные допустимые heat sources не затрагиваются.

## Влажность

Управление влажностью в новом App намеренно проще и нативно для HA:

- опционально для каждой комнаты;
- `humidifier` или `dehumidifier`;
- нативный MQTT `humidifier` facade;
- сохраняемый target;
- отдельный RH hysteresis;
- прямое управление actuator `switch` или `humidifier`.

## Граница persistence

SQLite хранит только состояние, которое должно переживать restart:

- season thresholds;
- rolling outdoor samples;
- room target matrix;
- room climate enable state;
- previous room HVAC action;
- humidity target/control state.

В SQLite **нет** jobs, dispatcher queues, command lifecycle tables, Matrix candidates, Firewall results, SQL procedures или business orchestration.

## Соответствие механизмов надёжности

| Legacy-механизм | Новый механизм |
| --- | --- |
| event/job append chain | HA WebSocket state events |
| current SQL views | state cache с защитой timestamp |
| UC retries | bounded executor retry |
| Confirmator | desired-vs-actual reconciliation |
| Supervisor | reconnect loop + диагностика Problem |
| runtime session reconstruction | свежий HA snapshot после reconnect |
| historical command replay | явно не выполняется |

Инвариант reconnect:

```text
сначала subscribe
-> получить current snapshot
-> отбросить более старые buffered events по timestamp
-> возобновить decisions
```

## Граница совместимости HA facade

Миграция считается принятой, когда тот же пользовательский intent даёт эквивалентное внешне значимое поведение:

```text
season thresholds
room target/profile
room on/off
room temperature response
device eligibility
window safety
cold-weather safety
humidity target
```

Внутренняя структура SQL tables, количество workers и топология command history явно **не являются** требованиями совместимости.

## Что намеренно не переносится

Следующая legacy-инфраструктура не должна возвращаться без конкретного будущего требования:

- PostgreSQL orchestration;
- Matrix как subsystem;
- Firewall как subsystem;
- Dispatcher;
- UC queue;
- lifecycle Universal Controller;
- lifecycle Confirmator;
- SQL jobs/handlers;
- runtime session tables;
- append-only operational history каждого перехода состояния.

Компактный App должен добавлять сложность только тогда, когда она защищает определённое пользовательское поведение или safety invariant.
