# DigitalHouses Climate App 0.1.19 — приёмочное тестирование HAOS

Дата: 2026-09-27

## Область проверки

Версия `0.1.19` проверена на реальной установке Home Assistant OS с bundled acceptance harness.

Релиз добавляет отдельную UI entity для уже существующего в Climate Core среднего значения наружной температуры за 24 часа:

- `sensor.dh_climate_app_outdoor_temperature_avg24`.

## Результат сенсора avg24

Live run подтвердил:

- новая entity появилась через Discovery после обновления до `0.1.19`;
- её state числовой;
- state совпадает с атрибутом `avg_24h_temperature` season facade;
- наблюдаемое значение в acceptance run: `18.0 °C`;
- значение берётся из существующего persisted rolling average Climate Core, а не из второго расчёта на стороне Home Assistant.

## Результат регрессии

Тот же bundled run прошёл полный существующий набор Climate acceptance:

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
outdoor temperature avg24 sensor = green
full existing regression suite = green
Climate-App-only backup/restore = green
final clean baseline = green
runtime acceptance = PASS
```

## Статус релиза

Runtime acceptance и immutable publication завершены.

Опубликованный релиз:

- tag: `digitalhouses_climate_app-v0.1.19`;
- commit релиза: `76a91373adae33e4ceffd2d1ad6b7727d6c6841f`;
- image: `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.19`;
- manifest digest: `sha256:3d9a057b56d408fc998dbae7f15b636d9b3c1cde4caab448019585c23a988248`;
- run release workflow: `36278385669`.

Опубликованная immutable image version не может быть перезаписана другим содержимым.
