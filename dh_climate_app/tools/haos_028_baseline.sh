#!/usr/bin/env bash
# DigitalHouses Climate App 0.1.28 · read-only live baseline.
# Только GET Supervisor / HA Core, без изменений состояния системы.
clear
set -uo pipefail

APP="8d59ce70_dh_climate_app"
API="http://supervisor"
printf '========== DIGITALHOUSES CLIMATE · BASELINE =========='
printf '\nMODE: READ-ONLY · %s\nAPP: %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$APP"

if [[ -z "${SUPERVISOR_TOKEN:-}" ]] || ! command -v jq >/dev/null 2>&1; then
  echo 'BLOCKED: требуется SUPERVISOR_TOKEN и jq в терминале HAOS.'
  exit 2
fi
AUTH="Authorization: Bearer ${SUPERVISOR_TOKEN}"

echo '=== 1. SUPERVISOR · CONFIG AND ROOMS ==='
if ! info="$(curl --fail --silent --show-error --max-time 15 -H "$AUTH" "$API/addons/$APP/info")"; then
  echo 'BLOCKED: Supervisor info недоступен.'
  exit 3
fi
if ! jq -e '.result == "ok" and (.data.options | type == "object")' >/dev/null <<< "$info"; then
  echo 'BLOCKED: невалидный ответ Supervisor.'
  exit 3
fi
jq '{
  app: {version: .data.version, version_latest: .data.version_latest,
        update_available: .data.update_available, state: .data.state},
  globals: (.data.options | {
    hysteresis, temperature_hysteresis, humidity_hysteresis,
    heat_threshold_default, cool_threshold_default,
    ac_min_outdoor_temperature, outdoor_temperature_ema_minutes,
    night_mode, we_at_home,
    outdoor_temperature_sources, outdoor_humidity_sources
  }),
  rooms: [(.data.options.rooms // [])[] | {
    id, name, heat_day, heat_night, heat_away, heat_antifreeze,
    cool_day, cool_night, cool_away, humidity_mode, humidity_target,
    temperature_sensors, humidity_sensors, fast_heat, fast_cool,
    slow_heat, slow_target, window_sensors, window_off_devices
  }]
}' <<< "$info"

echo '=== 2. HOME ASSISTANT · PERSISTED MQTT FACADE STATES ==='
if ! states="$(curl --fail --silent --show-error --max-time 25 -H "$AUTH" "$API/core/api/states")"; then
  echo 'BLOCKED: HA Core states недоступны.'
  exit 4
fi
if ! jq -e 'type == "array"' >/dev/null <<< "$states"; then
  echo 'BLOCKED: HA Core вернул неожиданный формат.'
  exit 4
fi
jq '[.[] |
  select(
    (.entity_id | startswith("climate.dh_climate_app_")) or
    (.entity_id | startswith("number.dh_climate_app_")) or
    (.entity_id | startswith("humidifier.dh_climate_app_")) or
    (.entity_id | startswith("sensor.dh_climate_app_outdoor_")) or
    (.entity_id == "binary_sensor.dh_climate_app_problem")
  ) |
  {entity_id, state,
   attributes: (.attributes | {
     temperature, current_temperature, current_humidity,
     target_temp_low, target_temp_high, min_temp, max_temp,
     preset_mode, hvac_modes, hvac_action, humidity,
     unit_of_measurement
   })}
] | sort_by(.entity_id)' <<< "$states"

echo '=== 3. SEASON AND SMARTIR SUMMARY ==='
jq '[.[] | select(.entity_id == "climate.dh_climate_app_season"
                   or .entity_id == "climate.bedroom_ac") |
   {entity_id, state, target_temp_low: .attributes.target_temp_low,
    target_temp_high: .attributes.target_temp_high,
    min_temp: .attributes.min_temp, max_temp: .attributes.max_temp,
    temperature: .attributes.temperature}]' <<< "$states"

echo '========== DONE · READ-ONLY =========='
