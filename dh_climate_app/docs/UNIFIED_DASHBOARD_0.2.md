# DH Climate 0.2.0 — единый Lovelace dashboard

**Продукт:** DigitalHouses Climate App 0.2.0. **Формат:** один dashboard `DH Climate` (`dh-climate`), несколько views. Этот комплект — **frontend-only**, не обновляет App, не меняет Supervisor YAML, исполнительную логику и MQTT.

## Структура

| View | Path | Содержание |
| --- | --- | --- |
| Система | `system` (полный образец) | Уже проверенный System Tree: штатная Markdown-карточка, кликабельный More Info, готовый read-model |
| Комнаты | `climate` | Динамические комнаты по Home Assistant Areas: нативные Tile термостата (`target-temperature`) и гигростата (`target-humidity`), без инженерных уставок |
| Улица | `outdoor` | Сезон, RAW/EMA/AVG24, наружная влажность, осадки и штатные HA History Graph |
| Администрирование | `admin` | Здоровье, проблема, версия, старт, события, пороги и гистерезисы, профили комнат, SLOW, Demand/Request, лабораторные комнаты |

LAB-комнаты **не входят в клиентскую вкладку** даже если им назначат Area: используется фильтр префикса `climate.dh_climate_app_lab_*`. Клиентская вкладка не перечисляет комнаты вручную: она берёт их через `area_name(entity_id)` и реальные MQTT Climate/Humidifier сущности. Схема Jinja/Auto-Entities основана на предыдущем работавшем Indoor v5.2; новый вариант требует визуального smoke-теста в HA.

Не используем `tojson` и новые frontend-библиотеки. Требуется уже установленный `custom:auto-entities`. Графики Улицы — нативные `history-graph`, без графиков, создаваемых из JSON/Jinja.

## Файлы

- [Полный dashboard](../examples/lovelace/dh_climate_dashboard_0.2.yaml) — образец для пустого dashboard: содержит действующую System Tree как первую страницу и три новые страницы.
- [Только новые страницы](../examples/lovelace/dh_climate_dashboard_add_views_0.2.yaml) — для **существующего** `DH Climate`, где System Tree уже работает.
- [Безопасный merger](../tools/merge_dh_climate_dashboard.py) — формирует новый YAML, не трогая исходный. Он заменяет существующие `climate` и `outdoor`, добавляет `admin`, сохраняет первую страницу и все прочие страницы (например `aqara-w500`).

## Как установить в действующий dashboard

1. В Home Assistant открой **DH Climate → Редактировать → ⋮ → Редактор исходного кода / Raw configuration editor**. **Сохрани полную копию текущего YAML** локально как `climate_current.yaml`.
2. На рабочем компьютере с Python и PyYAML выполни:

```bash
python3 merge_dh_climate_dashboard.py climate_current.yaml \
  --overlay dh_climate_dashboard_add_views_0.2.yaml \
  --out climate_merged.yaml
```

3. Проверь, что результат сообщил `REPLACED: climate, outdoor`, `ADDED: admin` (при ином состоянии списка views результат может отличаться). При этом **первая страница и не-Climаte вкладки должны остаться без изменений**.
4. Вставь содержимое `climate_merged.yaml` в Raw editor существующего dashboard; сохрани. Нет необходимости создавать новый dashboard, выполнять `ha core restart` или менять приложение.
5. Проверь: **System Tree** продолжает открывать More Info; на **Комнаты** появляются Area-группы и нативные управления; **Улица** рисует реальные графики; **Администрирование** показывает существующие настройки и параметры. Отдельно проверь видимость Admin для конкретных пользователей средствами Home Assistant.

**Важно:** файл `*_add_views_0.2.yaml` — только фрагмент `views`, **не полный** dashboard. Его нельзя целиком вставлять поверх существующей Raw-конфигурации: так будут потеряны прежние страницы.

## Границы реализации

- Доступность вкладки не является границей безопасности. Для администраторского dashboard используй права/доступ в HA; не считай скрытие view безопасной авторизацией.
- Стандарт DigitalHouses Unified Product Status Card требует `sensor.dh_climate_app_card`. В runtime 0.2.0 такого агрегатного сенсора нет; **не подменяем** его шаблонным состоянием. Пока показываем существующие `sensor.dh_climate_app_global_health`, `sensor.dh_climate_app_climate_health` и `binary_sensor.dh_climate_app_problem`. Отдельный status-card контракт — будущая backend-задача.
- Нажатие `button.dh_climate_app_delete_telemetry` не выводим: это разрушительное действие, для которого требуется подтверждение по стандарту Operation UI.
- Приложение **не управляет вентиляцией по CO₂**; наличие LAB VENTILATION не превращает его в полноценный DCV-контроллер.
- Значение `BOILER HEAT REQUEST: UNKNOWN` при отсутствующей привязке оборудования — корректное, его нельзя красить как OFF.
- Фактический Web/Lovelace smoke на HAOS остаётся следующим acceptance, автоматические тесты проверяют YAML, рендер Jinja и сохранность views.

## Разработка и тестирование

```bash
python3 -m unittest discover -s dh_climate_app/tests -q
```

Регрессия `test_unified_dashboard.py` проверяет четыре страницы, установленный System Tree, запрет `tojson`, Area-группировку, исключение LAB, соответствие текущим MQTT сущностям и нерушащее объединение с существующим dashboard.
