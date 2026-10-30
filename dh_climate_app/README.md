# DigitalHouses Climate App

`dh_climate_app` — компактное приложение Home Assistant для управления климатом всего дома.

Оно сохраняет полезный **контракт поведения** предыдущей системы DH Climate 5 на PostgreSQL, но заменяет PostgreSQL-оркестрацию, SQL jobs, Matrix/Dispatcher/UC и связанную runtime-инфраструктуру компактным управляющим ядром на Python.

## Архитектура

```text
Состояния Home Assistant
        ↓
Python Climate Core
 ├─ приоритет наружных источников + скользящее avg24
 ├─ глобальный сезон HEAT / COOL / OFF
 ├─ комнатный термостат + профили
 ├─ управление влажностью
 └─ FAST / SLOW + политика безопасности
        ↓
желаемое физическое состояние
        ↓
сервисы Home Assistant
        ↓
climate / switch / humidifier

Python Climate Core
        ↓
MQTT Discovery
        ↓
интерфейсы Home Assistant
```

SQLite в `/data/dh_climate.db` хранит только долговременное состояние установки. SQLite не является движком бизнес-правил или оркестрации.

## Реализованное поведение

- приоритетные цепочки основных/резервных источников наружной температуры и влажности с журналированием активного источника температуры и Events при переключении источника;
- отдельный RAW-диагностический сенсор, наружная температура после EMA-фильтра, средняя наружная температура за 24 часа и текущая наружная влажность для UI/отладки;
- публикация MQTT-фасадов, дружественная к Recorder: без timestamp на каждом runtime tick в атрибутах сущностей, раздельные topics наружных/weather-атрибутов и отсутствие повторной публикации при неизменном публичном состоянии;
- отображение публичных температур с точностью до одного знака при сохранении полной внутренней точности вычислений;
- классификация типа осадков по weather condition и прогнозируемое количество осадков текущего часа в мм;
- один MQTT Event для машинных событий погоды, сезона, окон, Problem и room/climate health; target payload без `schema_version`;
- минутный pipeline наружной температуры через EMA с настраиваемой постоянной времени 20 минут по умолчанию; 24-часовое среднее строится по сохранённым отфильтрованным отсчётам с одинаковым шагом, влажность сохраняет отдельное средневзвешенное по времени avg24;
- глобальный сезон `HEAT / COOL / OFF`;
- изменяемый двухпороговый сезонный термостат `heat_cool`;
- один MQTT Device и один комнатный термостат на каждую настроенную комнату;
- сезонно-нативный комнатный термостат: HEAT показывает только `off / heat`, COOL — только `off / cool`, межсезонье — только `off`; нативные presets `day / night / away` сохраняются при сезонных обновлениях MQTT Discovery, а HVAC action явно показывает `heating / cooling / idle / off`;
- скрытые конфигурационные Number для целей Heat/Cool Day/Night/Away и внутренней Heat antifreeze;
- отдельные persisted гистерезисы FAST HEAT, FAST COOL, SLOW HEAT и смены сезона;
- сохраняемый stateful-гистерезис комнат;
- исполнительные устройства FAST heat/cool;
- автоматическая физическая уставка реверсивных FAST climate по комнатной температурной ошибке без пользовательских offset; уставка стабильна в течение активного цикла;
- SLOW тёплый пол: сезонные релейные клапаны NO/NC и автономные климатические термостаты с отдельными persisted дневной/ночной/away целями стяжки;
- опциональное управление увлажнителем/осушителем;
- оконные контакты комнат с event-driven задержкой (начально 10 сек), отключающей только FAST_COOL; FAST_HEAT/SLOW_HEAT работают независимо;
- унаследованная защита реверсивных heat/cool climate-устройств от отопления при слишком низкой наружной температуре;
- прямое идемпотентное согласование через сервисы Home Assistant с отложенной event-driven проверкой состояния HA;
- ограниченные повторы и агрегированная диагностика Problem;
- безопасное восстановление соединения Home Assistant со свежим snapshot;
- диагностики Version и Started at;
- поддержка DigitalHouses Telemetry Protocol v1;
- канонический multi-architecture workflow публикации GHCR; доставка Supervisor из registry пока остаётся отдельным gate выравнивания со стандартами Experimental-канала.

## DH Climate Explorer (начиная с 0.2.2; Ingress с 0.2.1)

В App включён штатный Home Assistant Ingress. В меню приложения появляется
«Open Web UI» и, при желании администратора, панель DH Climate.
Начиная с 0.2.3 Explorer доступен всем авторизованным пользователям HA;
**серверная** проверка группы system-admin разрешает конфигурирование.
Остальным доступен только просмотр. Дерево System → Weather / Home
→ Resources / Season / Rooms → Devices, выбор объекта одним нажатием,
breadcrumbs, Inspector по запросу, состояния HA и Problems.
С версии 0.2.4 ширина дерева регулируется перетаскиванием границы
(с запоминанием в браузере), а создание/редактирование объектов —
через контекстное меню правой кнопкой мыши, без постоянных кнопок +.
С 0.2.5 в меню остаются только операции над узлом; открытие и
сворачивание выполняются непосредственно в дереве.
С 0.2.6 дерево показывает русские системные названия из словаря,
а для комнат, датчиков и исполнителей — заданные в Home Assistant
friendly_name с запасным вариантом (имя из конфигурации / entity_id).
Это **только отображение**: при переименовании сущности в HA идентификатор
и исполнительная логика Climate App не меняются.
[Правила отображаемых имён](docs/EXPLORER_FRIENDLY_NAMES_0.2.6.md).
С версии 0.2.7 русские и английские пользовательские имена можно
переопределять через ПКМ → «Изменить имя», без изменения HA и Engine.
Начиная с 0.2.8 поля привязки сущностей используют общий HA Entity Picker:
поиск, фильтрация по Area, domain, доступности и device_class, выбор
одного или нескольких entity_id.
[Контракт Picker](docs/EXPLORER_ENTITY_PICKER_0.2.8.md).
В 0.2.9 исправлен домен оконных контактов (строго binary_sensor)
и сужен фильтр по device_class: посторонние системные датчики
не попадают в результаты по умолчанию. Существующие неподходящие
привязки не удаляются, а помечаются для исправления.
Интерфейс переключается между русским и английским; словари расширяемы.
[Контракт и E2E-план Operations](docs/INGRESS_OPERATIONS_V1.md).

Формат Supervisor options 0.2.0 **не меняется**. До первого Apply они
остаются источником конфигурации; после Apply канонический манифест
/data/dh_climate_manifest.json имеет приоритет при следующем запуске.
Supervisor options не перезаписываются и больше не являются активной
конфигурацией, пока существует манифест. SQLite / MQTT / HA Area не
меняются. Runtime не зависит от Ingress; команды исполнителям из UI запрещены.
[Безопасное редактирование и откат](docs/EXPLORER_EDITOR_0.2.3.md).
HAOS ingress smoke остаётся обязательной проверкой перед установкой клиентам.

## Конфигурация

**Начиная с версии 0.2.0 — несовместимый формат Supervisor options.** Перед установкой
скопируйте текущий YAML, сохраните штатный backup App (/data с SQLite), затем
вставьте **полный** [YAML для семи комнат](examples/dh_climate_app_0.2.0_options.yaml).
Текущая версия 0.1.33 не примет новый YAML, а 0.2.0 не примет старый `control`.

- `device_type: virtual|hardware` независим от `role: fast_heat|fast_cool|slow_heat`.
  Для каждого SLOW VIRTUAL обязателен явный `screed_sensor_unavailable: open|closed`;
  `actuator` задаёт полярность NO/NC.
- `heating_source: boiler|central_heating` — глобальный выбор водяного источника,
  `vrf: 'on'|'off'` — отдельный глобальный выбор наличия VRF.
- `resource: home_heating|vrf|independent` у устройства — **только проверенная
  принадлежность**; без неё App не приписывает прибор котлу/ЦО/VRF.
  В противном случае запрос ресурса честно UNKNOWN, а не фиктивный OFF.
- `resources[]`, `pumps[]`, `circuits[]` перечисляют **только реальные**
  существующие датчики и агрегаты. В CENTRAL_HEATING дерево котла отсутствует.
- Изменяемые уставки, гистерезисы, min ON/OFF и задержка окна — MQTT Number
  и SQLite, **не** Supervisor YAML. `window_open_delay_seconds` по умолчанию
  10 секунд, диапазон 0–300 секунд.
- Ресурсные REQUEST — **наблюдение**, App не добавляет команд на запуск
  SALUS, котла, компрессора или насосов. HARDWARE-цепь сохраняет автономность.
- System Tree — одна нативная Markdown-карточка:
  [YAML Lovelace](examples/lovelace/dh_climate_system_tree.yaml).
  Никаких дополнительных JS-карт и YAML-списков комнат внутри Dashboard.
  Подробнее: [System Tree](docs/SYSTEM_TREE_SETUP.md).

**Важная граница:** unit/CI-тесты не подтверждают фактическую работу
HAOS и физического оборудования; первый реальный E2E выполняется после
явного обновления App и сохранения новой конфигурации. Проект всё ещё
экспериментальный. Старые пользовательские SQLite targets не пересоздаются.

**Ручная установка и безопасность:**
[Runbook](docs/TARGET_MANUAL_UPGRADE_RUNBOOK.md).

## Документация

Разработка отдельного Climate App следует нормативным контрактам разработки приложений DigitalHouses из репозитория [DigitalHouses/home-assistant-apps](https://github.com/DigitalHouses/home-assistant-apps/tree/main/docs/standards).

Совместимые идентификаторы Climate не переименовываются неявно; такие изменения требуют контролируемой миграции.

Документация этого проекта ведётся на русском языке.

- [Исторический план миграции (0.1.33)](docs/NEXT_IMPLEMENTATION_HANDOFF_2026-10-27.md)
- [Целевая архитектура System Tree, Demand и HOME ресурсов](docs/SYSTEM_TREE_AND_HEAT_RESOURCE_VISION_2026-10-28.md) — реализация первой версии в 0.2.0
- [System Tree: Markdown, MQTT read-model и HAOS приёмка](docs/SYSTEM_TREE_SETUP.md)
- [Единый dashboard 0.2 — System Tree, Комнаты, Улица, Администрирование](docs/UNIFIED_DASHBOARD_0.2.md)
- [Целевая матрица климатических комнат (TARGET, реализация в отдельной ветке)](docs/TARGET_ROOM_CLIMATE_MODEL.md)
- [Проверка вложенных списков Supervisor 2026.10.4](docs/SUPERVISOR_NESTED_SCHEMA_PROBE.md)
- [GAP-анализ версии 0.1.31 относительно целевой матрицы](docs/TARGET_ROOM_CLIMATE_GAP.md)
- [Манифест продукта и конфигурации](docs/PRODUCT_CONFIGURATION_MANIFEST.md)
- [Архитектура](docs/ARCHITECTURE.md)
- [Контракт поведения legacy-системы](docs/LEGACY_BEHAVIOR.md)
- [Пример нового YAML](docs/CONFIG_EXAMPLE.yaml)
- [Полный YAML живого 7-комнатного стенда 0.2.0](examples/dh_climate_app_0.2.0_options.yaml)
- [Машинные события](docs/EVENTS.md)
- [План реализации](docs/IMPLEMENTATION_PLAN.md)
- [План приёмочного тестирования HAOS](HAOS_TEST_PLAN.md)
- [Инструкция по обновлению Experimental](docs/EXPERIMENTAL_UPDATE_RUNBOOK.md)

## Обновление Experimental

Для текущего канала со сборкой из исходников обновите Store Home Assistant:

```bash
ha store reload
```

После этого обновляйте App обычным способом. Не используйте `ha store repair` как штатную команду обновления; см. [инструкцию по обновлению Experimental](docs/EXPERIMENTAL_UPDATE_RUNBOOK.md).

## Релизы и публикация

Версия `0.1.21` прошла bundled runtime acceptance на реальной установке Home Assistant OS и имеет канонический multi-architecture артефакт GHCR с зафиксированным происхождением digest. Текущий пакет App всё ещё не содержит `image:`, поэтому доставляется через сборку из исходников; доставка Supervisor напрямую из registry пока не считается завершённой.

Acceptance включает защиту Recorder от лишней записи, стабильный `last_updated` наружных фасадов между idle runtime tick, переключение/восстановление наружных источников и полный существующий регрессионный набор для комнатного климата, безопасности исполнительных устройств и backup/restore только Climate App. Для детерминированных тестов исполнительных устройств использовались fixtures вместо управления реальным HVAC. См. [HAOS acceptance 0.1.21](docs/ACCEPTANCE_0.1.21.md).

Канонический идентификатор релиза:

```text
digitalhouses_climate_app-v<version>
```

Production images:

```text
ghcr.io/digitalhouses/digitalhouses_climate_app:<version>
```

Публикация релиза контролируется репозиторием. `dh_climate_app/RELEASE` должен содержать точный канонический tag для версии из `config.yaml`. После проверенного merge в `main` workflow валидирует датированный changelog, создаёт канонический tag, проверяет отсутствие уже существующих immutable GHCR version tag и GitHub Release, затем публикует multi-architecture image и GitHub Release.

## Demand и ресурсы (0.2.0)

Наблюдение ROOM HEAT/COOL, HARDWARE HEAT/COOL, VIRTUAL HEAT/COOL,
а также вычисляемых `BOILER_HEAT_REQUEST` / `CENTRAL_HEAT_REQUEST` /
`VRF_COOL_REQUEST` по явно привязанным устройствам.
ROOM не становится независимым физическим выходом агрегатора.
REQUEST ≠ подтверждение SALUS и ≠ работа котла. Для неизвестных источников —
unavailable/UNKNOWN, точный count только для полного наблюдения.
Устаревший `ACTUAL` удалён как неоднозначный термин. Ранее выпущенный
фактический контракт 0.1.33 сохранён для истории:
[DEMAND_CONTRACT.md](docs/DEMAND_CONTRACT.md).
