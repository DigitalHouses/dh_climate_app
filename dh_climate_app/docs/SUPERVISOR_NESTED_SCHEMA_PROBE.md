# Проверка вложенных списков Supervisor для декларативного Climate App

**Статус:** isolated source-level probe = PASS; **native GUI на установленном HAOS пока не принят**.
**Дата:** 2026-10-27.
**Текущая версия Climate App:** 0.1.31 (рабочий runtime/config.yaml не изменён).
**Исследованный Supervisor:** GitHub release tag `2026.10.4`, файлы `supervisor/apps/validate.py` и `supervisor/apps/options.py`.

## Почему проводили проверку

Нужно оставить пользовательскую навигацию **«Комнаты → Изменить комнату»** из текущего Supervisor GUI и перейти от CSV-строк к настоящим упорядоченным YAML-спискам. В первую очередь:

```yaml
rooms:
  - id: bedroom
    name: Спальня
    temperature_sensors:
      - sensor.th_bedroom_temperature_1
      - sensor.th_bedroom_temperature_2
```

Та же форма должна использоваться для любых множественных фактов: `humidity_sensors`, `window_sensors`, `devices`, приоритетные `outdoor.temperature_sources` и `outdoor.humidity_sources`. **Один элемент также оформляется списком**.

Семантика отличается:
- комнатные температурные датчики по существующей политике **усредняются**;
- наружные источники **приоритетны, с fallback** по порядку;
- devices — список независимых актуаторов, не источник значений.

## Что доказывает исходный код Supervisor

В версии 2026.10.4 `SCHEMA_ELEMENT` в `supervisor/apps/validate.py` использует рекурсивный `vol.Self` для `dict` и для `list` из primitive либо dict. Прямой `list` внутри `list` без промежуточного dict запрещён.

`UiOptions` в `supervisor/apps/options.py` порождает:
- list of dict → `type: schema, multiple: true`;
- list of scalar внутри room schema → `type: string, multiple: true`;
- nested `rooms[].devices[]` → `type: schema, multiple: true`;
- `outdoor` → `type: schema` с дочерними `temperature_sources` и `humidity_sources`, обе `multiple: true`.

Старая документация/исторические issues о глубине 2 **не соответствуют** этой проверенной схеме source-code v2026.10.4. Поддержка **именно установленной версии Supervisor** требует живого GUI smoke.

## Выполненный изолированный тест

На отдельном Linux runner во временной директории:
- установлен `voluptuous` только в изолированную временную папку;
- из source tag `2026.10.4` взяты непосредственно `RE_SCHEMA_ELEMENT`, `SCHEMA_ELEMENT` и `UiOptions` (без запуска Supervisor);
- построена тестовая schema:

```yaml
schema:
  rooms:
    - id: str
      name: str
      temperature_sensors:
        - str
      humidity_sensors:
        - str?
      devices:
        - entity: str
          role: list(slow_heat|fast_heat|fast_cool)
          control: list(app|device)
          actuator: list(normal_open|normal_closed)?
  outdoor:
    temperature_sources:
      - str
    humidity_sources:
      - str
```

Результат теста:

```text
TEST_REF supervisor 2026.10.4
SCHEMA_VALIDATION: PASS
GUI_ROOM_LIST: schema multiple True
GUI_TEMPERATURE_SENSOR_LIST: string multiple True
GUI_ROOM_DEVICE_LIST: schema multiple True
GUI_OUTDOOR: schema ['temperature_sources:True', 'humidity_sources:True']
list_of_lists REJECTED_PASS
bad_deep_list REJECTED_PASS
```

Значит, формат согласуется **с реальной структурой схемы валидатора и генератора GUI**. Проверка **не означает**, что web frontend уже нарисован и сохранён на установленном HAOS.

## Следующий необходимый GUI smoke

**Без правок действующего `8d59ce70_dh_climate_app`, без изменения его options, рестарта и команд актуаторам.**

На изолированном тестовом App или локальном Supervisor dev-test:
1. Подтвердить версию Supervisor и доступность отдельной **тестовой** конфигурации.
2. Загрузить тестовый App со schema `rooms[].temperature_sensors[]`, `rooms[].devices[]`, `outdoor.temperature_sources[]`, `outdoor.humidity_sources[]`; тестовый App не имеет доступа к HVAC и не публикует управляющие команды.
3. Открыть **Комнаты**, отредактировать спальню, добавить/удалить два датчика, сохранить, затем снова открыть и убедиться в сохранности порядка и значений.
4. Проверить добавление двух устройств внутри одной комнаты, их роли и `control`; корректное удаление/сохранение.
5. Изменить приоритет наружных источников, проверить что порядок после save/reopen сохраняется.
6. Проверить отказ при невалидных вложенных данных и работоспособность русских labels.
7. Только после этого менять production options schema с **контролируемой миграцией**.

## Миграционные риски текущей 0.1.31

Текущая Supervisor `config.yaml` требует `temperature_sensors: str` и другие CSV-like строки; при прямой смене на `[str]` существующие сохранённые options будут невалидны **до миграции**. Поэтому нельзя менять только тип поля в production metadata.

Положительный момент: существующий `src/dh_climate_app/config.py::_entity_list` уже читает **и строку с запятыми, и настоящий Python list/tuple**, сохраняя порядок и удаляя повторы. Для комнатных sensor bindings на уровне Python большая часть совместимости имеется; основная проверка связана с Supervisor schema, migration options и GUI. Вложенный `rooms[].devices[]` и Outdoor object в текущем parser пока не реализованы.

**Обязательное решение:** в клиентском UI оставить одну таблицу комнат. Не создавать отдельно редактируемый пользователем root `devices` ради ограничений парсера. Все operational numbers (уставки, гистерезисы, 5/5 минут) — SQLite + MQTT, **не options YAML**.

## Источники

- [Supervisor 2026.10.4, apps/validate.py](https://github.com/home-assistant/supervisor/blob/2026.10.4/supervisor/apps/validate.py)
- [Supervisor 2026.10.4, apps/options.py](https://github.com/home-assistant/supervisor/blob/2026.10.4/supervisor/apps/options.py)
- [HA Apps configuration](https://contributors.home-assistant.io/apps/reference/configuration/)
- [Текущий Climate App config.yaml](../config.yaml)
- [Целевая матрица](TARGET_ROOM_CLIMATE_MODEL.md)

**Вердикт:** `rooms[].temperature_sensors[]`, `rooms[].devices[]` и `outdoor.*_sources[]` проходят isolated schema/UI generation. Следующий gate — реальные render/save/reopen tests в графическом Supervisor без изменения работающего Climate App.
