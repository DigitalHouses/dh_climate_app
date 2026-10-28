# System Tree — экспериментальная поставка, только чтение

**Baseline:** 0.1.33. **Статус:** код в feature-ветке, HAOS live acceptance ещё не пройден.
Действующая конфигурация Supervisor и SQLite не меняются. Реле, котёл и насосы не управляются.

## Контракт

- Единственный источник дерева: `sensor.dh_climate_app_topology`.
- MQTT: `DigitalHouses/Global/dh_climate_app/topology/state` — `ready | offline | too_large`;
  `.../topology/attributes` — объект `{schema_version: 1, lines: [...]}`.
- `lines[]` содержит `prefix` с уже рассчитанными линиями `├─ │ └─` и
  `parts[]` вида `{text, entity_id?}`. `entity_id` — настоящий HA entity_id.
- UI не строит логику источников, климата и Demand. Это презентационный слой;
  клик по конкретному span вызывает стандартный `hass-more-info`.
- Обновление через штатные HA push-state события, без JS polling.
- MQTT retained публикация только при изменении payload, статус `offline` при потере HA-соединения
  исключает показ устаревшего дерева как актуального.
- Полное дерево ограничено 32 000 байт UTF-8. При превышении `too_large`,
  сообщение в логе и явная ошибка в карточке вместо обрезанного или ложного дерева.
- Диагностический sensor не предназначен для Recorder. Добавить локально
  `sensor.dh_climate_app_topology` в `recorder.exclude.entities`,
  если он не исключён действующей Recorder include-политикой.

## Установка карточки (после review / release)

Лёгкая карточка хранится отдельно в `frontend/dh-climate-tree-card.js`.
Нативный HAOS App не гарантирует автоматического помещения ресурсов в `/config/www`
и регистрации Lovelace. **Не считать автоматическую поставку подтверждённой.**

На HAOS Terminal/SSH, после публикации утверждённой версии:

```bash
mkdir -p /config/www
curl -fsSL https://raw.githubusercontent.com/DigitalHouses/dh_climate_app/main/dh_climate_app/frontend/dh-climate-tree-card.js \
  -o /config/www/dh-climate-tree-card.js
```

Если каталог `/config/www` создан впервые после запуска Home Assistant,
для включения `/local/` требуется один перезапуск Home Assistant.
Файлы в `/config/www` доступны по URL без авторизации: никаких секретов там не хранить.

В Home Assistant: **Настройки → Панели управления → Ресурсы**.
Добавить URL `/local/dh-climate-tree-card.js?v=1`, тип **JavaScript module**.
После установки обновить браузер с очисткой кэша при необходимости.

В Lovelace YAML ровно одна карточка:

```yaml
type: custom:dh-climate-tree-card
entity: sensor.dh_climate_app_topology
```

Здесь нет конфигурации комнат, устройств, источников и иных физических ресурсов.

## Границы первой поставки

- Текущий `control: app|device` переводится в пользовательскую подпись
  `VIRTUAL|HARDWARE` только для отображения. Настоящий переход схемы YAML
  `device_type` будет отдельным этапом.
- Только действующие комнаты, устройства, влажность и внешние источники.
  BOILER/CENTRAL HEATING/VRF, насосы, агрегаторы, контуры и новые Demand
  не синтезируются и не показываются до появления их действительного resource-контракта.
- ONLINE/AVAILABLE в дереве — наблюдаемая доступность HA-сущности, а не
  гарантия механической исправности и не подтверждение сухого контакта.
- OUTDOOR SOURCES: одинаковый порядок T/H — общая цепочка; иначе два дерева,
  каждое со своей реальной приоритетностью.
- Время работы округлено вниз до 10 минут для защиты от частых обновлений.
- Актуальная версия установленного App не меняется этим PR.

## Приёмка

До релиза обязательно проверить на живом HAOS: регистрацию JS, More Info
каждой сущности, динамическое добавление/удаление комнат в конфиге,
изменение температуры/профиля/режима/health, unavailable/reconnect,
корректный статус SENSOR и отсутствие записи JSON дерева в Recorder.
Unit-тесты не заменяют HAOS acceptance. Не включать реальные реле SALUS/Dingtian.

Предполагаемый minimum PASS: тесты pytest/unittest/CI, нормальная сборка HAOS
без изменения существующих entity unique_id и SQLite, живое дерево без
периодической перезагрузки страницы, корректные More Info клики.

**Согласованный TARGET-контракт:** [SYSTEM_TREE_AND_HEAT_RESOURCE_VISION_2026-10-28.md](SYSTEM_TREE_AND_HEAT_RESOURCE_VISION_2026-10-28.md).
