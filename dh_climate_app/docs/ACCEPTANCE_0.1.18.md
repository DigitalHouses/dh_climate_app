# DigitalHouses Climate App 0.1.18 — приёмочное тестирование HAOS

Дата: 2026-09-27

## Область проверки

Версия `0.1.18` проверена на реальной установке Home Assistant OS с bundled acceptance harness и детерминированными MQTT fixtures.

Этот релиз исправляет список capabilities комнатного термостата, чтобы пользователь видел только режимы, допустимые для текущего глобального сезона.

## Результат нативного комнатного Climate

Live run прошёл точный сезонный capability contract:

- HEAT season: `hvac_modes = [off, heat]`;
- COOL season: `hvac_modes = [off, cool]`;
- interseason/OFF: `hvac_modes = [off]`;
- room state следует тому же season contract: `heat / cool / off`;
- `hvac_action` остаётся независимым и показывает фактическую активность;
- native presets `day / night / away` пережили Discovery updates HEAT → COOL → OFF;
- выбор `night` показал Night target;
- выбор зарезервированного Home Assistant `none` вернул автоматически effective profile.

Сохранение preset реализовано без timing delays. App сначала публикует authoritative retained preset в season-scoped preset state topic, затем season-specific MQTT Discovery payload. Изменение preset state topic заставляет Home Assistant переподписаться и сразу получить retained preset.

## Результат safety и actuators

Тот же run прошёл:

- начало и recovery `device_target_out_of_range`;
- bounded `device_no_confirmation` retry через RETRY 2/3, RETRY 3/3 и COOLDOWN 300s с последующим recovery;
- SLOW heat floor и shutdown вне HEAT season;
- selective window inhibition через `window_off_devices`;
- cold-weather heating protection reversible climate без блокировки COOL;
- активное humidity control и safe shutdown при stored target вне физического диапазона humidifier.

## Результат durability

До применения acceptance-конфигурации создан Supervisor backup только Climate App, после проверки он успешно восстановлен.

Финальный runtime вернулся к чистому baseline:

- App version `0.1.18`;
- room state `heat`;
- room control action `idle`;
- aggregate Problem `off`;
- Problem count `0`.

## Итог runtime acceptance

```text
repository CI = green
container build = green
real HAOS update/start = green
HEAT modes off/heat only = green
COOL modes off/cool only = green
OFF modes off only = green
day/night/away preset preservation = green
preset reset to automatic profile = green
target_out_of_range safety = green
no_confirmation/retry/cooldown = green
SLOW thermostat path = green
window context = green
cold-weather reversible climate protection = green
humidity safe shutdown = green
Climate-App-only backup/restore = green
final clean baseline = green
runtime acceptance = PASS
```

## Статус релиза

Runtime acceptance и immutable publication завершены.

Опубликованный релиз:

- tag: `digitalhouses_climate_app-v0.1.18`;
- release commit: `744c0cb479305f508ffd4b709d5e96c8623e5357`;
- image: `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.18`;
- manifest digest: `sha256:386b4890f893ba5c87f755a9b2f56267bba700618b870bb0dc8b875860be5e95`;
- release workflow run: `36276954342`.

Опубликованная immutable image version не может быть перезаписана другим содержимым.
