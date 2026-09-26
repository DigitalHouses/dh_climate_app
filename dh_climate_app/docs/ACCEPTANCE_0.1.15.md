# DigitalHouses Climate App 0.1.15 — HAOS acceptance

Date: 2026-09-27  
Environment: real Home Assistant OS installation  
App ID: `8d59ce70_dh_climate_app`  
Version: `0.1.15`

## Result

**Bundled live runtime acceptance: PASS**

The acceptance harness ran against the real Home Assistant Supervisor/Core/MQTT
boundaries. Physical HVAC equipment was not commandeered; temporary MQTT
Discovery fixtures were used for deterministic actuator fault and safety cases.
Hardware commissioning remains installation-specific and is not a software
release gate.

## Passed live gates

- App update/start at 0.1.15.
- Clean baseline: Problem off, room temperature 21.0 °C, season thresholds
  15.0 / 29.8 °C.
- `device_target_out_of_range`:
  - out-of-range climate target was blocked;
  - no forbidden actuator command was accepted;
  - Problem/Event v2 transition carried room/entity/details;
  - recovery cleared the Problem and actuator converged normally.
- `device_no_confirmation`:
  - bounded retries reached RETRY 2/3 and RETRY 3/3;
  - final confirmation window expired before COOLDOWN 300s;
  - later state confirmation recovered the Problem and reached VERIFIED_HA.
- SLOW floor policy:
  - HEAT season kept the SLOW thermostat in heat at its separate 27 °C target
    while room air demand was idle;
  - OFF season turned the SLOW thermostat off.
- Window policy:
  - room demand truth remained heating while the window was open;
  - only the actuator listed in `window_off_devices` was inhibited;
  - closing the window restored that actuator.
- Cold-weather reversible-climate protection:
  - reversible heating was inhibited below -10 °C;
  - other heating sources continued;
  - heating restored above the threshold;
  - cooling remained allowed below the heating-only protection threshold.
- Humidity:
  - humidity facade and physical humidifier path became active;
  - an active out-of-range physical humidity target raised
    `device_target_out_of_range`;
  - switching humidity control off still powered the physical humidifier off,
    proving target validation cannot block shutdown.
- Supervisor backup/restore:
  - a partial backup containing only the Climate App was created;
  - App options and durable `/data` state were restored;
  - persisted runtime room target state survived restore;
  - App returned to 0.1.15 started state.
- Final cleanup:
  - temporary MQTT fixtures were removed;
  - room returned to 21.0 °C;
  - season returned to OFF;
  - window state returned to not_configured;
  - aggregate Problem returned to off/count 0.

## Automated repository gates

The same revision is also covered by repository CI for:

- Python compile;
- unit and cross-module acceptance tests;
- YAML validation;
- shell syntax validation;
- HAOS container build.

## Release status

The **runtime acceptance gate is complete**.

The remaining release-publication gate is operational rather than behavioral:

1. create canonical tag `digitalhouses_climate_app-v0.1.15`;
2. let the release workflow build/push the immutable multi-architecture image;
3. verify the GitHub Release and GHCR provenance/digest.

No published immutable image version may be overwritten with different content.
