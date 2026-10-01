# DigitalHouses Climate App 0.1.20 — приёмочное тестирование HAOS

Дата: 2026-09-27

## Область проверки

Версия `0.1.20` проверена на реальной установке Home Assistant OS с bundled acceptance harness.

Релиз добавляет наблюдаемость существующей приоритетной цепочки источников наружной температуры.

## Результат наружных источников

Live run подтвердил:

- активный источник виден через season facade;
- изменение температуры при том же источнике записывается в `climate.log` вместе с active source;
- потеря primary source переключает систему на настроенный backup;
- failover записывает отдельную строку source-switch в log;
- failover публикует `outdoor_temperature_source_changed`;
- Event содержит previous/current source и previous/current temperature;
- восстановление preferred primary source автоматически переключает систему обратно;
- preferred-source recovery публикует обратный transition;
- первое полное наблюдение после startup/reconnect остаётся baseline, а не синтетическим source-change Event.

Наблюдавшаяся live-последовательность:

```text
primary 5.0 °C
primary 7.0 °C
primary unavailable
backup 6.0 °C
primary restored 5.0 °C
```

## Результат регрессии

Тот же bundled run прошёл полный существующий acceptance set:

- отдельный outdoor temperature avg24 sensor;
- нативная семантика room HEAT / COOL / OFF;
- native presets day / night / away;
- target-range safety;
- bounded no-confirmation retry и cooldown recovery;
- SLOW floor control;
- window context и selective inhibition;
- cold-weather protection reversible climate;
- активный humidity path и safe shutdown;
- Supervisor backup/restore только Climate App;
- финальный clean baseline с aggregate Problem off.

## Итог runtime acceptance

```text
repository CI = green
container build = green
real HAOS update/start = green
outdoor source temperature-change log = green
primary -> backup failover = green
source-switch log = green
outdoor_temperature_source_changed Event = green
backup -> preferred primary recovery = green
full existing regression suite = green
Climate-App-only backup/restore = green
final clean baseline = green
runtime acceptance = PASS
```

## Статус релиза

Runtime acceptance и immutable publication завершены.

Опубликованный релиз:

- tag: `digitalhouses_climate_app-v0.1.20`;
- release commit: `50f6ed7cc72cc3b01f8f12b05325d1eb9469a14b`;
- image: `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.20`;
- manifest digest: `sha256:1405f6b91adddc1325047bcdebcee23af0da401b6df4ffd742450d23a0f1476c`;
- release workflow run: `36280643923`.

Опубликованная immutable image version не может быть перезаписана другим содержимым.
