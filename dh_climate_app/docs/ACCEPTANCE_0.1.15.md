# DigitalHouses Climate App 0.1.15 — приёмочное тестирование HAOS

Дата: 2026-09-27  
Среда: реальная установка Home Assistant OS  
App ID: `8d59ce70_dh_climate_app`  
Версия: `0.1.15`

## Результат

**Bundled live runtime acceptance: PASS**

Acceptance harness выполнялся на реальных границах Home Assistant Supervisor/Core/MQTT. Физическое HVAC-оборудование не перехватывалось; для детерминированных сценариев ошибок и безопасности исполнительных устройств использовались временные MQTT Discovery fixtures.

Пусконаладка физического оборудования остаётся специфичной для конкретного объекта и не является software release gate.

## Пройденные live gates

- обновление/запуск App на 0.1.15;
- чистый baseline: Problem off, температура комнаты 21.0 °C, пороги сезона 15.0 / 29.8 °C;
- `device_target_out_of_range`:
  - target climate вне допустимого диапазона был заблокирован;
  - запрещённая команда actuator не была принята;
  - переход Problem/Event v2 содержал room/entity/details;
  - recovery очистил Problem, actuator штатно сошёлся к desired state;
- `device_no_confirmation`:
  - bounded retries дошли до RETRY 2/3 и RETRY 3/3;
  - финальное окно подтверждения истекло до COOLDOWN 300s;
  - последующее подтверждение state восстановило Problem и дошло до VERIFIED_HA;
- политика SLOW floor:
  - HEAT season удерживал SLOW thermostat в heat на отдельном target 27 °C, пока room air demand был idle;
  - OFF season выключал SLOW thermostat;
- window policy:
  - room demand оставался heating при открытом окне;
  - блокировался только actuator из `window_off_devices`;
  - закрытие окна восстанавливало этот actuator;
- cold-weather protection reversible climate:
  - heating реверсивного устройства блокировался ниже -10 °C;
  - остальные источники heating продолжали работу;
  - выше порога heating восстанавливался;
  - cooling оставался разрешён ниже heating-only protective threshold;
- влажность:
  - humidity facade и физический путь humidifier активировались;
  - активный target влажности вне физического диапазона вызывал `device_target_out_of_range`;
  - выключение humidity control всё равно физически выключало humidifier, доказывая, что validation target не может блокировать shutdown;
- Supervisor backup/restore:
  - создан partial backup только с Climate App;
  - App options и durable state `/data` восстановлены;
  - сохранённый runtime target комнаты пережил restore;
  - App вернулся в started state версии 0.1.15;
- финальная очистка:
  - временные MQTT fixtures удалены;
  - room temperature вернулась к 21.0 °C;
  - season вернулся в OFF;
  - window state вернулся в not_configured;
  - aggregate Problem вернулся в off/count 0.

## Автоматические gates репозитория

Та же revision покрывается CI репозитория:

- Python compile;
- unit и cross-module acceptance tests;
- validation YAML;
- validation shell syntax;
- build HAOS container.

## Статус релиза

**Runtime acceptance и immutable publication завершены.**

Опубликованный релиз:

- tag: `digitalhouses_climate_app-v0.1.15`;
- release commit: `cfbcc28b856a6d34f6e5892fa7b6aa9f477334a3`;
- image: `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.15`;
- manifest digest: `sha256:2ce86ebdd1a788ca3fbd9357ec0ae4ddef66818008c684559a58192770481997`;
- release workflow run: `36267401820`.

Канонический tag создан из проверенного release commit в `main`. Release workflow проверил, что versioned GHCR destination и GitHub Release ещё не использовались, до публикации.

Опубликованная immutable image version не может быть перезаписана другим содержимым.
