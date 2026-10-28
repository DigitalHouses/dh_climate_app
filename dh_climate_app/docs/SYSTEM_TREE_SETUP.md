# System Tree — штатная Markdown-карточка Home Assistant

**Версия к установке:** DH Climate App 0.2.0 (экспериментальный breaking upgrade).
**Статус:** Python/CI тесты выполнены; live HAOS acceptance ещё не проведён.
Действующая на объекте 0.1.33 остаётся неизменной до ручного обновления App и полного
Supervisor options YAML. Новая версия включает рефакторинг устройств, Demand и
ресурсов, а не только отображение дерева.

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
  `<a href="./?more-info-entity-id=climate.example">climate.example</a>`.
  **Важно:** query-only `href="?more-info-entity-id=..."` фильтр
  `js-xss` внутри Markdown HA удаляет из `<a>`; допустимый вариант —
  `href="./?more-info-entity-id=..."`. Он разрешён фильтром и передаёт
  запрос More Info фронтенду. Такая ссылка ведёт на корень текущей панели,
  поэтому при открытии диалога может измениться выбранная вкладка dashboard.
  Это исправление Lovelace-карточки, не требует обновления App 0.2.0.
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

До обновления Climate App 0.1.33 не публикует
`sensor.dh_climate_app_topology`: карточка корректно покажет
`данные недоступны`. После обновления 0.2.0 проверять живой push.

## Реализованная модель в 0.2.0

- Глобальный выбор `heating_source: boiler|central_heating`; BOILER или CENTRAL
  находится **только под HOME**, никогда на уровне корня. При CENTRAL
  ветка котла исчезает со всеми его собственными параметрами.
- VRF `on|off` не отменяет водяной источник; общая телеметрия компрессора,
  аварий, ограничений показывается под HOME **лишь при наличии resources[]**.
  Внутренние блоки всегда остаются под своими ROOM.
- Комнатные devices в YAML используют `device_type: virtual|hardware`,
  роли FAST/SLOW независимы; каждая физическая связь с ресурсом
  указывается через `resource: home_heating|vrf|independent`.
- ROOM/HARDWARE/VIRTUAL Demand и логический ресурсный REQUEST отличаются от
  физической обратной связи SALUS. При отсутствии зарегистрированных
  устройств ресурса его REQUEST — UNKNOWN, не выдуманный OFF.
- `resources[]` содержит реальную телеметрию уровня дома,
  `pumps[]` и `circuits[]` только при наличии физического оборудования.
  Их величины читаются из HA без команд включения.
- Один внешний read-model строится Python App; Markdown отвечает лишь за
  непрерывные линии и ссылки More Info. Графика и ссылки требуют живой
  приёмки в HAOS.

**Пример новых опций:** [семь комнат 0.2.0](../examples/dh_climate_app_0.2.0_options.yaml).
**Текущая 0.1.33** должна быть обновлена штатным способом только после
вставки корректных настроек версии; второй экземпляр с теми же MQTT
топиками одновременно не запускаем.

## Новая оконная политика FAST_COOL (feature-ветка, не релиз)

- Открытое окно через `rooms[].window_sensors[]` блокирует **только активный
  FAST_COOL** — и автономный `control: device`, и `control: app`.
  Реверсивный кондиционер в сезоне HEAT продолжает работать. FAST_HEAT и
  SLOW_HEAT не блокируются окнами независимо от домена их исполнительных
  сущностей.
- Задержка `window_open_delay_seconds`: SQLite seed **10 секунд**,
  MQTT Number `number.dh_climate_app_window_open_delay_seconds`, диапазон
  **0–300 секунд**, шаг 1 секунда. Настройка переживает перезапуск App и
  не входит в Supervisor YAML.
- На первое наблюдаемое OPEN App заводит один отменяемый таймер на комнату;
  при закрытии всех окон до deadline он отменяется. Нет периодического
  оконного опроса. После подтверждённого закрытия действие FAST_COOL снова
  определяется обычными правилами, не принудительным ON.
- При `unknown/unavailable` не утверждать CLOSED: временная политика
  **hold-last observed OPEN** до достоверного CLOSED; при изначально неизвестном
  окне без подтверждённого OPEN не создавать выдуманную блокировку. Событие
  неизвестного окна диагностируется отдельно.
- Устаревший `window_off` удалён из **нового** Supervisor-контракта; старый
  экспериментальный YAML с этим ключом не принимается. В этой feature-ветке
  компилятор ещё использует `control: app|device`, пока не выполнен
  отдельный обязательный переход на `device_type: virtual|hardware`.
- Комната сообщает `window_cooling_blocked` в MQTT-атрибутах climate.
  System Tree при активной блокировке показывает
  `🚪 WINDOW OPEN · ❄️ COOLING INHIBITED` как отдельный диагностический узел.

**Граница:** автоматизированные unit/integration-тесты подтверждают алгоритм,
но на реальном HAOS ещё проверить 10-секундную выдержку, выключение
физического тестового AC, восстановление после закрытия, reconnect и сохранение
MQTT Number. В production оборудование не затрагивать до HAOS acceptance.

## Границы приёмки

- Unit-тесты и CI; валидный YAML; полный read-model на 7 комнатах из
  фактических Supervisor options.
- На HAOS отдельно проверить: публикацию MQTT Discovery, масштаб и
  рисование всех ветвей, подстановку real HA states, изменение температуры,
  уставок, профиля и health без ручного обновления страницы, unknown/unavailable,
  MQTT HA reconnect, Recorder exclusion.
- Проверка отдельных More Info кликов через `./?more-info-entity-id=`
  **ещё не пройдена на живом HAOS**; автоматический Jinja-render и факт
  поддержки ссылки в штатном frontend не заменяют реальную приёмку.
- До отдельной приёмки не обновлять установленную 0.1.33, не трогать
  SALUS/Dingtian/котёл/насосы и не выполнять физическое управление.

Для безопасной диагностики до обновления можно использовать
`tools/haos_system_tree_preflight.sh` — только чтение, ничего не устанавливает.
