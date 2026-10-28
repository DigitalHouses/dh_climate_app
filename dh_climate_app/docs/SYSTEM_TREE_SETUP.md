# System Tree — штатная Markdown-карточка Home Assistant

**Baseline:** DH Climate App 0.1.33. **Статус:** экспериментальная реализация в PR, HAOS live acceptance ещё не проведён.
Основная система отопления, SQLite, исполнительная логика и Supervisor YAML не меняются.

## Решение по интерфейсу

Используем **одну штатную карточку `type: markdown`**, как в проекте
DigitalHouses PVE Agent. Собственного `custom:dh-climate-tree-card`, JS-ресурса
и регистрации в Lovelace **нет**. Пользователь вручную вставляет YAML
из [examples/lovelace/dh_climate_system_tree.yaml](../examples/lovelace/dh_climate_system_tree.yaml).
Никаких автоматических изменений Dashboard App не выполняет.

В отличие от более объёмного шаблона DH PVE, Jinja здесь не просматривает все
`states.sensor` и не реализует бизнес-правила. Он читает готовую топологию
из `sensor.dh_climate_app_topology` и соединяет подписи элементов в дерево,
сохраняя `├─`, `│`, `└─`, статусы и эмодзи.
Вся структура комнат, HOME/OUTDOOR, источников, устройств, сезонной логики
и последующих ресурсов определяется Python App по достоверным данным.

## Контракт read-model

- MQTT state: `DigitalHouses/Global/dh_climate_app/topology/state`:
  `ready | offline | too_large`.
- MQTT attributes: `DigitalHouses/Global/dh_climate_app/topology/attributes`:
  `{schema_version: 1, lines: [{prefix, parts: [{text, entity_id?}]}]}`.
- Единый HA-сенсор `sensor.dh_climate_app_topology` через MQTT Discovery.
- `prefix` уже содержит соответствующую ветвь и отступ; `parts[].text` —
  готовые фрагменты строки. Jinja только соединяет их.
- `parts[].entity_id` используется для генерации **штатной Markdown-ссылки**:
  `<a href="?more-info-entity-id=climate.example">climate.example</a>`.
  URL-параметр `more-info-entity-id` обрабатывается frontend Home Assistant
  и открывает стандартное More Info; текущая страница сохраняется за счёт
  относительного query URL. Нет JS-обработчиков или дополнительных карточек.
  Текст обязательно HTML-экранируется через Jinja `|e`, идентификатор — `|urlencode`.
  Автоматический Jinja-render тест пройден; пользовательский клик в HAOS 2026.10.4
  ещё требует **живой проверки**.
- Изменения доходят через обычные HA state updates, без polling в Lovelace.
- Ретейнимые MQTT публикации дедуплицируются; при потере HA статус `offline`.
- Ограничение на JSON-атрибуты: 32 000 байт UTF-8; при превышении явный
  `too_large`, а не обрезанное дерево.
- Сенсор диагностический, **не предназначен для Recorder**. Исключить
  `sensor.dh_climate_app_topology` из Recorder, если действующая
  include-политика этого ещё не делает.

## Markdown YAML

Скопировать **целиком** файл
[dh_climate_system_tree.yaml](../examples/lovelace/dh_climate_system_tree.yaml)
в редактор одной Markdown-карточки Home Assistant. `grid_options.columns: 12`
соответствует примеру DH PVE; при необходимости размещение меняется вручную.
Дополнительных JS-зависимостей, `/config/www` или Dashboard Resources нет.

До установки новой версии Climate App существующая 0.1.33 не публикует
`sensor.dh_climate_app_topology`: карточка корректно сообщит
`данные недоступны`.

## Строгое соответствие архитектурной модели

Макет и порядок ветвей заданы
[утверждённым TARGET-документом](SYSTEM_TREE_AND_HEAT_RESOURCE_VISION_2026-10-28.md).
В экспериментальном read-model уже существуют: ONLINE/health, OUTDOOR,
независимые приоритеты T/RH, HOME, ROOMS по порядку YAML, room climate,
вложенные FAST/SLOW, влажность, фактические поля устройств и профили.

BOILER/CENTRAL HEATING/VRF, ROOM/HARDWARE/VIRTUAL Demand под ресурсом,
SALUS, насосы и гидроконтуры добавляются **только после появления достоверного
ресурсного контракта и источников фактов**. Они не синтезируются
по названию комнаты, role, домену entity или HA weather.

До несовместимого обновления YAML старое `control: app|device` только
отображается под именем `VIRTUAL|HARDWARE`. Реальное `device_type` —
отдельный утверждённый этап.

`AVAILABLE` означает доступную HA-сущность, **не** подтверждение исправности
физического термостата или сухого контакта. Измеряемые факты не заменяются
договорными значениями.

## Границы приёмки

- Unit-тесты и CI; валидный YAML; полный read-model на 7 комнатах из
  фактических Supervisor options.
- На HAOS отдельно проверить: публикацию MQTT Discovery, масштаб и
  рисование всех ветвей, подстановку real HA states, изменение температуры,
  уставок, профиля и health без ручного обновления страницы, unknown/unavailable,
  MQTT HA reconnect, Recorder exclusion.
- Проверка отдельных More Info кликов через `?more-info-entity-id=`
  **ещё не пройдена на живом HAOS**; автоматический Jinja-render и факт
  поддержки ссылки в штатном frontend не заменяют реальную приёмку.
- До отдельной приёмки не обновлять установленную 0.1.33, не трогать
  SALUS/Dingtian/котёл/насосы и не выполнять физическое управление.

Для безопасной диагностики до обновления можно использовать
`tools/haos_system_tree_preflight.sh` — только чтение, ничего не устанавливает.
