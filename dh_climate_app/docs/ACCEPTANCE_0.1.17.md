# DigitalHouses Climate App 0.1.17 — приёмочное тестирование HAOS

Дата: 2026-09-27

## Область проверки

Версия `0.1.17` проверена на реальной установке Home Assistant OS с bundled acceptance harness и детерминированными MQTT fixtures для физических actuators.

Live gate покрывал нативный комнатный Climate UI, появившийся после 0.1.15, и повторно прогонял существующий набор acceptance для actuators/safety/durability.

## Результат нативного комнатного Climate

Комнатный термостат прошёл полный нативный Climate-сценарий:

- HEAT season публикует room state `heat`;
- фактический heating demand показывает `hvac_action=heating`;
- effective profile публикуется через native Climate presets;
- выбор `night` показывает Night target для редактирования;
- выбор зарезервированного Home Assistant `none` возвращает автоматически effective profile;
- COOL season публикует room state `cool` и `hvac_action=cooling`;
- межсезонье публикует room state `off`;
- MQTT Climate capabilities остаются стабильными `off / heat / cool` при смене сезонов, чтобы Home Assistant не пересоздавал Climate entity.

## Результат safety и actuators

Тот же run прошёл:

- начало и recovery `device_target_out_of_range`;
- bounded `device_no_confirmation` retry через RETRY 2/3, RETRY 3/3 и COOLDOWN 300s с последующим recovery;
- поведение SLOW heat floor и shutdown вне HEAT season;
- window context с selective inhibition через `window_off_devices`;
- low-temperature heating protection reversible climate без блокировки COOL;
- активное humidity control, воспроизведение range-problem и безопасное power-off при target вне физического диапазона humidifier.

## Результат durability

До применения acceptance-конфигурации был создан Supervisor backup только Climate App. После всех behavioral gates backup успешно восстановлен.

Restore сохранил:

- App options;
- persisted room targets;
- season thresholds;
- App version `0.1.17`.

Финальный runtime вернулся к чистому baseline:

- room state `heat`;
- room control action `idle`;
- aggregate Problem `off`;
- Problem count `0`.

## Итог runtime acceptance

```text
repository CI = green
container build = green
real HAOS update/start = green
room native HEAT/COOL/OFF semantics = green
room day/night/away presets = green
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

- tag: `digitalhouses_climate_app-v0.1.17`;
- commit релиза: `a346d46e990b1355fbbcc1c46ebc7d15431f66a8`;
- image: `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.17`;
- manifest digest: `sha256:641367437f7d8b1bb2796c0fee983080183cf760217a09661be80baf1b229f3d`;
- run release workflow: `36275409307`.

Release workflow проверил canonical tag, убедился, что immutable destination не занят, опубликовал multi-architecture GHCR image и создал GitHub Release.

Опубликованная immutable image version не может быть перезаписана другим содержимым.
