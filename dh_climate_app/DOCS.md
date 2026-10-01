# DigitalHouses Climate App

## Что делает App

App принимает климатические решения для дома и публикует нативные climate-сущности Home Assistant через MQTT Discovery.

Цепочка управления:

```text
состояния HA sensors
→ наружные / комнатные факты
→ решения season + room thermostat
→ политика устройств FAST / SLOW
→ прямое reconciliation через сервисы HA
→ физические climate / switch / humidifier entities
```

App не использует PostgreSQL. SQLite в `/data/dh_climate.db` служит только для durable state.

## Форма конфигурации

Схема Home Assistant App намеренно плоская. Home Assistant ограничивает глубину вложенности options schema, поэтому списки Home Assistant entities задаются строками через запятую. Записи комнат содержат только primitive fields; App компилирует их в типизированную внутреннюю модель.

Полный пример см. в [docs/CONFIG_EXAMPLE.yaml](docs/CONFIG_EXAMPLE.yaml).

## Глобальные настройки

`hysteresis` — единый гистерезис температуры дома, используемый контроллерами сезона и комнатной температуры.

`humidity_hysteresis` задаётся отдельно, потому что относительная влажность измеряется в другой физической единице.

`night_mode` и `we_at_home` — опциональные Home Assistant facts. Если настроенная entity `we_at_home` недоступна, App использует более безопасный профиль `away`.

## Наружные источники

`outdoor_temperature_sources` и `outdoor_humidity_sources` — упорядоченные списки entities через запятую. Температура и влажность имеют независимые priority chains.

Для каждого измерения App использует первую текущую валидную настроенную entity. Если она становится недоступной, выбирается следующая. Когда preferred source снова становится валидным, он автоматически возвращается в работу.

В temperature chain можно свободно смешивать `sensor.*` и `weather.*` entities в заданном порядке приоритета. Обычный `sensor.*` читается из его numeric state. `weather.*` поддерживается напрямую: App читает текущий атрибут `temperature` для наружной температуры и `humidity` для наружной влажности. Поэтому такие entities, как `weather.forecast_home_assistant`, могут быть primary или fallback без template sensors.

Изменения RAW наружной температуры записываются в `climate.log` вместе с active source. Переходы active source записываются отдельной строкой и публикуются как `outdoor_temperature_source_changed` в `event.dh_climate_app_event`.

Для обычного шума источника и ступеней при provider/sensor failover используется один pipeline:

```text
приоритетный источник
→ RAW temperature
→ EMA filter
→ публичная наружная температура
→ внутренние минутные samples
→ скользящее 24-часовое арифметическое среднее
→ season
```

`outdoor_temperature_ema_minutes` — постоянная времени EMA, по умолчанию 20 минут. EMA продвигается не чаще одного раза в минуту. Переключение источника не имеет специального режима интерполяции: ступень обрабатывается той же EMA, что и любое другое изменение температуры.

Минутные filtered samples сохраняются в SQLite, а 24-часовое среднее является их арифметическим средним. Так каждая известная минута получает одинаковый вес и устраняется прежняя зависимость от нерегулярной частоты обновления provider. При upgrade существующая история температуры до EMA один раз преобразуется в minute EMA history. Recorder остаётся поверхностью наблюдения/истории, а не source of truth для климатического расчёта. Наружная влажность сохраняет отдельное time-weighted 24-hour average.

Глобальный season:

```text
avg24 < heat_threshold - hysteresis → HEAT
avg24 > cool_threshold + hysteresis → COOL
otherwise                           → OFF
```

Если ни одного live source наружной температуры нет, season принудительно становится `OFF`.

Season thermostat в Home Assistant — climate entity `heat_cool` с двумя targets:

- lower/red target = порог отопительного сезона;
- upper/blue target = порог сезона охлаждения.

Изменение любого target сохраняется в SQLite.

## Комнаты

Каждая настроенная комната становится отдельным MQTT Device. Этот Device следует назначить соответствующей Home Assistant Area.

Комнатный термостат публикует:

- текущую температуру комнаты;
- текущую влажность комнаты, если она настроена;
- target текущего активного пользовательского профиля, когда активен HEAT или COOL;
- season-native HVAC modes: HEAT показывает только `off / heat`, COOL — только `off / cool`, межсезонье — только `off`;
- нативные Home Assistant presets `day / night / away`;
- HVAC action `heating / cooling / idle / off`.

В межсезонье (`season: off`) комнатный термостат остаётся доступным, чтобы Home Assistant и Apple Home продолжали показывать текущую комнатную температуру, но facade принудительно находится в `off` и не публикует seasonal target. Команды target и HVAC, пришедшие через room thermostat, игнорируются до появления HEAT или COOL. Persisted Number entities целей профилей остаются доступны для installer/advanced configuration.

Изменение target на термостате всегда меняет target профиля, который пользователь редактирует в этот момент: `day`, `night` или `away`. Неактивный профиль не редактируется скрытно.

Профили публикуются через нативный `climate.preset_mode`; они не кодируются через fan speed.

Каждая комната публикует отдельные configuration entities `number`, скрытые по умолчанию, для сохраняемых profile targets:

- Heat day / night / away;
- Heat antifreeze;
- Cool day / night / away.

Эти настройки позволяют инсталлятору или advanced-пользователю Home Assistant, например, подготовить Night target днём, не меняя текущую работу активного термостата.

`antifreeze` остаётся внутренним защитным профилем HEAT. Когда комнатный термостат находится в Off, пользовательский thermostat сохраняет свой scheduled target `day / night / away`, а внутренний control loop может использовать antifreeze target.

Если настроено несколько room temperature или humidity sensors, используются средние их последних доступных значений.

Идентичность target:

```text
room × season × profile
```

Скрытые configuration Number entities остаются доступными и в межсезонье, поэтому инсталлятор может подготовить targets будущего сезона, не показывая обычному пользователю неактивный room thermostat.

## Точность температуры

Climate calculations сохраняют полную floating-point precision внутри App. Каждое температурное значение, опубликованное через публичный контракт Home Assistant / MQTT / machine Event, округляется до одного знака.

Это касается текущих температур, rolling 24-hour values, temperature thresholds и температурных полей Events. Округление — только правило presentation и не меняет расчёты season, hysteresis или device control.

## Наружные UI sensors

Системный Device публикует отдельные наружные измерения для dashboards и debugging:

- `sensor.dh_climate_app_outdoor_temperature_raw` — значение выбранного источника, diagnostic;
- `sensor.dh_climate_app_outdoor_temperature` — EMA-filtered температура, используемая обычной climate logic;
- `sensor.dh_climate_app_outdoor_temperature_avg24` — rolling 24-hour mean минутных filtered samples;
- `sensor.dh_climate_app_outdoor_humidity`.

Три temperature sensors используют state-only MQTT contracts: пользовательские динамические attributes к ним не прикрепляются. Их states подходят для Recorder. RAW diagnostic facade ограничен максимум одной публикацией в минуту, а filtered и avg24 меняются только на той же минутной сетке фильтра. Неизменившиеся значения с одним знаком дополнительно подавляются MQTT payload deduplication.

Внутренняя RAW truth при этом немедленно поступает в hard safety, logs и machine events. Идентичность источника остаётся доступной через season facade, logs и machine event смены источника.

## Осадки по weather

Если хотя бы один настроенный наружный source — `weather.*`, App использует первую настроенную weather entity из temperature/humidity chains как источник осадков.

Текущий precipitation type определяется по condition weather entity:

- `rainy / pouring / lightning-rainy` → `rain`;
- `snowy` → `snow`;
- `snowy-rainy` → `mixed`;
- `hail` → `hail`;
- остальные нормальные conditions → `none`.

Количество осадков запрашивается через Home Assistant `weather.get_forecasts` с `type: hourly`. App публикует количество для текущего hourly forecast bucket, нормализованное в миллиметры. Это прогноз осадков на текущий час, а не физическое измерение дождемером.

Системный Device публикует:

- `sensor.dh_climate_app_precipitation_type`;
- `sensor.dh_climate_app_precipitation_amount`.

## Машинные события

App публикует одну MQTT Event entity Home Assistant:

`event.dh_climate_app_event`

Event payloads используют schema version 2, QoS 1 и никогда не retain. Первое полное runtime observation устанавливает baseline и не создаёт event. Reconnect также устанавливает новый baseline, поэтому transitions, произошедшие пока Home Assistant был недоступен, не реконструируются.

Начальные event types:

- `season_changed`;
- `precipitation_started`;
- `precipitation_stopped`;
- `precipitation_type_changed`;
- `window_opened`;
- `window_closed`;
- `problem_started`;
- `problem_recovered`.

Events содержат только машинные данные. Человеческий язык, formatting и delivery остаются в локальном notification package Home Assistant.

Unknown/restored window truth представляется через `problem_started` / `problem_recovered` с problem code `room_window_state_unknown`, чтобы не создавать дублирующие machine events для одного transition.

Обычные циклы гистерезиса термостата намеренно не являются Event; retained room state уже представляет текущий факт.

## Контекст окна

Window contacts опциональны для комнаты через `window_sensors`.

Truth окна комнаты следует прежнему поведению DH Climate:

```text
любой open contact          → open
иначе любой unavailable     → unknown
иначе                       → closed
```

Window state **не** меняет demand комнатного термостата. Это device context. В `window_off_devices` нужно помещать только те actuators, которые действительно должны остановиться при открытом окне. Другие thermal devices продолжают нормальную работу.

Unknown для настроенного window state публикуется через aggregate Problem diagnostic.

## FAST devices

FAST devices следуют room demand.

Поддерживаемые domains первой реализации:

- `switch`;
- `climate`.

`fast_heat` и `fast_cool` — списки actuators через запятую. Одна `climate` entity может находиться в обоих списках и тогда трактуется как `heat_cool`. `switch` может находиться только в одном списке.

Reversible `climate` entity в обоих FAST lists также получает legacy cold-weather heating protection. Ниже `ac_min_outdoor_temperature` (default `-10 °C`) App не разрешает ей heating mode, при этом другие допустимые heat sources могут продолжать работу.

## Окна

Контакты окон комнаты опциональны и настраиваются через `window_sensors`.

Window state — **контекст**, а не thermostat truth: открытие окна не переписывает room target и HVAC action. Только devices, явно перечисленные в `window_off_devices`, принудительно выключаются, пока открыто любое настроенное окно. Так сохраняется legacy per-device window-policy без воссоздания слоёв Firewall/Matrix.

Если настроенный window contact unavailable и ни один другой contact не открыт, комната публикует `unknown` через aggregate Problem diagnostic. App не придумывает состояние closed.

## Защита AC при низкой наружной температуре

Reversible FAST `climate` entity, настроенная одновременно в `fast_heat` и `fast_cool`, считается классом AC/heat-pump для legacy low-outdoor-temperature heating limit.

`ac_min_outdoor_temperature` — глобальный safety threshold. Ниже него heating этих reversible devices блокируется. Hard-safety comparison намеренно использует выбранную RAW наружную температуру, а не EMA-filtered значение, поэтому smoothing не может задержать low-temperature protection action.

Cooling не затрагивается. Heating-only switches и SLOW floor thermostats автоматически не классифицируются как AC devices.

## SLOW devices

SLOW предназначен для тёплого пола или другого высокоинерционного comfort loop со своим локальным thermostat и probe.

Для безопасности v0.1 принимает SLOW только как Home Assistant `climate` entities. Они перечисляются в `slow_heat`, и все SLOW thermostats одной комнаты используют отдельный `slow_target` комнаты.

В HEAT season:

```text
hvac_mode = heat
target    = configured SLOW target
```

В COOL или OFF:

```text
hvac_mode = off
```

SLOW target намеренно отделён от room air target.

## Влажность

Humidity control опционален для комнаты и может быть:

- `humidifier`;
- `dehumidifier`.

App публикует нативную Home Assistant entity `humidifier`, содержащую current humidity и target humidity.

Физический actuator может быть `switch` или существующей Home Assistant entity `humidifier`. `humidity_mode` задаётся как `off`, `humidifier` или `dehumidifier`.

Для actuator `humidifier.*` humidity target применяется только пока controller активно увлажняет/осушает. Когда controller неактивен, desired physical state содержит только power-off, поэтому mismatch диапазона target устройства никогда не может заблокировать shutdown command.

## Безопасность и reconciliation

Перед каждым service call App сравнивает desired и actual physical state.

Если state уже совпадает, команда не отправляется. Повторяющиеся mismatches ограничены по частоте/количеству и публикуются через aggregate diagnostic Problem entity.

Перед отправкой climate commands App проверяет reported supported HVAC modes и target limits там, где Home Assistant их предоставляет.

### Диагностический climate logging

Climate diagnostics используют два независимых канала:

- собственный Python log App является authoritative и доступен через Home Assistant App logs;
- важные transitions climate control best-effort зеркалируются в локальный сервис Home Assistant `script.write2climatelog`.

Mirror асинхронен и сериализован через одну bounded FIFO queue, поэтому `climate.log` сохраняет тот же порядок решений, что и App log. Ошибка или отсутствие `script.write2climatelog` никогда не задерживает управление, не создаёт retry pressure и не вызывает Climate Problem.

FAST/SLOW actuator traces содержат desired vs actual state, service calls, bounded retries, вход в cooldown и command confirmation. Стабильные reconciles `desired == actual` намеренно не логируются, поэтому 10-second runtime tick не переполняет `climate.log`.

Room control state логируется только при изменении control signature (season/profile/enabled state/control action/internal control target/window state). Поэтому internal control target виден при FAST debugging без записи каждого неизменившегося tick.

При disconnect Home Assistant cached facts инвалидируются, управление App приостанавливается до получения свежего snapshot.

## Persistence

Persistent state включает:

- season thresholds;
- rolling outdoor samples;
- room profile targets;
- room climate-control enable state;
- previous thermostat action для непрерывности hysteresis;
- humidity targets и control state.

Database не содержит jobs, dispatcher queues или SQL business logic.

## Диагностика

Системный MQTT Device публикует:

- Version;
- Started at;
- Problem.

`Problem` — агрегированный diagnostic binary sensor с machine-readable details в attributes.

## Usage telemetry

Telemetry опциональна и по умолчанию отключена:

```yaml
telemetry_enabled: false
```

При включении App отправляет heartbeat общего DigitalHouses Telemetry Protocol v1. Client payload содержит только:

- protocol schema version;
- telemetry policy version;
- случайный persistent installation UUID;
- product identifier `digitalhouses_climate_app`;
- released App version.

Страна определяется server-side по network metadata. App не отправляет room names, Home Assistant entity IDs, inventory устройств, climate values, targets, local/WAN addresses, identity Home Assistant или MQTT credentials.

Успешный heartbeat обычно отправляется примерно раз в 24 часа с deterministic jitter. Включение telemetry или установка новой released version даёт право на немедленный best-effort heartbeat. Failure использует persisted one-hour backoff и никогда не влияет на climate control или product health.

Отключение telemetry прекращает будущие heartbeats, но не удаляет уже сохранённые server-side данные. Для authenticated deletion данных этой installation используется `button.dh_climate_app_delete_telemetry`.

Development versions, заканчивающиеся на `-local`, никогда не отправляют production telemetry.
