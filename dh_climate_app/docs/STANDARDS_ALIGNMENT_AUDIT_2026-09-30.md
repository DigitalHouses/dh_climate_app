# DigitalHouses Climate App — standards alignment audit

Date: 2026-09-30

Audit baseline:

- Climate repository: `DigitalHouses/dh_climate_app`
- Climate `main`: `df00d19c366ce78ecab24bdf5463d8203465c332`
- Shared standards repository: `DigitalHouses/home-assistant-apps`
- Shared standards `main`: `5bd27f4b4acf6bd3cc2a6bfec21b64fd1ca6d83c`
- Canonical product: `digitalhouses_climate_app`
- Stable Home Assistant entity prefix: `dh_climate_app`
- Existing Home Assistant App slug: `dh_climate_app`

The shared standards under `home-assistant-apps/docs/standards/` are normative.
This repository does not copy or fork them.

## Audit matrix

| # | Area | Status | Evidence / required action |
| --- | --- | --- | --- |
| 1 | Canonical product identity / naming | PASS | Telemetry uses `digitalhouses_climate_app`; release tags use `digitalhouses_climate_app-v<version>`; GHCR uses `ghcr.io/digitalhouses/digitalhouses_climate_app:<version>`; shared registry declares canonical ID and `dh_climate_app` entity prefix. |
| 2 | GitHub repository identity | PASS | Climate remains the standalone public repository `DigitalHouses/dh_climate_app` as an intentional product boundary. It is not moved into the monorepo. |
| 3 | Home Assistant App slug / compatibility | GAP | Installed slug is `dh_climate_app`. This is compatibility-sensitive. It must not be renamed cosmetically. Shared registry must record the actual legacy slug and a pending controlled migration target. Any future change to `digitalhouses_climate_app` requires a separately designed reinstall/migration preserving options, `/data`, backup/restore and the installed product lifecycle. |
| 4 | HA entity prefix / MQTT device / unique IDs | PASS | Discovery uses `dh_climate_app` entity IDs/unique IDs and MQTT namespace `DigitalHouses/Global/dh_climate_app`. System device ID is `dh_climate_app`; room devices remain stable children via `via_device`. No cosmetic rename is required. |
| 5 | Version / changelog / release tag | GAP | Current development version `0.1.26` is consistent across `config.yaml`, Dockerfile, pyproject and CHANGELOG, while the last published release is `0.1.21`. The standalone workflow intentionally leaves development versions on `main`, whereas the shared release policy treats version-source change as release intent. The standalone release trigger semantics must be aligned without accidentally publishing the current unaccepted development build. |
| 6 | Immutable GHCR delivery / provenance | GAP | Published `0.1.21` has a complete recorded tag → commit → GHCR tag → digest chain: tag `digitalhouses_climate_app-v0.1.21`, commit `0c53d1ffb11d205daffd08ee9ae836ecaa508a01`, image `ghcr.io/digitalhouses/digitalhouses_climate_app:0.1.21`, digest `sha256:5870a9e2791fadc76165f2a5c604cf7d1f84d7448de5e5401721be2a63045349`. However `config.yaml` omits `image:`, so Supervisor delivery is still source-build rather than registry-backed. |
| 7 | Runtime metadata: Version + Started at | PASS | MQTT Discovery exposes `sensor.dh_climate_app_version` and `sensor.dh_climate_app_started_at`; Started at is a timestamp diagnostic generated once per process and Version comes from `APP_VERSION`. |
| 8 | Machine events / notifications | PASS | One MQTT Event entity `event.dh_climate_app_event`, schema v2, QoS 1, non-retained; event payloads are machine data and are emitted after current state/problem publication. No public notification envelope exists. |
| 9 | Config validation | PASS | Supervisor schema plus typed `parse_options()` validation enforce entity domains, target ranges, ownership conflicts, FAST/SLOW constraints, humidity requirements and global thresholds. Unit tests cover positive and negative configuration cases. |
| 10 | Persistent state / no-silent-fallback | GAP | SQLite is under `/data` and persistence is explicit, but several reads silently synthesize runtime state when durable rows are missing/invalid: previous HVAC action → `off`; climate-control missing row → enabled; humidity previous-active missing row → false; humidity-control missing row → enabled. Telemetry v1 also silently regenerates malformed persisted identity. These paths require an explicit contract-error/recovery design rather than hidden safe-looking values. |
| 11 | Backup / restore | GAP | Released `0.1.21` passed real HAOS App-only backup/restore and preserved persistent state. Current `0.1.26` development changes have not yet passed a new live restore acceptance, and registry-backed immutable delivery is not yet complete. |
| 12 | Recorder churn / publish-on-change | PASS | MQTT adapter deduplicates retained payloads; recorder-facing outdoor/weather payloads avoid per-tick timestamps; current `main` additionally caps RAW diagnostic publication to at most once per minute while keeping internal safety input immediate. CI on `df00d19...` is green. |
| 13 | Telemetry Policy v2 | GAP | Current implementation is policy v1 with user `telemetry_enabled` opt-out and `telemetry_policy_version=1`; Delete does not rotate UUID/token. Shared source contains DigitalHouses Stats `0.4.1` and Climate is allowlisted, but production deployment of Stats 0.4.1+ has not been independently confirmed, so the policy-v2 release gate remains closed. |
| 14 | Public docs/examples / no private dependencies | GAP | Public docs/examples are mostly reusable, but runtime logging calls site-local `script.write2climatelog`. Shared standards forbid reusable public product dependence on private services. The App log and machine events are sufficient public mechanisms; any local mirror belongs outside the public App. Documentation also contained stale pre-native-mode/preset wording and stale immutable-delivery wording; the phase-1 branch corrects those docs. |
| 15 | CI / validators / release tooling | GAP | Current `main` CI compiles Python, runs unit tests, validates YAML/shell and builds an amd64 image; latest `main` run is green. Release workflow validates canonical tag, commit ancestry, image immutability and records digest. Gaps remain: product tests were explicitly enforcing absence of `image:`; release semantics differ from shared version-change release intent; no mechanical guard yet covers private runtime dependencies or no-silent-fallback persistent state. Phase-1 removes the test that enshrines the source-build gap and adds canonical release-workflow assertions. |
| 16 | HAOS acceptance | GAP | Last completed full live acceptance is released `0.1.21`. Current `0.1.26` development contains EMA/RAW/avg24 and Recorder-churn changes and therefore requires a fresh complete HAOS acceptance before release. Delivery, telemetry-v2, persistent-state contract changes and any slug migration each require their own relevant live acceptance. |

## Compatibility-sensitive gaps

These must not be folded into cosmetic cleanup:

1. **HAOS slug** — `dh_climate_app` is an installed Supervisor identity. A future canonical slug migration must preserve options, `/data`, backup/restore and installation continuity through an explicit controlled procedure.
2. **MQTT / HA entity identities** — current `dh_climate_app` topics, device identifiers, unique IDs and entity IDs are stable public runtime interfaces. They are already aligned to the canonical entity prefix and must not be renamed.
3. **Persistent-state error semantics** — removing silent fallbacks can change recovery behavior. Design explicit corruption/missing-state handling and acceptance before touching the control path.
4. **Telemetry v2** — removes the existing user opt-out surface and changes Delete identity semantics. It is a runtime contract migration and is blocked until production Stats 0.4.1+ is confirmed.
5. **Registry-backed delivery** — adding `image: ghcr.io/digitalhouses/digitalhouses_climate_app` changes the Supervisor delivery path. It must be paired with release/backup/restore HAOS acceptance.
6. **Private climate-log mirror removal** — this does not belong to climate decision logic, but it changes a runtime diagnostic side channel and should still receive regression/live acceptance.

## Phase-1 safe changes

The standards-alignment phase-1 branch intentionally makes no climate-control runtime changes.

Safe changes:

- correct public room-facade documentation to the actual season-native `off/heat`, `off/cool`, `off` modes and native `day/night/away` presets;
- describe GHCR publication versus current source-build Supervisor delivery accurately;
- refresh HAOS acceptance gates for current `0.1.26` behavior and current shared backup/telemetry policy;
- stop CI from asserting that the known missing `image:` field is a required state;
- add product-contract assertions for the canonical Climate release tag/image/provenance workflow.

The shared product registry must independently record the existing `dh_climate_app` slug as a compatibility exception with a pending controlled-reinstall target `digitalhouses_climate_app`.

## Required next migrations

Recommended sequence:

1. merge safe docs/contract-test cleanup;
2. merge shared-registry correction for the actual legacy Climate slug;
3. design and implement no-silent-fallback persistent-state handling with unit tests, without changing climate decisions for valid state;
4. remove the public `script.write2climatelog` runtime dependency while keeping authoritative App logging and machine events;
5. migrate Supervisor delivery to the canonical versioned GHCR image and complete backup/restore live acceptance;
6. align standalone release automation with shared release provenance without publishing an unaccepted development build;
7. confirm production DigitalHouses Stats 0.4.1+;
8. only then implement Telemetry Policy v2 and perform live heartbeat/Delete/identity-rotation acceptance;
9. run the complete HAOS climate acceptance suite on the release candidate;
10. consider slug migration only as a separate controlled migration project, not as part of general standards cleanup.

Do not declare `gaps = 0` until the release-delivery, persistent-state, telemetry-v2, backup/restore and required live-acceptance gates are actually closed.
