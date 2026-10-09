# DH Climate App — план приёмочного тестирования HAOS

Статус: исторический bundled runtime acceptance для `0.1.21` успешно пройден на реальном HAOS 2026-09-27, происхождение канонического GHCR-артефакта зафиксировано. Текущий `main` (`0.1.26` development) требует нового полного HAOS acceptance. Registry-backed delivery через Supervisor всё ещё не завершён, поскольку пакет App пока не содержит `image:`.

Unit test suite доказывает детерминированные бизнес-правила. Этот план проверяет границы, которые можно доказать только на реальной установке Home Assistant OS: конфигурацию Supervisor, MQTT Discovery, поведение сущностей в UI, выполнение сервисов, persistence, backup и restore.

Для проблем установки/обновления Experimental-канала со сборкой из исходников используйте [docs/EXPERIMENTAL_UPDATE_RUNBOOK.md](docs/EXPERIMENTAL_UPDATE_RUNBOOK.md). Штатные обновления выполняются через `ha store reload`; repository repair предназначен только для явно повреждённого git checkout Supervisor и не должен использоваться как команда refresh.

## 1. Установка и запуск

Acceptance:

- App устанавливается из versioned GHCR image для целевой архитектуры.
- Разрешён первый запуск с пустой конфигурацией.
- App запускается без PostgreSQL и любой внешней базы данных.
- Системный MQTT Device появляется как `DigitalHouses Climate`.
- Диагностики `Version`, `Started at`, `Problem` и telemetry-delete прикреплены к системному Device.
- Если наружный источник не настроен, climate control остаётся безопасно unavailable/OFF и не генерирует команды.

## 2. Наружные источники и фасад сезона

Настроить минимум два источника температуры и, если возможно, два источника влажности.

Acceptance:

- `outdoor_temperature_sources` принимает упорядоченную смешанную цепочку entities `sensor.*` и `weather.*`;
- используется первый валидный источник температуры;
- первый валидный источник влажности выбирается независимо;
- каждое публичное изменение наружной температуры с точностью до одного знака логируется вместе с active source;
- primary unavailable -> выбирается fallback source;
- переключение источника публикует `outdoor_temperature_source_changed` с previous/current source и temperature values;
- после восстановления primary снова становится current source и публикует обратный transition;
- startup/reconnect устанавливает baseline и не создаёт ложный source transition;
- current source/value видимы в season attributes;
- MQTT facade attributes не содержат per-recalculation timestamp `observed_at`;
- при стабильных outdoor temperature/humidity values и sources их `last_updated` в Home Assistant не меняется минимум в течение одного 10-second runtime tick;
- `sensor.dh_climate_app_outdoor_temperature_raw` показывает selected RAW source value, но публикуется не чаще одного раза в минуту;
- hard low-temperature safety продолжает использовать мгновенное выбранное RAW value внутри App и не задерживается Recorder-facing cadence RAW publication;
- `sensor.dh_climate_app_outdoor_temperature` показывает минутную EMA-filtered наружную температуру;
- `sensor.dh_climate_app_outdoor_temperature_avg24` показывает арифметическое среднее persisted минутных filtered samples внутри rolling 24-hour window;
- `sensor.dh_climate_app_outdoor_humidity` показывает текущую выбранную наружную влажность;
- RAW, filtered и avg24 остаются отдельными state-only UI entities без dynamic custom attributes;
- rolling avg24 переживает restart App благодаря persistent sample window и не зависит от Recorder history как источника truth для climate calculation;
- если существует `sensor.avg_outdoor_temperature_24_temp`, его можно использовать как observation oracle, но Recorder/Statistics не является source of truth App;
- отсутствие live outdoor temperature переводит season в OFF, даже если старое avg24 существует;
- lower/red slider сохраняет threshold отопительного сезона;
- upper/blue slider сохраняет threshold сезона охлаждения;
- avg24 ниже lower threshold минус hysteresis -> HEAT;
- avg24 выше upper threshold плюс hysteresis -> COOL;
- между thresholds -> OFF.

## 2.1 Осадки и weather events

Если настроен источник `weather.*`:

- current condition правильно классифицирует rain/snow/mixed/hail/none;
- hourly forecast precipitation публикуется в миллиметрах;
- rain → snow и snow → rain публикуют `precipitation_type_changed`;
- dry → precipitation публикует `precipitation_started`;
- precipitation → dry публикует `precipitation_stopped`;
- MQTT Event payload использует QoS 1 и non-retained;
- initial startup/reconnect устанавливает baseline и не воспроизводит ложный transition;
- transitions season, window и Problem используют тот же контракт `event.dh_climate_app_event`.

## 3. MQTT Device комнаты

Создать одну тестовую комнату.

Acceptance:

- комната появляется как отдельный MQTT Device;
- Device можно вручную назначить правильной Home Assistant Area;
- комната публикует одну `climate` entity;
- не создаются избыточные temperature/humidity sensors только ради дублирования данных термостата;
- несколько настроенных room temperature sensors усредняются;
- unavailable room temperature делает room climate facade unavailable;
- room climate capabilities точно следуют глобальному сезону:
  HEAT -> `off/heat`, COOL -> `off/cool`, OFF -> `off`;
- смена сезона обновляет MQTT Discovery без потери native preset `day/night/away`; новый season-scoped retained preset topic считывается Home Assistant после переподписки на Discovery update;
- включённая комната публикует state `heat` в HEAT season и state `cool` в COOL season; межсезонье публикует `off`;
- HVAC action независимо показывает текущее действие комнаты:
  `heating / cooling / idle / off`;
- OFF season оставляет climate entity доступной при валидной room temperature, публикует HVAC mode `off`, показывает current temperature и не показывает seasonal target;
- target/HVAC commands, отправленные room thermostat во время OFF season, не меняют persisted room control state.

## 4. Профили комнаты и гистерезис

Acceptance:

- day target используется в обычном режиме;
- `night_mode=on` выбирает night;
- `we_at_home=off` выбирает away;
- unavailable настроенный presence input трактуется как away;
- выключение room climate в HEAT показывает HVAC off, но внутренне использует antifreeze target;
- выключение room climate в COOL даёт настоящий off;
- выбор profile в thermostat работает как временный edit overlay;
- изменение target при выбранном другом profile записывает target этого profile;
- profile edit overlay возвращается к effective profile после idle timeout;
- targets переживают restart App;
- внутри hysteresis band предыдущее active/idle action переживает и recalculation, и restart App.

## 5. Выполнение FAST

По возможности проверить и switch, и climate actuator.

Acceptance:

- heating demand включает FAST heat switch;
- idle/off выключает его;
- cooling demand активирует только настроенные FAST cooling devices;
- FAST climate получает правильный HVAC mode; реверсивный FAST climate получает автоматически рассчитанный физический target с учётом комнатного target, фактической room temperature и физических min/max/step;
- уже корректное physical state не создаёт дублирующий service call;
- unsupported HVAC mode или target вне range не отправляются вслепую;
- unavailable physical entity создаёт Problem diagnostic вместо tight retry loop;
- App log показывает FAST desired/actual, CALL, SENT, retry/cooldown, VERIFIED_HA и delayed DRIFT transitions; строка executor CONFIRMED не создаётся;
- локальный `climate.log` получает те же выбранные traces через `script.write2climatelog` в порядке решений App;
- повторные already-correct reconciles не создают log spam;
- ошибка локального climate-log mirror не меняет actuator control или Problem state.

## 6. Выполнение SLOW тёплого пола

Использовать физический wall/floor thermostat с собственным локальным floor или slab probe.

Acceptance:

- HEAT season переводит физический thermostat в `heat`;
- App отправляет настроенный `slow_target`, а не room air target;
- циклирование room thermostat не переключает SLOW heat постоянно on/off;
- физический thermostat локально циклирует relay по собственному probe;
- COOL/OFF переводит SLOW thermostat в `off`;
- потеря/restart App оставляет физическому thermostat возможность регулировать по последнему локальному setpoint до восстановления Home Assistant control.

## 7. Контекст окна

Если возможно, настроить минимум два window contacts.

Acceptance:

- любой open contact -> room `window_state=open`;
- все contacts closed -> `closed`;
- ни один не open и один unavailable -> `unknown`;
- window state не меняет HVAC demand комнатного термостата;
- при open окне принудительно off переводятся только actuators из `window_off_devices`;
- остальные actuators продолжают нормальную policy;
- unknown настроенного window state создаёт warning Problem.

## 8. Защита reversible climate при холоде

Использовать reversible `climate` entity одновременно в `fast_heat` и `fast_cool`.

Acceptance:

- выше `ac_min_outdoor_temperature` heating demand может использовать reversible climate device;
- ниже threshold это устройство удерживается off для heating;
- другой разрешённый heat source продолжает работу;
- cooling не блокируется heating-only low-temperature rule.

## 9. Влажность

Для комнаты с humidity control:

- MQTT entity `humidifier` появляется на том же room Device;
- current и target humidity корректны;
- направление humidifier/dehumidifier соответствует config;
- humidity hysteresis предотвращает chatter;
- target changes переживают restart;
- humidity control можно отключить независимо от thermal season;
- если humidity control не настроен, соответствующая entity не создаётся.

## 10. Disconnect и recovery

Acceptance:

- потеря Home Assistant connectivity помечает climate facades unavailable;
- cached sensor truth отбрасывается;
- пока HA truth disconnected, физические команды не отправляются;
- reconnect получает fresh snapshot до возобновления нормального control;
- старые buffered events не могут перезаписать более новый snapshot state;
- MQTT reconnect восстанавливает subscriptions и retained facade state;
- stale retained command messages после restart не меняют runtime settings.

## 11. Telemetry

Предлагаемый development-код `0.1.27` всё ещё является baseline policy v1. Нельзя объявлять policy v2 release-ready, пока production deployment `telemetry.digitalhouses.vip` независимо не подтверждён как DigitalHouses Stats `0.4.1+`.

Финальный acceptance policy v2 должен проверить:

- отсутствует пользовательский opt-out `telemetry_enabled`;
- wire schema остаётся `1`, а `telemetry_policy_version=2`;
- payload содержит только schema, policy version, persistent UUIDv4, `digitalhouses_climate_app` и released App version;
- country отсутствует в client payload и определяется только server-side;
- UUID/token переживают restart, upgrade и поддерживаемый backup/restore;
- нормальная cadence около 24h ±30 минут с неагрессивным failure retry;
- fresh install и новая released version могут отправить один immediate best-effort heartbeat;
- development/local builds никогда не попадают в production statistics;
- failure telemetry-server/DNS/firewall никогда не влияет на climate runtime или Problem health;
- authenticated Delete удаляет server history, ротирует локальные UUID/token, после чего дальнейшее использование продукта возобновляет reporting под новой identity.

## 12. Backup и immutable delivery

Acceptance после подключения registry-backed delivery в `config.yaml`:

- установленный App использует `ghcr.io/digitalhouses/digitalhouses_climate_app:<version>`;
- Supervisor backup с Climate App, полный или App-only partial, содержит persistent state `/data`;
- restored App сохраняет season thresholds, room targets, humidity targets и telemetry installation identity;
- backup не включает локально собранный application image;
- restore поддерживаемого текущего production release получает требуемый опубликованный registry image.

Restore исторической версии после выхода более нового релиза не является общим требованием immutable-delivery acceptance. Downgrade/rollback проверяется только если конкретный migration/recovery plan этого требует.

## 13. Решение о релизе

Блок ниже — историческая запись acceptance опубликованного `0.1.21`; он не означает acceptance текущего development-кода `0.1.26`.

Последний завершённый released runtime acceptance (`0.1.21`):

```text
repository CI = green
container build = green
real HAOS update/start = green
recorder churn guard = green
stable outdoor last_updated across runtime tick = green
outdoor temperature avg24 sensor = green
outdoor temperature change log = green
outdoor primary -> backup failover = green
outdoor source-switch Event = green
outdoor preferred-source recovery = green
HEAT modes off/heat only = green
COOL modes off/cool only = green
OFF modes off only = green
room day/night/away presets = green
preset reset to automatic profile = green
FAST heat/cool execution = green
target_out_of_range safety = green
no_confirmation/retry/cooldown = green
SLOW thermostat path = green
window context = green
cold-weather reversible climate protection = green
humidity safe shutdown = green
restart/reconnect = green
Climate-App-only backup/restore = green
final clean baseline = green
immutable release publication = green
```

Зафиксированный live acceptance см. в [docs/ACCEPTANCE_0.1.21.md](docs/ACCEPTANCE_0.1.21.md).

Опубликованный артефакт: `digitalhouses_climate_app-v0.1.21` / `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.21` / `sha256:5870a9e2791fadc76165f2a5c604cf7d1f84d7448de5e5401721be2a63045349`.

Эта запись не закрывает оставшийся registry-delivery gap: в `config.yaml` всё ещё отсутствует `image:`. Изменения `0.1.27` требуют нового полного HAOS acceptance до любого релиза. Дефекты, найденные в HAOS acceptance, исправляются новым commit/version; опубликованная immutable image version никогда не перезаписывается другим содержимым.
