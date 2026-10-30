# DH Climate App · Универсальный HA Entity Picker · v0.2.8

## Назначение

Один повторно используемый компонент выбора Home Assistant
сущностей для форм DH Climate Explorer. Датчики и устройства
выбираются по friendly_name, entity_id, HA Area, domain и доступности.
В интерфейсе нет textarea с ручным вводом entity_id.

## Контексты

- Room.temperature_sensors: sensor, device_class=temperature, множественный.
- Room.humidity_sensors: sensor, device_class=humidity, множественный.
- Room.window_sensors: binary_sensor, классы window/door/opening,
  множественный.
- Device.entity: hardware → только climate; virtual → climate/switch,
  одиночный выбор.
- Device.temperature_sensor: sensor, temperature, одиночный выбор.

Доменные ограничения жёсткие. Несовпадения device_class можно явно
включить («Показать также сущности других классов»).
У датчика без device_class доступность к выбору сохраняется.
Действующий parse_options проверяет итоговую конфигурацию.

## Поиск и HA Area

GET /api/entities выполняется при открытии Picker. Из отдельной
read-only WebSocket-сессии к Home Assistant запрашиваются:
- get_states
- config/entity_registry/list_for_display
- config/device_registry/list
- config/area_registry/list

Область берётся из Entity Registry или, если нет, из Device Registry.
Если имя HA Area точно совпадает с именем DH Room, это подсказка
начального фильтра, но Area не становится обязательной связью.
Сущности без Area показываются через «Без зоны».

Использованные entity_id помечаются комнатой. Приложение не переносит
их между комнатами автоматически.

Для больших сетей: кеш каталога на 30 секунд, браузер показывает
не более 150 результатов одновременно, сервер ограничивает каталог
8000 сущностей. Уточнение поиска и фильтров сужает список.
Собственного реестра HA и глобальной фоновой подписки нет.

## Безопасность

- GET /api/entities доступен только system-admin через доверенный
  Supervisor Ingress peer.
- В JSON возвращаются только entity_id, friendly_name, domain,
  device_class, unit, state, availability, HA Area, device name;
  произвольные HA attributes в браузер не передаются.
- Окно выбора не выполняет HA service calls и не редактирует HA Registry.
- Picker меняет только локальную форму. Для действующего конфига нужны
  Save Draft → Validate → Apply → отдельный restart приложения.
- Недоступные сущности видны. Если существующий ID уже не находится в HA,
  он остаётся в выбранных элементах до явного удаления.

## Приёмка на домашнем HAOS

1. Обновить App, открыть Explorer → Комната → ПКМ → «Редактировать комнату».
2. В блоке «Датчики температуры» нажать «Выбрать в Home Assistant».
   Убедиться, что доступны и ещё не привязанные датчики.
3. Проверить поиск по entity_id, Area и недоступные сущности.
4. Добавить дополнительный датчик в локальную форму,
   нажать «Отмена» и проверить отсутствие изменений Engine.
5. Проверить редактор HARDWARE устройства: видны climate.*, но
   не switch.*. Для VIRTUAL выбор switch.* допустим.
6. Проверить, что существующая недоступная привязка не исчезает.

Текущий YAML, MQTT и SQLite не мигрируют при обновлении версии.
