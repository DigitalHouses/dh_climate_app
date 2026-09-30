# DigitalHouses Climate App — Product & Configuration Manifest

**Version:** 0.1  
**Date:** 2026-09-30  
**Status:** first normative baseline  
**Scope:** product boundaries, configuration ownership, Home Assistant UI contract, and the FAST/SLOW thermal model.

This document freezes the product principles that should guide further dh_climate_app development. It is intentionally smaller than the full architecture specification. It defines **where configuration belongs and what the user should see**, not every control algorithm.

When implementation details evolve, they should preserve this contract unless this manifest is explicitly revised.

---

## 1. Product model

The user-facing abstraction is the **room thermostat**.

A room owns the desired air temperature and presents one native Home Assistant climate entity. Physical devices are executors behind that room abstraction.

The main thermal path is:

    global season
        ↓
    effective room profile
        ↓
    room target
        ↓
    stateful room thermostat
        ↓
    FAST device demand
        ↓
    device-specific desired state
        ↓
    Home Assistant service reconciliation

SLOW heating is a separate seasonal path:

    global season
        ↓
    SLOW heating enable / disable
        ↓
    local physical thermostat

The compact App must preserve useful climate behavior without recreating the previous PostgreSQL orchestration system.

---

## 2. Configuration ownership

The system has three distinct configuration/state layers.

### 2.1 App YAML/options = installation topology

Home Assistant App options describe **what is installed and where it is connected**.

Typical YAML-owned facts:

- global Home Assistant fact bindings such as night_mode and we_at_home;
- outdoor temperature/humidity source bindings;
- room identity and display name;
- room temperature/humidity sensor bindings;
- window-contact bindings;
- FAST heating actuator bindings;
- FAST cooling actuator bindings;
- SLOW heating actuator bindings;
- exceptional hardware binding/policy that cannot be safely inferred from Home Assistant capabilities.

YAML must not become the operational settings database.

A healthy room record should remain close to:

    rooms:
      - id: living_room
        name: Living Room
        temperature_sensors: sensor.living_room_temperature
        fast_heat: switch.living_room_convector
        fast_cool: climate.living_room_ac
        slow_heat: climate.living_room_floor

Optional bindings are added only when the installation actually requires them.

### 2.2 Home Assistant entities = editable climate policy

Parameters that an owner/installer may change after commissioning should be exposed as native Home Assistant entities, normally through MQTT Discovery.

Use the native domain matching the value:

- number for numeric settings;
- select for enumerated policies;
- switch only for genuine boolean policy choices;
- climate for normal room thermostat interaction;
- sensor / binary_sensor for state and diagnostics.

Examples of editable policy/settings:

- Heat Day / Night / Away targets;
- Heat Antifreeze target;
- Cool Day / Night / Away targets;
- SLOW heating target;
- device target offsets;
- fan limits/policies;
- future window reaction choices;
- global climate tuning that is meaningful to an installer.

These values should not need YAML edits for routine commissioning or later adjustment.

### 2.3 SQLite = persisted truth

SQLite under /data stores durable App state.

For settings represented by MQTT configuration entities:

    HA command
    → App validation
    → SQLite
    → climate recomputation
    → MQTT state publication

On restart:

    SQLite
    → App runtime
    → retained MQTT state
    → Home Assistant UI

**SQLite wins over retained MQTT command/state history.**

Retained MQTT is a transport/UI continuity mechanism, not a competing persistence authority.

---

## 3. Defaults and first creation

Built-in product defaults are used only to seed a setting when it does not yet exist.

Example:

    room first appears
    → setting absent in SQLite
    → seed product default
    → persist
    → publish HA configuration entity

After creation, upgrading or reloading App configuration must not silently replace a user's persisted setting with a new default.

A new setting introduced by a later version may be seeded once during migration.

Defaults should not be repeated per room in YAML.

---

## 4. Room thermostat contract

Each configured room exposes one primary MQTT climate entity.

The room thermostat is the normal client control surface.

It owns:

- current room temperature;
- current humidity when useful;
- current season-compatible target;
- season-compatible HVAC modes;
- HVAC action;
- normal target adjustment.

Season capability remains native:

    HEAT → off / heat
    COOL → off / cool
    OFF  → off

Opposite-season thermal actions are forbidden.

Internal Day / Night / Away profile targets remain part of the control model, but they are **not normal client-facing controls**.

Antifreeze is an internal HEAT protection profile and is not a normal client preset.

---

## 5. FAST thermal devices

FAST means low enough thermal inertia that the device participates in active room-temperature regulation.

Typical examples:

- radiator;
- convector;
- fan-coil;
- air conditioner;
- other responsive room heating/cooling equipment.

FAST devices follow room thermostat demand:

    room heating → FAST heat devices active
    room cooling → FAST cool devices active
    room idle/off → corresponding FAST devices inactive

The room thermostat decides demand. A FAST device must not independently reinterpret room temperature into a second competing thermostat algorithm.

For smart climate executors, device-specific transformation may later include:

- target-temperature offset;
- device min/max/step normalization;
- fan policy;
- supported-mode mapping.

Those are device execution details, not reasons to move the room target itself into YAML.

---

## 6. SLOW thermal devices

SLOW means a high-inertia heating system whose normal operation should not cycle with the room-air thermostat.

Primary case: **hydronic underfloor heating** with its own local thermostat/probe.

Canonical behavior:

    season == HEAT  → SLOW heating enabled
    season != HEAT  → SLOW heating disabled

A SLOW local climate thermostat receives its own SLOW target. Its local physical thermostat performs the actual cycling.

The SLOW target is separate from the room-air target.

Room hysteresis must not repeatedly switch SLOW heating on and off.

This FAST/SLOW distinction describes thermal control behavior, not a generic framework that must be generalized prematurely.

---

## 7. TRV scope

TRVs are **out of scope for the new core climate App**.

They must not drive additional core device classes, special synchronization logic, or PostgreSQL-era abstractions.

If TRVs are required at a site, handle them separately, for example with Home Assistant automation based on the global HEAT season.

This decision may be revisited only with a concrete device/use case that justifies bringing TRV behavior into the App.

---

## 8. Client UI contract

Client-facing room UI must remain deliberately small.

Default room surface:

1. the room thermostat;
2. only a small number of additional controls that have a clear everyday meaning to the client.

Possible client-visible examples:

- maximum fan speed;
- window-open reaction.

A setting is client-facing only when it answers an understandable household question without requiring knowledge of internal climate architecture.

The following are **not normal client-facing controls**:

- Heat Day / Night / Away internal targets;
- Cool Day / Night / Away internal targets;
- antifreeze target;
- hysteresis;
- EMA/filter parameters;
- device target offsets;
- SLOW engineering target unless deliberately exposed for a particular product UX;
- fan boost threshold;
- device capability mappings;
- low-level safety thresholds.

The user interacts primarily with the thermostat. Automation profiles remain under the hood.

---

## 9. Admin UI contract

Engineering/system parameters remain available in Home Assistant for commissioning, debugging, and maintenance.

They are rendered on a separate **DH Climate Admin** dashboard.

Configuration entities should normally use:

    entity_category = config

and belong to the most appropriate MQTT Device:

- system-wide setting → DigitalHouses Climate system Device;
- room setting → room MQTT Device;
- device-specific setting → the owning room Device unless a stronger future device model is justified.

The Admin dashboard should be generated as automatically as practical, for example through Auto-Entities, so newly introduced configuration entities do not require manual dashboard edits.

Do not add metadata solely to build an elaborate UI framework. Start with native Home Assistant properties and add only minimal stable metadata when a real filtering/sorting need appears.

---

## 10. UI discoverability metadata

Initial rule:

- native Home Assistant device ownership;
- native entity_category: config;
- stable DigitalHouses entity IDs / unique IDs.

If client/admin filtering cannot be expressed reliably with native Home Assistant metadata, add **one minimal stable UI classification attribute** rather than a large presentation schema.

Potential future value:

    dh_climate_ui = client | admin

Do not add section/order/device metadata until the dashboard implementation demonstrates a real need.

---

## 11. Recorder discipline

Operational configuration entities are not high-frequency telemetry.

Time-series sensor entities should remain lean and avoid dynamic attribute churn.

Configuration metadata may contain a small number of stable attributes where needed for UI discovery, because these entities are not intended as high-frequency measurements.

Do not attach rapidly changing diagnostic payloads to configuration entities.

---

## 12. Device capabilities

The App should use Home Assistant device/entity capabilities wherever they are trustworthy, including:

- supported HVAC modes;
- min/max target temperature;
- target temperature step;
- supported fan modes.

Do not duplicate discoverable capabilities into YAML without a demonstrated compatibility need.

Hardware-specific overrides may exist when Home Assistant cannot expose the required truth reliably.

---

## 13. Window policy

Window state is device context, not room thermostat truth.

Opening a window must not rewrite the room target or invent a different thermostat state.

A device may be inhibited by an explicit window policy.

The exact client-facing window reaction control is still subject to product design. The initial principle is:

- internal policy is configurable;
- only a simple understandable reaction, if any, is exposed to the client;
- detailed policy remains on the Admin side.

---

## 14. Fan policy

The exact dynamic fan algorithm is not frozen by this manifest.

Current direction:

    room temperature error
    → requested fan level
    → profile/client maximum fan constraint
    → device-supported fan mapping
    → desired device command

A large temperature error may request maximum fan, while a Night or client maximum may cap the result.

The eventual policy should remain compact and must not create repeated per-room YAML fields.

---

## 15. Device target transformation

Room target and physical device target are separate concepts.

Example:

    room target = 24 °C
    device cool offset = -3 °C
    → raw device target = 21 °C

The device target is then normalized against physical device capabilities.

Target offsets are commissioning/device settings and should normally be editable through Home Assistant configuration entities and persisted in SQLite, not repeated as operational YAML values.

---

## 16. Safety and unresolved HEAT fallback

HEAT season has a protection requirement: the building must not freeze merely because normal room control is disabled.

However, loss of room-temperature truth must not cause an unsafe unconditional ON command to a dumb actuator.

The exact fail-safe policy for missing room temperature remains intentionally open and must be resolved by actuator control authority/capability.

Examples to evaluate later:

- local thermostatic climate device with valid internal regulation;
- simple binary relay without independent temperature safety;
- fallback room sensor;
- separately configured safety thermostat.

This question must be resolved explicitly before declaring the HEAT fail-safe complete.

---

## 17. Generalized logical-device model

The existing architecture document explores future properties such as:

- roles;
- inertia;
- control source;
- control profile;
- scope;
- equipment ID.

These concepts may remain useful for future ventilation or more complex installations, but they are **not a requirement for the current thermal App**.

Current implementation should prefer the smallest model that correctly expresses:

    FAST heat
    FAST cool
    SLOW heat

Do not introduce a generic device framework merely because one can be designed.

---

## 18. Explicit non-goals

The following must not return through this refactor:

- PostgreSQL as business engine;
- SQL job orchestration;
- Matrix/Firewall/Dispatcher/UC/Confirmator as literal runtime layers;
- per-room YAML copies of operational targets;
- TRV-specific core complexity;
- UI exposing every internal parameter to the client;
- duplicate sources of truth between YAML, MQTT retained state, and SQLite;
- generic abstraction layers without a demonstrated current use case.

---

## 19. Target ownership summary

| Concern | Owner |
| --- | --- |
| Physical entity binding | App YAML/options |
| Room sensor binding | App YAML/options |
| FAST/SLOW membership | App YAML/options |
| Day/Night/Away/Antifreeze targets | SQLite + HA config entities |
| SLOW target | SQLite + HA config entity |
| Device target offset | SQLite + HA config entity |
| Fan tuning/policy | SQLite + HA config entities |
| Room thermostat target interaction | HA climate facade → SQLite |
| Persistent runtime truth | SQLite |
| MQTT retained state | UI/transport continuity |
| Client dashboard | thermostat + minimal understandable controls |
| Admin dashboard | complete commissioning/system controls |

---

## 20. Change rule

A new configuration field should pass this test before being added to YAML:

> Does this field describe **what is physically installed or how it is bound to Home Assistant**?

If no, it should normally be a persisted Home Assistant configuration entity instead.

A new client-facing entity should pass this test:

> Does this control answer a normal household question without exposing implementation details?

If no, it belongs on the Admin side.

These two tests are the default guardrails against configuration and UI bloat.
