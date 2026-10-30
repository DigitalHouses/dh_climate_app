# История изменений

## 0.2.9 — 2026-10-30

- Исправлена критическая ошибка контекста датчиков окон:
  Picker для window теперь ищет **binary_sensor**, а не sensor.
  Глобальные метрики вида sensor.count_binary_sensor больше не
  предлагаются в качестве оконных контактов.
- Классификация температуры стала строгой: по умолчанию показываем
  device_class=temperature и неклассифицированные датчики с единицей
  °C/°F/K. Сенсоры версии ПО, активности и другие посторонние
  сущности больше не засоряют список.
- Для влажности/окон по умолчанию учитывается соответствующий
  device_class. Остальные типы и сенсоры без класса доступны только
  после явного включения расширенного поиска; domain остаётся строгим.
- Уже привязанные, но не подходящие фильтру сущности не исчезают
  из списка. Несовместимый domain явно отмечается красным,
  подтверждение привязки блокируется до удаления неверного выбора.
- Подсказки «по одному entity_id в строке» убраны из форм.
  Используемые в других комнатах ID показывают собственное
  имя комнаты DH Climate, если оно задано. Фильтр HA Area умеет
  учитывать локализованную подпись комнаты при точном совпадении.
- Climate Engine, MQTT, YAML, SQLite, manifest и принятые
  инженерные идентификаторы не изменены.

## 0.2.8 — 2026-10-30

- Реализован единый **HA Entity Picker** для привязок датчиков
  температуры/влажности/окон, комнатных исполнительных устройств,
  внешнего температурного датчика виртуального регулятора.
- При открытии Picker разово запрашиваются Home Assistant states,
  Entity/Device/Area Registry, с 30-секундным кешем и без
  подписки на глобальный state_changed.
- Доступны поиск по имени/entity_id/устройству, фильтры HA Area,
  допустимых domain, доступности и классификации device_class.
  Автоматический контекстный фильтр не пропускает неподходящий
  домен (hardware требует climate.*, virtual — switch.* или climate.*).
- Множественный выбор датчиков и одиночный выбор устройств;
  существующие, даже отсутствующие в каталоге, привязки сохраняются
  до явного удаления. Указана существующая связь с комнатой.
- Каталог возвращает только ограниченные поля, без произвольных
  HA attributes; доступ к API только администратору через доверенный
  HAOS Ingress. В каталоге нет записи, HA service calls не выполняются.
- Результат Picker изменяет только локальную форму и далее обычный
  черновик Draft → Validate → Apply. До сохранения/применения
  конфигурации климатические регуляторы не меняются.
- Climate Engine, manifest SoT, SQLite, MQTT identities и
  политика управления исполнительными устройствами не изменены.

## 0.2.7 — 2026-10-30

- DH Climate Explorer получил собственные русские и английские
  имена комнат, датчиков, исполнителей и ресурсов через ПКМ
  «Изменить имя». Для справки в карточке показывается имя в HA,
  имя из конфигурации и исходный технический ID.
- UI-подписи сохраняются отдельно в
  /data/dh_climate_ui_labels.json (атомарно, с revision и блокировкой
  конфликтующих записей); не меняют /data/options.json,
  манифест Engine, HA friendly_name, SQLite или MQTT.
- Отображаемое имя выбирается в порядке: DH locale override →
  HA friendly_name → имя из конфигурации → ID.
- Сохранение подписи работает немедленно и **не требует**
  Draft/Validate/Apply, перезапуска приложения или Climate Engine.
- API для чтения названий доступно через Ingress; запись только
  системному администратору с теми же проверками доверенного
  Supervisor proxy, CSRF и формата JSON.
- Системные названия и FAST_HEAT/FAST_COOL/VIRTUAL/HARDWARE
  по-прежнему живут в своих словарях и не затрагиваются.

## 0.2.6 — 2026-10-30

- В Explorer дерево системных объектов и ресурсов локализуется через
  действующие ru/en словари: Система, Погода, Дом, Ресурсы, Сезон,
  Комнаты, Котёл; машинные идентификаторы остаются неизменными.
- Для HA-датчиков, исполнителей и комнатной climate-сущности
  read-only projection использует атрибут Home Assistant
  friendly_name, если он задан; иначе показывает существующее
  имя комнаты / entity_id. Никакого перевода по догадке.
- Breadcrumbs и заголовки карточек следуют той же логике имён.
  Оригинальный entity_id доступен в карточке, Inspector, подсказке
  по наведению и действии «Копировать entity_id».
- Данные friendly_name поступают из уже имеющихся HA states;
  дополнительные запросы к HA, конфигурация для хранения псевдонимов,
  новые MQTT-сущности, миграция или перезапись Supervisor options
  не нужны. Секретные атрибуты HA не копируются в Ingress.
- Технические классы FAST_HEAT, FAST_COOL, FAST_HEAT_COOL,
  SLOW_HEAT, VIRTUAL, HARDWARE по-прежнему не переводятся.
- Climate Engine, SQLite, MQTT, права редактирования,
  Draft/Validate/Apply не изменены.

## 0.2.5 — 2026-10-30

- Контекстное меню Explorer содержит только действия над выбранным объектом:
  удалены пункты «Открыть» и «Развернуть/Свернуть», дублировавшие
  обычный клик и стрелку дерева. Если для объекта действий нет,
  пустое меню не появляется.
- «Копировать entity_id» сохранено для датчиков и устройств.
  Правила прав администратора, Draft/Validate/Apply не изменены.
- После «Отмена» в редакторе больше не остаётся красное
  предупреждение «Перед переходом сохраните форму…» в списке комнат.
- Изменения ограничены интерфейсом; логика управления климатом,
  SQLite, MQTT, manifest и Supervisor options не затронуты.

## 0.2.4 — 2026-10-30

- Левая панель Explorer получила настоящую перемещаемую границу.
  Ширина меняется мышью (190–1100 px с учётом доступной ширины)
  и сохраняется локально в браузере. Двойной клик по границе
  сбрасывает её к 275 px. Предусмотрено управление с клавиатуры.
- Удалён постоянный символ + в дереве. На любом узле
  работает компактное контекстное меню по правому клику.
  Для ROOMS — создание комнаты, для комнаты —
  добавить устройство / изменить / удалить; для устройств —
  изменить / удалить. Права определяются текущим backend API.
- Меню поддерживает открытие объекта, раскрытие ветвей,
  копирование entity_id там, где оно применимо;
  закрытие по Escape и нажатию вне меню, вызов Shift+F10.
  В центральной карточке больше нет дублирующих кнопок CRUD.
- Climate Engine, MQTT, SQLite, manifest, права доступа,
  Draft/Validate/Apply и формат конфигурации не изменены.

## 0.2.3 — 2026-10-30

- Единый Explorer получил реальное административное создание, изменение
  и удаление комнат и их исполнительных устройств; редактирование
  temperature/humidity/window sensors из карточки комнаты.
- ROOMS и ветки устройств показывают кнопку + только после
  серверного подтверждения прав. Черновики сохраняются в /data.
- Утверждён механизм Draft → Validate → Apply: глобальный revision,
  SHA-256 base, защита от конфликтов, строгая валидация текущим
  parse_options(), атомарная запись, резерв предыдущего манифеста.
- Apply **не перезапускает** климат и не меняет действующий Runtime:
  новый манифест активируется только после явного перезапуска App.
  Состояние pending restart видно в UI. Ошибочный активный манифест
  не приводит к автоматическому запуску по другой топологии.
- Ingress доступен авторизованным пользователям (panel_admin: false);
  API записи проверяет доверенный Supervisor peer, HA user ID,
  группу system-admin, CSRF-маркер и JSON size/type.
- Существующий формат Supervisor options, SQLite, MQTT identities и
  климатические алгоритмы остаются прежними. Редактирование ресурсов
  и создание насосов/контуров — следующий этап, без отдельного UI.

## 0.2.2 — 2026-10-30

- Вместо отдельных Activity Bar и Navigation реализован один
  **DH Climate Explorer** в стиле VS Code: раскрываемые узлы, выбор
  объекта одним нажатием, контекстные дочерние узлы и breadcrumbs.
- Центральная область показывает полный контекст выбранной комнаты:
  комнатный термостат, фактические датчики, исполнительные устройства
  и диагностические Problems. Для ресурсов доступны насосы и контуры,
  если они реально конфигурированы; источник отопления остаётся видимым
  и без собственной телеметрии.
- Inspector скрыт по умолчанию; Explorer можно скрывать и менять ширину.
  На малом экране дерево открывается поверх основной области.
- Технические термины FAST_HEAT, FAST_COOL, FAST_HEAT_COOL, SLOW_HEAT,
  VIRTUAL, HARDWARE не переводятся. Остальные подписи — ru/en.
  Уточнена визуализация недоступного и отсутствующего hvac_action.
- Web UI остаётся **read-only**: никаких незавершённых кнопок «Создать»,
  скрытых записей конфигурации, второго backend SoT или изменений Engine.
  Реальные server-side permissions, Draft/Validate/Apply — отдельный
  следующий этап на той же структуре Explorer.
- Формат Supervisor YAML 0.2.0/0.2.1, SQLite, MQTT, управление FAST/SLOW
  и безопасности исполнительных устройств не изменены.

## 0.2.1 — 2026-10-29

- Первый read-only **Ingress Operations Workbench**: System, Weather,
  Home, Resources, Season, Rooms и устройства комнат. UI не управляет
  климатом и не зависит от HA Area.
- Небольшой HTTP/SSE backend на port 8099: данные из текущего Runtime,
  только GET, доступ исключительно через Supervisor Ingress. Состояния
  HA offline не отображаются как действующие.
- Перевод интерфейса ru/en через словари с возможностью расширения,
  Inspector, копирование entity_id и адаптация под разные размеры экрана.
- Новый конфигуратор, запись в /data, оборудование без HA entities,
  Channels/Ports, паспорта и физические связи перенесены в roadmap.
- Supervisor options, SQLite targets, MQTT IDs и алгоритмы FAST/SLOW
  не изменены. Live HAOS Ingress smoke — отдельная обязательная приёмка.

## 0.2.0 — 2026-10-28

- Несовместимый **новый Supervisor YAML**: `device_type: virtual|hardware`
  вместо `control: app|device`. Роли `fast_heat`, `fast_cool`, `slow_heat`
  независимы от типа регулятора; один реверсивный AC остаётся одним устройством.
- Для каждого **SLOW_HEAT VIRTUAL** требуется явная
  `screed_sensor_unavailable: open|closed`, как при отсутствии датчика стяжки
  по проекту, так и при его отказе. Сохранены NO/NC, сезонные ограничения,
  SLOW targets и таймеры; для потери существующего датчика сохраняется Problem.
- Окно блокирует **только FAST_COOL**, включая охлаждение реверсивного
  устройства, через `window_open_delay_seconds`: глобальная MQTT Number,
  SQLite seed 10 сек, диапазон 0–300 сек; отменяемая event-driven выдержка.
  FAST_HEAT и SLOW_HEAT не закрываются оконной политикой.
- Глобальные `heating_source: boiler|central_heating` и `vrf: on|off`;
  ресурсные запросы разрешены только явно связанным устройствам
  (`resource: home_heating|vrf|independent`). Нет выдуманных входов,
  нулевой телеметрии и команд запускать котёл/насосы из Demand.
- MQTT Demand: независимые ROOM, HARDWARE, VIRTUAL и вычисляемые
  `BOILER_HEAT_REQUEST` / `CENTRAL_HEAT_REQUEST` / `VRF_COOL_REQUEST`.
  Прежние диагностические DEVICE/ACTUAL discovery удаляются.
  `REQUEST` не тождественен обратной связи SALUS.
- Полное дерево в штатном Lovelace Markdown из единого read-model:
  HOME → BOILER либо CENTRAL_HEATING, необязательные агрегатор/насосы/
  контуры, общая VRF телеметрия при наличии; комнатные FAST/SLOW
  остаются под Room Climate. Кликабельные HA More Info ссылки,
  непрерывные соединительные линии и плотный `<pre>`.
- Использовать полную новую конфигурацию из
  `examples/dh_climate_app_0.2.0_options.yaml`. SQLite /data и действующие
  комнатные MQTT climate/целевые уставки сохраняются; **миграции YAML нет**.
  До HAOS acceptance считать выпуск экспериментальным.


## 0.1.33 — 2026-10-28

- Добавлено агрегирование запросов ROOM HEAT/COOL строго по {hvac_mode, hvac_action} комнатных термостатов (гистерезис уже внутри ROOM), без зависимости от физических устройств.
- Добавлен DEVICE HEAT/COOL по реальным `hvac_action` термостатов `control: device`, без учёта `control: app`.
- Добавлены независимые ACTUAL HEAT/COOL — только из явно указанных пользователем `actual_demand.heat/cool` (binary_sensor), без автоматического обнаружения.
- Для Recorder: бинарные MQTT-сенсоры без динамических атрибутов; для UI: Count с перечнем комнат/термостатов. Недостоверные источники дают `unavailable`, а не ложный OFF. Дополнительного опроса и команд оборудованию нет.
- Контракт и правила исключения четырёх UI Count из Recorder описаны в `docs/DEMAND_CONTRACT.md`. Старый конфиг 0.1.32 остаётся допустим, раздел `actual_demand` необязателен.

## 0.1.32 — 2026-10-27

- Новый формат конфигурации: вложенные списки датчиков/устройств в комнатах и отдельный объект наружных источников.
- Реализовано раздельное управление FAST и SLOW, режимы `control: app/device`, обратимое климатическое устройство с единым owner, управление клапанами NO/NC и защитой от устаревшего outdoor RAW.
- Добавлены persisted global tuning, дневные/ночные/away SLOW-профили без выдуманных значений по умолчанию, отдельный offline seed с резервной копией SQLite.
- Добавлены retained health и machine events на переходах состояний; сохранены интерфейсы MQTT комнат и совместимость идентификаторов.
- Обновление через штатный магазин Home Assistant. Старые options несовместимы с новой схемой: перед обновлением сохранить backup App с SQLite, затем заменить YAML целиком на новый формат. LAB SLOW 27 °C требует однократного заполнения day/night/away при отсутствии ранее сохранённых значений.


## 0.1.31 — 2026-10-26

- Устранена лишняя команда OFF физическим FAST-актуаторам при запуске HA, когда начальный снимок ещё не содержит температуру комнаты или данные наружной температуры/сезона.
- Введён ограниченный 60-секундный startup readiness gate для команд: FAST ждёт температуру комнаты и сезон, SLOW — сезон, а гигростаты — влажность; остальные комнаты продолжают работать независимо.
- Как только соответствующий источник хотя бы раз появился, его дальнейшая потеря немедленно обрабатывается существующей безопасной политикой; после 60 секунд startup guard заканчивается без бесконечного ожидания.
- Изменения границ ожидания пишутся в climate.log как STARTUP_GATE DEFER / READY / TIMEOUT_FAIL_SAFE.
- Добавлены регрессионные тесты для SmartIR OFF→HEAT на старте, раздельной готовности комнат, гигростатов, SLOW, последующей потери датчика и тайм-аута.
- LAB package, Supervisor options, уставки, гистерезис и алгоритмы самого регулирования не изменены.

## 0.1.30 — 2026-10-19

- Исправлена ошибочная отправка null-маркеров при очистке устаревших Supervisor options: Supervisor заменяет объект options целиком, поэтому теперь App отправляет полный очищенный словарь.
- Сохраняются все привязки устройств, режимы, и пользовательские параметры; удаляются только старые initial targets и старые глобальные ключи.
- После записи проверяется точное соответствие сохранённых options новому объекту.
- Резервная копия исходных Supervisor options перед миграцией: /data/options_before_0.1.30_supervisor.json.
- Regression-тесты моделируют точную семантику full replacement Supervisor и отвергают null tombstones.


## 0.1.29 — 2026-10-19

- Исправлена миграция устаревших Supervisor options после обновления схемы: список старых ключей теперь читается через GET /addons/self/info, а не из очищенного /data/options.json.
- Удаление top-level полей выполняется явными null tombstones, как предписывает Supervisor; комнаты очищаются заменой списка rooms без потери привязок.
- В /data/options_before_0.1.29_supervisor.json сохраняется исходная конфигурация Supervisor до изменения.
- После POST выполняется проверка реально сохранённых options; ошибка не блокирует работу климата. SQLite и runtime уставки не затрагиваются.
- Regression тесты моделируют различие между валидированным runtime options.json и фактическими сохранёнными настройками Supervisor.


## 0.1.28 — 2026-10-19

- Упрощены Supervisor options: комнатные Day/Night/Away/Antifreeze и начальная цель влажности хранятся в SQLite и больше не нужны в YAML.
- Первичные уставки HEAT 23/23/18/10 °C, COOL 25/24/30 °C, RH 50%. Для новой установки сезонные пороги HEAT 10 °C, COOL 25 °C; существующие уставки и пороги сохраняются.
- Редактирование порогов сезонного MQTT climate ограничено диапазоном 5–25 °C; прежние значения вне диапазона не изменяются автоматически.
- Настройка hysteresis переименована в temperature_hysteresis с совместимой миграцией; EMA 20 минут и RAW защита кондиционера −10 °C сохранены.
- Старые Supervisor options удаляются через self API только после SQLite seed, с копией прежних options. При нестандартном EMA/AC ограничении автоматическая очистка откладывается.
- Добавлены regression tests для повторной инициализации, добавления комнаты, сохранения уставок, миграции и сезонного диапазона.


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
