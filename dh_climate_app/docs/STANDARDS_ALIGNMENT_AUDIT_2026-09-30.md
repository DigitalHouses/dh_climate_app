# DigitalHouses Climate App — аудит соответствия стандартам

Дата: 2026-09-30

Базовая точка аудита:

- репозиторий Climate: `DigitalHouses/dh_climate_app`
- Climate `main`: `df00d19c366ce78ecab24bdf5463d8203465c332`
- общий репозиторий стандартов: `DigitalHouses/home-assistant-apps`
- shared standards `main`: `5bd27f4b4acf6bd3cc2a6bfec21b64fd1ca6d83c`
- канонический продукт: `digitalhouses_climate_app`
- стабильный префикс сущностей Home Assistant: `dh_climate_app`
- существующий slug Home Assistant App: `dh_climate_app`

Стандарты в `home-assistant-apps/docs/standards/` являются нормативными. Этот репозиторий не копирует и не форкает их.

## Матрица аудита

| # | Область | Статус | Доказательство / требуемое действие |
| --- | --- | --- | --- |
| 1 | Каноническая идентичность продукта / naming | PASS | Telemetry использует `digitalhouses_climate_app`; release tags используют `digitalhouses_climate_app-v<version>`; GHCR использует `ghcr.io/digitalhouses/digitalhouses_climate_app:<version>`; shared registry объявляет canonical ID и entity prefix `dh_climate_app`. |
| 2 | Идентичность GitHub repository | PASS | Climate остаётся отдельным публичным репозиторием `DigitalHouses/dh_climate_app` как осознанная граница продукта. В monorepo он не переносится. |
| 3 | Home Assistant App slug / compatibility | GAP | Установленный slug — `dh_climate_app`. Он чувствителен к совместимости и не должен переименовываться косметически. Shared registry должен хранить фактический legacy slug и pending controlled migration target. Любой будущий переход на `digitalhouses_climate_app` требует отдельно спроектированной reinstall/migration процедуры с сохранением options, `/data`, backup/restore и жизненного цикла установленного продукта. |
| 4 | HA entity prefix / MQTT device / unique IDs | PASS | Discovery использует entity IDs/unique IDs с `dh_climate_app` и MQTT namespace `DigitalHouses/Global/dh_climate_app`. System device ID — `dh_climate_app`; room devices остаются стабильными дочерними устройствами через `via_device`. Косметическое переименование не требуется. |
| 5 | Version / changelog / release tag | GAP | Development-версия `0.1.26` согласована между `config.yaml`, Dockerfile, pyproject и CHANGELOG, последний опубликованный релиз — `0.1.21`. Standalone workflow намеренно допускает development versions в `main`, тогда как shared release policy трактует изменение version source как release intent. Семантику standalone release trigger нужно выровнять, не опубликовав случайно текущий не прошедший acceptance development build. |
| 6 | Immutable GHCR delivery / provenance | GAP | Для опубликованного `0.1.21` зафиксирована полная цепочка tag → commit → GHCR tag → digest: tag `digitalhouses_climate_app-v0.1.21`, commit `0c53d1ffb11d205daffd08ee9ae836ecaa508a01`, image `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.21`, digest `sha256:5870a9e2791fadc76165f2a5c604cf7d1f84d7448de5e5401721be2a63045349`. Однако в `config.yaml` отсутствует `image:`, поэтому Supervisor всё ещё доставляет App через source build, а не из registry. |
| 7 | Runtime metadata: Version + Started at | PASS | MQTT Discovery публикует `sensor.dh_climate_app_version` и `sensor.dh_climate_app_started_at`; Started at — timestamp diagnostic, создаваемый один раз на процесс, Version берётся из `APP_VERSION`. |
| 8 | Machine events / notifications | PASS | Одна MQTT Event entity `event.dh_climate_app_event`, schema v2, QoS 1, non-retained; payloads содержат машинные данные и публикуются после current state/problem. Публичного notification envelope нет. |
| 9 | Config validation | PASS | Supervisor schema вместе с типизированным `parse_options()` проверяют entity domains, диапазоны targets, конфликты ownership, ограничения FAST/SLOW, требования humidity и глобальные thresholds. Unit tests покрывают положительные и отрицательные случаи конфигурации. |
| 10 | Persistent state / no-silent-fallback | GAP | SQLite находится в `/data`, persistence явный, но несколько reads молча синтезируют runtime state при отсутствии/невалидности durable rows: previous HVAC action → `off`; отсутствующий climate-control row → enabled; отсутствующий humidity previous-active → false; отсутствующий humidity-control row → enabled. Telemetry v1 также молча генерирует новую identity при повреждённой persisted identity. Нужен явный contract-error/recovery design вместо скрытых безопасно выглядящих значений. |
| 11 | Backup / restore | GAP | Релиз `0.1.21` прошёл реальный HAOS App-only backup/restore с сохранением persistent state. Текущие development-изменения `0.1.26` ещё не прошли новый live restore acceptance, а registry-backed immutable delivery ещё не завершена. |
| 12 | Recorder churn / publish-on-change | PASS | MQTT adapter дедуплицирует retained payloads; Recorder-facing outdoor/weather payloads не содержат per-tick timestamps; текущий `main` дополнительно ограничивает публикацию RAW diagnostic максимум одним разом в минуту, сохраняя мгновенный internal safety input. CI на `df00d19...` зелёный. |
| 13 | Telemetry Policy v2 | GAP | Текущая реализация — policy v1 с пользовательским opt-out `telemetry_enabled` и `telemetry_policy_version=1`; Delete не ротирует UUID/token. Shared source содержит DigitalHouses Stats `0.4.1`, Climate находится в allowlist, но production deployment Stats 0.4.1+ независимо не подтверждён, поэтому release gate policy v2 остаётся закрыт. |
| 14 | Public docs/examples / отсутствие private dependencies | GAP | Публичная документация/примеры в основном переиспользуемы, но runtime logging вызывает site-local `script.write2climatelog`. Shared standards запрещают зависимость публичного reusable product от private services. App log и machine events достаточны как публичные механизмы; любой локальный mirror должен быть вне публичного App. В документации также оставались устаревшие формулировки до native modes/presets и immutable delivery; phase-1 исправляет их. |
| 15 | CI / validators / release tooling | GAP | Текущий `main` CI компилирует Python, запускает unit tests, валидирует YAML/shell и строит amd64 image; последний run `main` зелёный. Release workflow валидирует canonical tag, commit ancestry, image immutability и фиксирует digest. Остались gaps: product tests явно требовали отсутствие `image:`; release semantics отличаются от shared version-change release intent; пока нет mechanical guard для private runtime dependencies и no-silent-fallback persistent state. Phase-1 удаляет тест, закрепляющий source-build gap, и добавляет canonical release-workflow assertions. |
| 16 | HAOS acceptance | GAP | Последний полный live acceptance завершён для опубликованного `0.1.21`. Текущий development `0.1.26` содержит изменения EMA/RAW/avg24 и Recorder churn, поэтому перед релизом требуется новый полный HAOS acceptance. Delivery, telemetry-v2, persistent-state contract changes и любая slug migration требуют соответствующего отдельного live acceptance. |

## Gaps, чувствительные к совместимости

Их нельзя смешивать с косметической очисткой:

1. **HAOS slug** — `dh_climate_app` является установленной Supervisor identity. Будущая миграция на canonical slug должна сохранять options, `/data`, backup/restore и непрерывность installation через явную контролируемую процедуру.
2. **MQTT / HA entity identities** — текущие topics `dh_climate_app`, device identifiers, unique IDs и entity IDs — стабильные публичные runtime interfaces. Они уже соответствуют canonical entity prefix и не должны переименовываться.
3. **Persistent-state error semantics** — устранение silent fallbacks может изменить recovery behavior. До изменения control path нужен явный design обработки corruption/missing state и acceptance.
4. **Telemetry v2** — удаляет существующую поверхность user opt-out и меняет semantics identity после Delete. Это runtime contract migration, заблокированная до подтверждения production Stats 0.4.1+.
5. **Registry-backed delivery** — добавление `image: ghcr.io/digitalhouses/digitalhouses_climate_app` меняет путь доставки Supervisor. Оно должно сопровождаться HAOS acceptance release/backup/restore.
6. **Удаление private climate-log mirror** — это не часть climate decision logic, но меняет runtime diagnostic side channel и всё равно требует regression/live acceptance.

## Безопасные изменения Phase 1

Ветка standards-alignment phase-1 намеренно не меняет runtime climate control.

Безопасные изменения:

- исправить публичную документацию room facade по фактическим season-native режимам `off/heat`, `off/cool`, `off` и native presets `day/night/away`;
- точно описать разницу между GHCR publication и текущей source-build delivery Supervisor;
- обновить HAOS acceptance gates для текущего поведения `0.1.26` и общей backup/telemetry policy;
- перестать требовать в CI отсутствие известного поля `image:`;
- добавить product-contract assertions для canonical Climate release tag/image/provenance workflow.

Shared product registry должен отдельно зафиксировать существующий slug `dh_climate_app` как compatibility exception с pending controlled-reinstall target `digitalhouses_climate_app`.

## Требуемые следующие миграции

Рекомендуемая последовательность:

1. merge безопасной очистки docs/contract tests;
2. merge исправления shared registry для фактического legacy Climate slug;
3. спроектировать и реализовать no-silent-fallback persistent-state handling с unit tests, не меняя климатические решения при валидном state;
4. удалить публичную runtime-зависимость `script.write2climatelog`, сохранив authoritative App logging и machine events;
5. перевести delivery Supervisor на canonical versioned GHCR image и выполнить live acceptance backup/restore;
6. выровнять standalone release automation с shared release provenance без публикации не прошедшего acceptance development build;
7. подтвердить production DigitalHouses Stats 0.4.1+;
8. только после этого реализовать Telemetry Policy v2 и выполнить live acceptance heartbeat/Delete/identity rotation;
9. запустить полный HAOS climate acceptance suite на release candidate;
10. рассматривать slug migration только как отдельный controlled migration project, а не часть общей очистки стандартов.

Не объявлять `gaps = 0`, пока реально не закрыты release-delivery, persistent-state, telemetry-v2, backup/restore и требуемые live-acceptance gates.
