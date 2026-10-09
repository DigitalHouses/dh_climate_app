# История изменений

## 0.1.27 — разработка

- Автоматическая физическая уставка для реверсивных FAST climate в зависимости от комнатной цели и температурной ошибки: без новых YAML-опций, MQTT Number и ручных offset.
- Уставка фиксируется в пределах одного активного цикла; при отсутствии прогресса за 20 минут допускается одна дополнительная ступень HEAT/COOL, в границах физических min/max/step устройства.
- Для SmartIR отправка режима и уставки объединена в один вызов climate.set_temperature, предотвращая два последовательных ИК-пакета.
- Unit-тесты покрывают оба режима, сохранение одной цели при sensor updates, ограничение возможностей устройства, отсутствие прогресса, перезапуск цикла и комбинированную SmartIR-команду.
- Новый код требует CI и отдельного live HAOS acceptance; production не обновлён.

## 0.1.26 — разработка

- Добавлен единый pipeline обработки наружной температуры и для обычного шума источника, и для ступеней при provider/sensor failover: выбранная RAW temperature → минутная EMA → публичная filtered temperature → rolling avg24 → season.
- Добавлен настраиваемый `outdoor_temperature_ema_minutes` с default 20 минут и жёсткой минимальной cadence фильтра/samples в одну минуту.
- Добавлен диагностический `sensor.dh_climate_app_outdoor_temperature_raw`; RAW, filtered и avg24 temperature sensors используют state-only MQTT contracts без custom dynamic attributes.
- Публикация RAW diagnostic MQTT sensor ограничена максимум одним разом в минуту; внутренняя RAW temperature остаётся мгновенной для low-temperature safety, logs и source-change events.
- Avg24 изменён на арифметическое среднее persisted минутных filtered samples, устраняя зависимость от нерегулярной частоты обновления weather provider. Существующая pre-EMA history при upgrade один раз преобразуется через EMA.
- Hard low-temperature AC heating protection сохранена на выбранной RAW temperature, поэтому smoothing не может задержать safety behavior `ac_min_outdoor_temperature`.
- Recorder history удалена из зависимостей климатического расчёта; Recorder остаётся поверхностью наблюдения/истории для публичных RAW, filtered и avg24 sensors.
- Изменение выровнено с нормативными стандартами разработки DigitalHouses из `DigitalHouses/home-assistant-apps`.

## 0.1.25 — разработка

- Bootstrap filtering Recorder выровнен с нативным Home Assistant Statistics: из History запрашиваются только significant/state changes вместо принудительного `significant_changes_only=0`.
- Это исключает Recorder rows, где state наружной температуры не менялся, а менялись только attributes, предотвращая bias 24-hour arithmetic mean из-за повторных одинаковых samples.
- Startup deduplication 0.1.24, bootstrap для пустой history, runtime sampling и поведение humidity оставлены без изменений.
- `sensor.avg_outdoor_temperature_24_temp` сохранён как live acceptance oracle; после restart App avg24 должен совпадать с ним до 0.1 °C.

## 0.1.24 — разработка

- Исправлен оставшийся gap совместимости с Home Assistant Statistics при startup App: если Recorder history уже содержит текущее canonical outdoor-temperature value, startup snapshot больше не вставляет то же значение второй раз в 24-hour mean.
- Runtime transition baseline инициализируется самым новым restored Recorder sample, поэтому действительно новое live temperature всё ещё добавляется немедленно, а идентичное startup value дедуплицируется.
- Контракт пустой history не изменён: первая live outdoor temperature становится первым sample avg24.
- Добавлено regression coverage для startup deduplication и настоящего live transition сразу после Recorder bootstrap.

## 0.1.23 — разработка

- Outdoor temperature `avg24` приведён к startup semantics Home Assistant Statistics `state_characteristic: mean` / `max_age: 24h` вместо опоры только на private SQLite sample history App.
- При каждом Home Assistant snapshot/reconnect temperature sample window перестраивается из Recorder history `sensor.dh_climate_app_outdoor_temperature`, исключая pre-window baseline так же, как Statistics.
- Если Recorder не содержит пригодной history, mean bootstrap выполняется от текущей live outdoor temperature; искусственное historical value не создаётся.
- Во время runtime sample берутся те же переходы публичной наружной температуры с одним знаком, которые видит Home Assistant, поэтому raw source precision или source-only switches не могут смещать mean относительно Statistics oracle.
- Outdoor humidity сохраняет существующий time-weighted путь; semantics season thresholds и hysteresis не меняются.
- Unit/live acceptance расширен так, чтобы временный `sensor.avg_outdoor_temperature_24_temp` можно было использовать как опциональный oracle 0.1 °C на HAOS.

## 0.1.22 — разработка

- Outdoor temperature `avg24` изменён в соответствии с Home Assistant Statistics `state_characteristic: mean`: простое арифметическое среднее persisted temperature samples внутри rolling 24-hour window.
- Pre-window baseline sample удалён из temperature mean, поэтому значения старше 24 часов не могут влиять на выбор season.
- Outdoor humidity оставлена на существующем time-weighted rolling average; season thresholds, hysteresis и semantics `decide_season()` не изменены.
- Добавлено regression coverage для irregular sample spacing, исключения за пределами 24-hour window, SQLite restart durability и season transition по новому mean.

## 0.1.21 — 2026-09-27

- Уменьшен Home Assistant Recorder churn от MQTT facades Climate App за счёт удаления per-recalculation timestamp `observed_at` из entity attributes.
- Topics attributes наружной температуры и влажности разделены, поэтому изменение одного source/value больше не обновляет несвязанные outdoor entities; avg24 sensor больше не содержит dynamic JSON attributes.
- Topics attributes precipitation type и precipitation amount разделены, поэтому weather-condition changes и hourly amount metadata больше не переписывают обе entities одновременно.
- Public season humidity attributes округляются до одного знака, как и public temperature precision, чтобы незначимый floating-point drift не превращался в Recorder rows.
- Добавлено regression coverage, доказывающее, что продвижение observation clock на 10 секунд при неизменных публичных climate/weather data не создаёт второй MQTT publication.
- Bundled live HAOS acceptance успешно пройден 2026-09-27, включая Recorder churn guard: стабильные facades наружной температуры/влажности сохранили одинаковые `last_updated` между runtime ticks, при этом полный suite source failover, room climate, safety, backup/restore и clean baseline остался green.

## 0.1.20 — 2026-09-27

- Добавлена наблюдаемость источника наружной температуры: каждое публичное изменение температуры до одного знака логируется вместе с текущим active source.
- Добавлены явный source-switch log и machine Event `outdoor_temperature_source_changed` с previous/current source и temperature values.
- Подтверждён и документирован существующий ordered fallback contract: `outdoor_temperature_sources` принимает смешанный список `sensor.*` и `weather.*` через запятую; побеждает первый текущий валидный source, preferred source автоматически возвращается после recovery.
- HAOS acceptance расширен deterministic primary/backup outdoor sources, failover, preferred-source recovery, assertions логов и source-change Event.
- Bundled live HAOS acceptance успешно пройден 2026-09-27, включая primary→backup failover, preferred-source recovery, temperature-change logging, source-switch logging/Event payloads, существующий room-climate/safety suite, App-only backup/restore и final clean baseline.

## 0.1.19 — 2026-09-27

- Добавлена отдельная entity `sensor.dh_climate_app_outdoor_temperature_avg24` для существующего time-weighted 24-hour average наружной температуры App.
- Sensor использует тот же persisted rolling average Climate Core, публикует °C с точностью до одного знака и не создаёт второй calculation path.
- Bundled live HAOS acceptance успешно пройден 2026-09-27; новый avg24 sensor совпал со значением `avg_24h_temperature` season facade, полный существующий safety/backup suite остался green.

## 0.1.18 — 2026-09-27

- Восстановлены season-specific capabilities room Climate: HEAT показывает только `off / heat`, COOL — только `off / cool`, interseason — только `off`.
- Нативные presets `day / night / away` сохраняются между MQTT Discovery updates благодаря season-scoped retained preset-state topics и публикации authoritative preset до Discovery payload.
- Из room thermostat удалён видимый пользователю HVAC mode противоположного сезона, при этом runtime rejection невалидных opposite-season commands сохранён.
- Bundled live HAOS acceptance успешно пройден 2026-09-27, включая точные seasonal `hvac_modes`, сохранение native presets при HEAT → COOL → OFF, target-range safety, bounded no-confirmation retry/cooldown, SLOW, window context, cold-weather reversible protection, humidity safe shutdown, App-only backup/restore и final clean baseline.

## 0.1.17 — 2026-09-27

- Восстановлена нативная семантика room thermostat: room state `heat` в HEAT season, `cool` в COOL season и `off` в interseason.
- Восстановлены native Climate presets `day / night / away` вместо misuse fan-speed semantics; зарезервированная команда Home Assistant `none` очищает временный profile-edit overlay.
- Восстановлен короткоживущий profile-edit overlay, позволяющий выбрать и редактировать target неактивного profile через room thermostat без изменения автоматического day/night/away control source.
- `hvac_action` оставлен независимым от HVAC mode и показывает фактическое действие `heating / cooling / idle / off`.
- MQTT Climate capabilities комнаты оставлены стабильными `off / heat / cool` при season transitions, чтобы Home Assistant не пересоздавал Climate entity и не сбрасывал native preset state в `none`.
- HAOS acceptance harness усилен ожиданием numeric room-target и season baseline после App update до создания baseline backup.
- Bundled live HAOS acceptance успешно пройден 2026-09-27, включая native room heat/cool/off state, day/night/away presets, preset reset, target range protection, bounded no-confirmation retry/cooldown, SLOW, window context, cold-weather reversible protection, humidity safe shutdown и App-only backup/restore.

## 0.1.16 — неопубликованный кандидат

- Промежуточный кандидат HAOS validation для native room Climate UI. Заменён 0.1.17 до immutable publication.

## 0.1.15 — 2026-09-27

- Исправлена безопасность shutdown humidifier: неактивные `humidifier.*` actuators больше не несут target-humidity command, поэтому out-of-range target не может заблокировать `turn_off`.
- Добавлено cross-module humidity safety coverage для active target application, независимого отключения humidity и shutdown неактивного device.
- Добавлено cold `/data` durability coverage для season thresholds, room targets/control state, humidity targets/control state, hysteresis continuity и telemetry installation identity.
- Добавлено bundled actuator/safety acceptance coverage для SLOW floor, window inhibition, cold-weather reversible climate protection, target range blocking и retry/cooldown recovery.
- Bundled live HAOS runtime acceptance успешно пройден 2026-09-27, включая target range blocking, bounded no-confirmation retry/cooldown recovery, SLOW, window context, cold-weather protection, humidity safe shutdown и Supervisor backup/restore только Climate App.

## 0.1.14 — разработка

- Успешный Home Assistant service call отделён от verification device state: успешные calls теперь логируются как `SENT`, никогда как `CONFIRMED`.
- Добавлен event-driven delayed HA-state verification: post-command `state_changed` запускает settle window, и только последующий matching state становится `VERIFIED_HA`.
- Добавлен delayed drift detection для ранее стабильного actuator state до отправки corrective commands.
- Сохранён bounded no-event watchdog/retry path; последняя попытка retry получает полное confirmation window до перехода в cooldown.
- Transient verification evidence сбрасывается при disconnect Home Assistant.

## 0.1.13 — разработка

- Best-effort mirror `script.write2climatelog` сериализован через одну asynchronous queue, чтобы `climate.log` сохранял порядок решений.
- Authoritative App log остаётся мгновенным, climate control — non-blocking.
- Добавлена bounded mirror queue, предотвращающая неограниченный рост памяти при недоступном local log script.

## 0.1.12 — разработка

- Исправлены обновления season range из Home Assistant thermostat `heat_cool`: paired lower/upper MQTT commands теперь coalesced и валидируются атомарно.
- Порядок сообщений `target_temp_low` / `target_temp_high` больше не важен.
- Single-threshold edits остаются поддержанными, invalid final ranges по-прежнему отклоняются.

## 0.1.11 — разработка

- Добавлен dual-channel Climate diagnostic logging: authoritative App log + asynchronous best-effort mirror в локальный `script.write2climatelog`.
- Добавлено transition-based room control logging и FAST/SLOW execution traces для desired/actual state, service calls, bounded retries, cooldown и confirmation без per-tick already-correct spam.
- Ошибки climate-log mirror изолированы от climate control, retries и Problem state.
- Actuator Problems сохраняют `room_id`, где применимо, поэтому существующие events `problem_started` / `problem_recovered` содержат достаточно room context для будущих local notifications.

## 0.1.10 — разработка

- Все публичные temperature values App стандартизированы до одного знака.
- Внутренние climate calculations сохраняют полную precision; округление применяется только на границах presentation Home Assistant, MQTT и machine events.
- Округляются current/avg24 outdoor temperature, season thresholds и temperature fields semantic events.

## 0.1.9 — разработка

- Добавлены отдельные UI sensors для current outdoor temperature и humidity.
- Outdoor UI sensors используют те же priority/fallback sources, что Climate Core, и никогда не заменяют current values значениями avg24.
- Source и avg24 context добавлены в sensor attributes.

## 0.1.8 — разработка

- Поведение room climate в interseason изменено с unavailable на readable-Off: current room temperature остаётся видимой, seasonal target не публикуется, а room thermostat commands игнорируются при season OFF.
- Добавлено normalized precipitation state из настроенных `weather.*` sources: current precipitation type + forecast precipitation amount текущего часа в миллиметрах.
- Добавлена одна MQTT Event entity schema v2 для semantic Climate transitions, первоначально season, precipitation, windows и aggregate Problem start/recovery; events используют QoS 1, retain=false и не replay после reconnect.
- Добавлена явная классификация rain/snow/mixed/hail и events переходов rain↔snow без генерации шума обычных thermostat cycles.

## 0.1.7 — разработка

- Исправлена migration availability profile target Number после interseason-изменения 0.1.6. Существующие MQTT Discovery entities теперь явно заменяют старый room-dependent availability list на system-only availability, поэтому target settings остаются редактируемыми, пока room thermostats unavailable между сезонами.

## 0.1.6 — разработка

- Room thermostats намеренно unavailable при global season `OFF`, чтобы пользователи не меняли неактивный thermostat в межсезонье.
- Profile target configuration Number entities остаются доступны независимо, чтобы seasonal targets можно было подготовить заранее.

## 0.1.5 — разработка

- Room climate facade переработан для Apple Home/HomeKit: стабильные HVAC modes `off / auto`, без fan/preset semantics; thermostat target всегда редактирует текущий активный profile `day / night / away`.
- User-facing scheduled target отделён от internal HEAT antifreeze control target, поэтому выключение комнаты не показывает antifreeze setpoint как normal thermostat target.
- Временный Profile select заменён hidden-by-default configuration Number entities для Heat/Cool Day/Night/Away targets и Heat antifreeze target; старая retained select Discovery entry автоматически удаляется при upgrade.

## 0.1.4 — разработка

- Room profiles полностью удалены из MQTT Climate presets. Каждая комната публикует отдельную entity `select` Profile ровно с `day / night / away`, чтобы thermostat оставался обычной native climate entity и Home Assistant больше не добавлял reserved preset `none` в UI.

## 0.1.3 — разработка

- Reserved MQTT climate preset `none` Home Assistant трактуется как reset временного room profile overlay с возвратом к автоматически выбранному profile `day / night / away`.

## 0.1.2 — разработка

- `fan_modes` room thermostat заменены на native climate `preset_modes` (`day / night / away`), чтобы Apple Home и другие thermostat consumers сохраняли native thermostat semantics; `antifreeze` остаётся внутренней защитой.
- Добавлена прямая поддержка `weather.*` как sources наружной температуры и влажности через current weather attributes.
- Создана компактная Python architecture на основе поведения DH Climate 5 без PostgreSQL orchestration, Matrix, Dispatcher, UC, Confirmator и SQL business logic.
- Добавлен входной адаптер Home Assistant Supervisor REST/WebSocket с reconnect по subscribe-before-snapshot и защитой от stale events.
- Добавлено recovery MQTT reconnect с восстановлением subscriptions, retained Discovery/state и online availability после restart broker.
- Исправлена race condition startup/reconnect MQTT subscription set, наблюдавшаяся на реальном HAOS.
- Включено Supervisor API permission, необходимое для startup timezone lookup.
- Добавлены независимые priority chains sources наружной температуры и влажности.
- Добавлены persisted rolling 24-hour outdoor averages и расчёт глобального season `HEAT / COOL / OFF`.
- Добавлен MQTT Discovery season thermostat `heat_cool` с двумя thresholds и persisted thresholds сезонов heating/cooling.
- Добавлены отдельный MQTT Device и room `climate` facade для каждой настроенной комнаты.
- Добавлены target profiles `day / night / away / antifreeze` и legacy short-lived profile-edit overlay.
- Добавлен один общий temperature hysteresis дома и persisted stateful room thermostat action.
- Добавлена прямая FAST heat/cool policy для Home Assistant `switch` и `climate` entities.
- Добавлен SLOW floor/comfort control через local `climate` thermostats с отдельным SLOW target.
- Добавлены optional per-room humidifier/dehumidifier facade и direct actuator control с отдельным humidity hysteresis.
- Добавлены optional aggregation window contacts комнаты и per-device open-window shutdown policy.
- Добавлена legacy cold-weather heating protection для reversible FAST climate devices с default `-10 °C`.
- Добавлены idempotent Home Assistant service reconciliation, capability/range checks, bounded retry и cooldown.
- Добавлены aggregate `Problem` diagnostic, а также diagnostics `Version` и `Started at`.
- Добавлено fail-safe поведение для unavailable outdoor temperature, room sensors, disconnect Home Assistant и unavailable presence input.
- Добавлена lightweight SQLite persistence для season thresholds, outdoor samples, room targets, humidity targets и hysteresis continuity.
- Добавлен client DigitalHouses Telemetry Protocol v1 с persistent installation credentials, daily jittered heartbeat, one-hour failure backoff и authenticated deletion.
- Добавлены плоская Supervisor-compatible App configuration, английская/русская локализация UI и пользовательская документация.
- Добавлен immutable multi-architecture GHCR delivery workflow и validation canonical release tag.
- Добавлены architecture-specific Home Assistant image labels, чтобы manifest variants amd64 и aarch64 публиковали canonical HA architecture names.
- Добавлена автоматическая CI validation unit, contract, shell, Python compile и container build.
