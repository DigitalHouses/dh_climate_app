# DigitalHouses Climate App 0.1.21 — приёмочное тестирование HAOS

Дата: 2026-09-27

## Область проверки

Версия `0.1.21` проверена на реальной установке Home Assistant OS с bundled acceptance harness.

Этот релиз уменьшает лишние записи Home Assistant Recorder от MQTT facade entities, не отключая полезную историю.

## Результат Recorder churn

Live run подтвердил:

- `climate.dh_climate_app_season` больше не содержит per-recalculation атрибут `observed_at`;
- facades наружной температуры и влажности содержат стабильные source attributes;
- при неизменных values и sources обе outdoor facade entities сохранили ровно те же `last_updated` Home Assistant между runtime ticks;
- новый acceptance gate сообщил:
  `PASS stable outdoor facades do not update every runtime tick`;
- source failover и source recovery продолжают обновлять facades, когда данные действительно меняются;
- avg24, room climate и поведение actuators не затронуты.

Regression suite репозитория также доказывает, что продвижение только внутреннего observation clock на десять секунд при неизменных публичных climate/weather данных не создаёт второй MQTT publication ни для outdoor/season state, ни для weather precipitation state.

## Изменения MQTT contract

Релиз устраняет синтетический state churn:

- удалён `observed_at` из attributes season, outdoor и weather entities;
- topics attributes температуры и влажности разделены;
- из avg24 sensor удалены dynamic JSON attributes;
- topics attributes precipitation type и amount разделены;
- public season humidity attributes округляются до одного знака;
- legacy shared retained attribute topics очищаются на startup.

## Результат регрессии

Bundled live run также прошёл:

- отдельный outdoor temperature avg24 sensor;
- failover primary/backup и preferred-source recovery;
- logging outdoor temperature/source и source-change Event;
- нативную семантику room HEAT / COOL / OFF;
- native presets day / night / away;
- target-range safety;
- bounded no-confirmation retry/cooldown recovery;
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
recorder churn guard = green
stable outdoor last_updated across runtime tick = green
outdoor source failover/recovery = green
full existing regression suite = green
Climate-App-only backup/restore = green
final clean baseline = green
runtime acceptance = PASS
```

## Статус релиза

Runtime acceptance и immutable publication завершены.

Опубликованный релиз:

- tag: `digitalhouses_climate_app-v0.1.21`;
- release commit: `0c53d1ffb11d205daffd08ee9ae836ecaa508a01`;
- image: `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.21`;
- manifest digest: `sha256:5870a9e2791fadc76165f2a5c604cf7d1f84d7448de5e5401721be2a63045349`;
- release workflow run: `36282433114`.

Опубликованная immutable image version не может быть перезаписана другим содержимым.
