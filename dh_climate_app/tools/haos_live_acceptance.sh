#!/usr/bin/env bash
set -Ee -o pipefail

APP="8d59ce70_dh_climate_app"
EXPECTED_VERSION="0.1.16"
CORE="http://supervisor/core"
SUPERVISOR="http://supervisor"
TOKEN="${SUPERVISOR_TOKEN:-}"

BASE="dh_climate_accept"
DISCOVERY="homeassistant"
ROOM_ID="livingroom"

OUTDOOR_SENSOR="sensor.dh_climate_accept_outdoor"
HUMIDITY_SENSOR="sensor.dh_climate_accept_humidity"
WINDOW_SENSOR="binary_sensor.dh_climate_accept_window"
REVERSIBLE="climate.dh_climate_accept_reversible"
NARROW="climate.dh_climate_accept_narrow"
STUBBORN="climate.dh_climate_accept_stubborn"
SLOW="climate.dh_climate_accept_slow"
PHYSICAL_HUMIDIFIER="humidifier.dh_climate_accept_humidifier"

ROOM_CLIMATE="climate.dh_climate_app_livingroom"
SEASON_CLIMATE="climate.dh_climate_app_season"
PROBLEM="binary_sensor.dh_climate_app_problem"
EVENT="event.dh_climate_app_event"
HEAT_DAY="number.dh_climate_app_livingroom_heat_day"
COOL_DAY="number.dh_climate_app_livingroom_cool_day"
ROOM_TEMP_HELPER="input_number.dh_climate_test_livingroom_temperature"
ROOM_TEMP_SENSOR="sensor.dh_climate_test_livingroom_temperature"
HUMIDITY_FACADE="humidifier.dh_climate_app_livingroom"

WORKDIR="/config/.dh_climate_acceptance"
LOG="${WORKDIR}/run_$(date +%Y%m%d_%H%M%S).log"
BASE_OPTIONS_FILE="${WORKDIR}/baseline_options.json"
BASE_STATE_FILE="${WORKDIR}/baseline_state.json"

BACKUP_SLUG=""
BACKUP_RESTORED=0
FIXTURES_CREATED=0
BASE_ROOM_TEMP=""
BASE_HEAT_DAY=""
BASE_COOL_DAY=""
BASE_SEASON_LOW=""
BASE_SEASON_HIGH=""

mkdir -p "$WORKDIR"
exec > >(tee "$LOG") 2>&1

say() {
  printf '\n=== %s ===\n' "$*"
}

fail() {
  echo "FAIL: $*" >&2
  return 1
}

core_get() {
  curl -fsS     -H "Authorization: Bearer ${TOKEN}"     -H "Content-Type: application/json"     "${CORE}/api/${1}"
}

core_post() {
  local path="$1"
  local body="$2"
  curl -fsS     -X POST     -H "Authorization: Bearer ${TOKEN}"     -H "Content-Type: application/json"     -d "$body"     "${CORE}/api/${path}"
}

state_json() {
  core_get "states/$1"
}

state_value() {
  state_json "$1" | jq -r '.state'
}

attr_value() {
  local entity="$1"
  local attr="$2"
  state_json "$entity" | jq -r --arg attr "$attr" '.attributes[$attr] // empty'
}

ha_service() {
  local domain="$1"
  local service="$2"
  local body="$3"
  core_post "services/${domain}/${service}" "$body" >/dev/null
}

mqtt_pub() {
  local topic="$1"
  local payload="$2"
  local retain="${3:-false}"
  local body
  body="$(
    jq -cn       --arg topic "$topic"       --arg payload "$payload"       --argjson retain "$retain"       '{topic:$topic,payload:$payload,qos:1,retain:$retain}'
  )"
  ha_service "mqtt" "publish" "$body"
}

wait_entity() {
  local entity="$1"
  local seconds="${2:-30}"
  local i
  for i in $(seq 1 "$seconds"); do
    if state_json "$entity" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  fail "entity did not appear: $entity"
}

wait_state() {
  local entity="$1"
  local expected="$2"
  local seconds="${3:-30}"
  local i actual
  for i in $(seq 1 "$seconds"); do
    actual="$(state_value "$entity" 2>/dev/null || true)"
    if [ "$actual" = "$expected" ]; then
      return 0
    fi
    sleep 1
  done
  actual="$(state_value "$entity" 2>/dev/null || true)"
  fail "$entity state=$actual expected=$expected"
}

wait_attr() {
  local entity="$1"
  local attr="$2"
  local expected="$3"
  local seconds="${4:-30}"
  local i actual
  for i in $(seq 1 "$seconds"); do
    actual="$(attr_value "$entity" "$attr" 2>/dev/null || true)"
    if [ "$actual" = "$expected" ]; then
      return 0
    fi
    sleep 1
  done
  actual="$(attr_value "$entity" "$attr" 2>/dev/null || true)"
  fail "$entity.$attr=$actual expected=$expected"
}

wait_numeric_state_present() {
  local entity="$1"
  local seconds="${2:-30}"
  local i
  for i in $(seq 1 "$seconds"); do
    if state_json "$entity" 2>/dev/null | jq -e '.state | tonumber' >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  fail "$entity did not become numeric"
}

wait_numeric_attr_present() {
  local entity="$1"
  local attr="$2"
  local seconds="${3:-30}"
  local i
  for i in $(seq 1 "$seconds"); do
    if state_json "$entity" 2>/dev/null | jq -e --arg attr "$attr" '.attributes[$attr] | tonumber' >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  fail "$entity.$attr did not become numeric"
}
wait_number() {
  local entity="$1"
  local expected="$2"
  local seconds="${3:-30}"
  local i actual
  for i in $(seq 1 "$seconds"); do
    actual="$(state_value "$entity" 2>/dev/null || true)"
    if awk -v a="$actual" -v b="$expected" 'BEGIN{exit !((a-b<0?b-a:a-b)<0.051)}'; then
      return 0
    fi
    sleep 1
  done
  actual="$(state_value "$entity" 2>/dev/null || true)"
  fail "$entity=$actual expected≈$expected"
}

wait_numeric_attr() {
  local entity="$1"
  local attr="$2"
  local expected="$3"
  local seconds="${4:-30}"
  local i actual
  for i in $(seq 1 "$seconds"); do
    actual="$(attr_value "$entity" "$attr" 2>/dev/null || true)"
    if awk -v a="$actual" -v b="$expected" 'BEGIN{exit !((a-b<0?b-a:a-b)<0.051)}'; then
      return 0
    fi
    sleep 1
  done
  actual="$(attr_value "$entity" "$attr" 2>/dev/null || true)"
  fail "$entity.$attr=$actual expected≈$expected"
}

problem_has() {
  local code="$1"
  local entity="${2:-}"
  state_json "$PROBLEM" | jq -e     --arg code "$code"     --arg entity "$entity" '
      (.attributes.problems // []) |
      any(
        .code == $code and
        ($entity == "" or .entity_id == $entity)
      )
    ' >/dev/null
}

wait_problem() {
  local code="$1"
  local entity="${2:-}"
  local seconds="${3:-45}"
  local i
  for i in $(seq 1 "$seconds"); do
    if problem_has "$code" "$entity" 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  state_json "$PROBLEM" | jq .
  fail "problem not observed: code=$code entity=$entity"
}

wait_no_problem() {
  local code="$1"
  local entity="${2:-}"
  local seconds="${3:-30}"
  local i
  for i in $(seq 1 "$seconds"); do
    if ! problem_has "$code" "$entity" 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  state_json "$PROBLEM" | jq .
  fail "problem did not recover: code=$code entity=$entity"
}

wait_app_started() {
  local seconds="${1:-90}"
  local i state
  for i in $(seq 1 "$seconds"); do
    state="$(ha apps info "$APP" --no-progress --raw-json 2>/dev/null | jq -r '.data.state // empty' || true)"
    if [ "$state" = "started" ]; then
      return 0
    fi
    sleep 1
  done
  fail "App did not reach started state"
}

restart_app() {
  curl -fsS     -X POST     -H "Authorization: Bearer ${TOKEN}"     -H "Content-Type: application/json"     -d '{}'     "${SUPERVISOR}/addons/${APP}/restart" >/dev/null
  wait_app_started 90
  sleep 4
}

apply_options_file() {
  local file="$1"
  local options validation apply_payload

  options="$(cat "$file")"
  validation="$(
    curl -fsS       -X POST       -H "Authorization: Bearer ${TOKEN}"       -H "Content-Type: application/json"       -d "$options"       "${SUPERVISOR}/addons/${APP}/options/validate"
  )"

  echo "$validation" | jq .
  echo "$validation" | jq -e '
    .result == "ok" and
    ((.data.valid // true) == true)
  ' >/dev/null || fail "Supervisor rejected test options"

  apply_payload="$(jq -cn --argjson options "$options" '{options:$options}')"
  curl -fsS     -X POST     -H "Authorization: Bearer ${TOKEN}"     -H "Content-Type: application/json"     -d "$apply_payload"     "${SUPERVISOR}/addons/${APP}/options" | jq .

  restart_app
}

set_input_number() {
  local entity="$1"
  local value="$2"
  ha_service     "input_number"     "set_value"     "$(jq -cn --arg entity "$entity" --argjson value "$value"       '{entity_id:$entity,value:$value}')"
}

set_number() {
  local entity="$1"
  local value="$2"
  ha_service     "number"     "set_value"     "$(jq -cn --arg entity "$entity" --argjson value "$value"       '{entity_id:$entity,value:$value}')"
}

set_climate_preset() {
  local entity="$1"
  local preset="$2"
  ha_service \
    "climate" \
    "set_preset_mode" \
    "$(jq -cn --arg entity "$entity" --arg preset "$preset" \
      '{entity_id:$entity,preset_mode:$preset}')"
}

set_humidifier_power() {
  local entity="$1"
  local action="$2"
  ha_service     "humidifier"     "$action"     "$(jq -cn --arg entity "$entity" '{entity_id:$entity}')"
}

set_humidifier_target() {
  local entity="$1"
  local value="$2"
  ha_service     "humidifier"     "set_humidity"     "$(jq -cn --arg entity "$entity" --argjson value "$value"       '{entity_id:$entity,humidity:$value}')"
}

force_heat() {
  mqtt_pub "DigitalHouses/Global/dh_climate_app/season/set/target_temp_high" "35.0" false
  sleep 1
  mqtt_pub "DigitalHouses/Global/dh_climate_app/season/set/target_temp_low" "30.0" false
  wait_attr "$ROOM_CLIMATE" "season" "heat" 30
}

force_cool() {
  mqtt_pub "DigitalHouses/Global/dh_climate_app/season/set/target_temp_low" "10.0" false
  sleep 1
  mqtt_pub "DigitalHouses/Global/dh_climate_app/season/set/target_temp_high" "15.0" false
  wait_attr "$ROOM_CLIMATE" "season" "cool" 30
}

force_off() {
  mqtt_pub "DigitalHouses/Global/dh_climate_app/season/set/target_temp_low" "0.0" false
  sleep 1
  mqtt_pub "DigitalHouses/Global/dh_climate_app/season/set/target_temp_high" "50.0" false
  wait_attr "$ROOM_CLIMATE" "season" "off" 30
}

publish_fixture_discovery() {
  local payload

  payload='{"name":"DH Climate Accept Outdoor","unique_id":"dh_climate_accept_outdoor","default_entity_id":"sensor.dh_climate_accept_outdoor","device_class":"temperature","unit_of_measurement":"°C","state_topic":"dh_climate_accept/outdoor/state"}'
  mqtt_pub "${DISCOVERY}/sensor/dh_climate_accept_outdoor/config" "$payload" true

  payload='{"name":"DH Climate Accept Humidity","unique_id":"dh_climate_accept_humidity","default_entity_id":"sensor.dh_climate_accept_humidity","device_class":"humidity","unit_of_measurement":"%","state_topic":"dh_climate_accept/humidity/state"}'
  mqtt_pub "${DISCOVERY}/sensor/dh_climate_accept_humidity/config" "$payload" true

  payload='{"name":"DH Climate Accept Window","unique_id":"dh_climate_accept_window","default_entity_id":"binary_sensor.dh_climate_accept_window","device_class":"window","state_topic":"dh_climate_accept/window/state","payload_on":"ON","payload_off":"OFF"}'
  mqtt_pub "${DISCOVERY}/binary_sensor/dh_climate_accept_window/config" "$payload" true

  payload='{"name":"DH Climate Accept Reversible","unique_id":"dh_climate_accept_reversible","default_entity_id":"climate.dh_climate_accept_reversible","modes":["off","heat","cool"],"mode_command_topic":"dh_climate_accept/reversible/mode/set","temperature_command_topic":"dh_climate_accept/reversible/temp/set","min_temp":5,"max_temp":35,"temp_step":0.1,"initial":23,"optimistic":true}'
  mqtt_pub "${DISCOVERY}/climate/dh_climate_accept_reversible/config" "$payload" true

  payload='{"name":"DH Climate Accept Narrow","unique_id":"dh_climate_accept_narrow","default_entity_id":"climate.dh_climate_accept_narrow","modes":["off","heat"],"mode_command_topic":"dh_climate_accept/narrow/mode/set","temperature_command_topic":"dh_climate_accept/narrow/temp/set","min_temp":25,"max_temp":30,"temp_step":0.1,"initial":25,"optimistic":true}'
  mqtt_pub "${DISCOVERY}/climate/dh_climate_accept_narrow/config" "$payload" true

  payload='{"name":"DH Climate Accept Stubborn","unique_id":"dh_climate_accept_stubborn","default_entity_id":"climate.dh_climate_accept_stubborn","modes":["off","heat"],"mode_command_topic":"dh_climate_accept/stubborn/mode/set","mode_state_topic":"dh_climate_accept/stubborn/mode/state","temperature_command_topic":"dh_climate_accept/stubborn/temp/set","temperature_state_topic":"dh_climate_accept/stubborn/temp/state","min_temp":5,"max_temp":35,"temp_step":0.1,"optimistic":false}'
  mqtt_pub "${DISCOVERY}/climate/dh_climate_accept_stubborn/config" "$payload" true

  payload='{"name":"DH Climate Accept Slow","unique_id":"dh_climate_accept_slow","default_entity_id":"climate.dh_climate_accept_slow","modes":["off","heat"],"mode_command_topic":"dh_climate_accept/slow/mode/set","temperature_command_topic":"dh_climate_accept/slow/temp/set","min_temp":5,"max_temp":35,"temp_step":0.1,"initial":27,"optimistic":true}'
  mqtt_pub "${DISCOVERY}/climate/dh_climate_accept_slow/config" "$payload" true

  payload='{"name":"DH Climate Accept Humidifier","unique_id":"dh_climate_accept_humidifier","default_entity_id":"humidifier.dh_climate_accept_humidifier","command_topic":"dh_climate_accept/humidifier/power/set","state_topic":"dh_climate_accept/humidifier/power/state","target_humidity_command_topic":"dh_climate_accept/humidifier/target/set","target_humidity_state_topic":"dh_climate_accept/humidifier/target/state","min_humidity":30,"max_humidity":80,"optimistic":true}'
  mqtt_pub "${DISCOVERY}/humidifier/dh_climate_accept_humidifier/config" "$payload" true

  mqtt_pub "dh_climate_accept/outdoor/state" "5.0" true
  mqtt_pub "dh_climate_accept/humidity/state" "40.0" true
  mqtt_pub "dh_climate_accept/window/state" "OFF" true
  mqtt_pub "dh_climate_accept/stubborn/mode/state" "heat" true
  mqtt_pub "dh_climate_accept/stubborn/temp/state" "23.0" true
  mqtt_pub "dh_climate_accept/humidifier/power/state" "OFF" true
  mqtt_pub "dh_climate_accept/humidifier/target/state" "50" true

  FIXTURES_CREATED=1

  wait_entity "$OUTDOOR_SENSOR" 30
  wait_entity "$HUMIDITY_SENSOR" 30
  wait_entity "$WINDOW_SENSOR" 30
  wait_entity "$REVERSIBLE" 30
  wait_entity "$NARROW" 30
  wait_entity "$STUBBORN" 30
  wait_entity "$SLOW" 30
  wait_entity "$PHYSICAL_HUMIDIFIER" 30
}

relax_narrow_range() {
  local payload
  payload='{"name":"DH Climate Accept Narrow","unique_id":"dh_climate_accept_narrow","default_entity_id":"climate.dh_climate_accept_narrow","modes":["off","heat"],"mode_command_topic":"dh_climate_accept/narrow/mode/set","temperature_command_topic":"dh_climate_accept/narrow/temp/set","min_temp":5,"max_temp":30,"temp_step":0.1,"initial":25,"optimistic":true}'
  mqtt_pub "${DISCOVERY}/climate/dh_climate_accept_narrow/config" "$payload" true
}

restrict_humidifier_range() {
  local payload
  payload='{"name":"DH Climate Accept Humidifier","unique_id":"dh_climate_accept_humidifier","default_entity_id":"humidifier.dh_climate_accept_humidifier","command_topic":"dh_climate_accept/humidifier/power/set","state_topic":"dh_climate_accept/humidifier/power/state","target_humidity_command_topic":"dh_climate_accept/humidifier/target/set","target_humidity_state_topic":"dh_climate_accept/humidifier/target/state","min_humidity":60,"max_humidity":80,"optimistic":true}'
  mqtt_pub "${DISCOVERY}/humidifier/dh_climate_accept_humidifier/config" "$payload" true
  mqtt_pub "dh_climate_accept/humidifier/power/state" "ON" true
  mqtt_pub "dh_climate_accept/humidifier/target/state" "50" true
}

clear_fixture_topics() {
  local topic
  for topic in     "${DISCOVERY}/sensor/dh_climate_accept_outdoor/config"     "${DISCOVERY}/sensor/dh_climate_accept_humidity/config"     "${DISCOVERY}/binary_sensor/dh_climate_accept_window/config"     "${DISCOVERY}/climate/dh_climate_accept_reversible/config"     "${DISCOVERY}/climate/dh_climate_accept_narrow/config"     "${DISCOVERY}/climate/dh_climate_accept_stubborn/config"     "${DISCOVERY}/climate/dh_climate_accept_slow/config"     "${DISCOVERY}/humidifier/dh_climate_accept_humidifier/config"     "dh_climate_accept/outdoor/state"     "dh_climate_accept/humidity/state"     "dh_climate_accept/window/state"     "dh_climate_accept/stubborn/mode/state"     "dh_climate_accept/stubborn/temp/state"     "dh_climate_accept/humidifier/power/state"     "dh_climate_accept/humidifier/target/state"
  do
    mqtt_pub "$topic" "" true >/dev/null 2>&1 || true
  done
}

restore_backup() {
  if [ -z "$BACKUP_SLUG" ] || [ "$BACKUP_RESTORED" = "1" ]; then
    return 0
  fi

  say "RESTORE APP FROM BASELINE BACKUP"
  local result
  result="$(
    curl -fsS \
      -X POST \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json" \
      -d "$(jq -cn --arg app "$APP" '{addons:[$app],background:false}')" \
      "${SUPERVISOR}/backups/${BACKUP_SLUG}/restore/partial"
  )"
  echo "$result" | jq .
  echo "$result" | jq -e '.result == "ok"' >/dev/null || return 1

  wait_app_started 120
  sleep 5
  BACKUP_RESTORED=1
}

emergency_cleanup() {
  local rc="$?"
  trap - EXIT

  if [ "$rc" -ne 0 ]; then
    echo
    echo "========== ACCEPTANCE FAILED · EMERGENCY RESTORE =========="
  fi

  if [ -n "$BACKUP_SLUG" ] && [ "$BACKUP_RESTORED" != "1" ]; then
    restore_backup || true
  fi

  if [ -n "$BASE_ROOM_TEMP" ]; then
    set_input_number "$ROOM_TEMP_HELPER" "$BASE_ROOM_TEMP" >/dev/null 2>&1 || true
  fi

  if [ "$FIXTURES_CREATED" = "1" ]; then
    clear_fixture_topics
  fi

  if [ "$BACKUP_RESTORED" = "1" ] && [ -n "$BACKUP_SLUG" ]; then
    curl -fsS       -X DELETE       -H "Authorization: Bearer ${TOKEN}"       "${SUPERVISOR}/backups/${BACKUP_SLUG}" >/dev/null 2>&1 || true
  fi

  if [ "$rc" -ne 0 ]; then
    echo "Acceptance log: $LOG"
  fi
  exit "$rc"
}

trap emergency_cleanup EXIT

say "0. PREREQUISITES"

[ -n "$TOKEN" ] || fail "SUPERVISOR_TOKEN is empty"
command -v jq >/dev/null || fail "jq is required"
command -v curl >/dev/null || fail "curl is required"
command -v ha >/dev/null || fail "ha CLI is required"

services="$(core_get services)"
echo "$services" | jq -e '
  any(.[]; .domain == "mqtt" and any(.services | keys[]; . == "publish"))
' >/dev/null || fail "mqtt.publish action is unavailable"

for entity in   "$ROOM_CLIMATE"   "$SEASON_CLIMATE"   "$PROBLEM"   "$HEAT_DAY"   "$COOL_DAY"   "$ROOM_TEMP_HELPER"   "$ROOM_TEMP_SENSOR"
do
  wait_entity "$entity" 5
done

say "1. UPDATE TO 0.1.16"

ha store reload
sleep 3

APP_INFO="$(ha apps info "$APP" --no-progress --raw-json)"
echo "$APP_INFO" | jq '{
  state:.data.state,
  version:.data.version,
  version_latest:.data.version_latest,
  update_available:.data.update_available
}'

LATEST="$(echo "$APP_INFO" | jq -r '.data.version_latest')"
CURRENT="$(echo "$APP_INFO" | jq -r '.data.version')"

[ "$LATEST" = "$EXPECTED_VERSION" ] || fail "Store latest=$LATEST expected=$EXPECTED_VERSION"

if [ "$CURRENT" != "$EXPECTED_VERSION" ]; then
  ha apps update "$APP"
  wait_app_started 120
fi

APP_INFO="$(ha apps info "$APP" --no-progress --raw-json)"
CURRENT="$(echo "$APP_INFO" | jq -r '.data.version')"
[ "$CURRENT" = "$EXPECTED_VERSION" ] || fail "Installed version=$CURRENT expected=$EXPECTED_VERSION"

say "2. CAPTURE CLEAN BASELINE"

echo "$APP_INFO" | jq '.data.options' > "$BASE_OPTIONS_FILE"
jq -e 'type=="object" and (.rooms|type=="array")' "$BASE_OPTIONS_FILE" >/dev/null ||
  fail "Could not read current App options"

core_get states > "$BASE_STATE_FILE"

wait_numeric_state_present "$HEAT_DAY" 40
wait_numeric_state_present "$COOL_DAY" 40
wait_numeric_attr_present "$SEASON_CLIMATE" "target_temp_low" 40
wait_numeric_attr_present "$SEASON_CLIMATE" "target_temp_high" 40

BASE_ROOM_TEMP="$(state_value "$ROOM_TEMP_HELPER")"
BASE_HEAT_DAY="$(state_value "$HEAT_DAY")"
BASE_COOL_DAY="$(state_value "$COOL_DAY")"
BASE_SEASON_LOW="$(attr_value "$SEASON_CLIMATE" "target_temp_low")"
BASE_SEASON_HIGH="$(attr_value "$SEASON_CLIMATE" "target_temp_high")"

echo "room_temp=$BASE_ROOM_TEMP"
echo "heat_day=$BASE_HEAT_DAY"
echo "cool_day=$BASE_COOL_DAY"
echo "season_low=$BASE_SEASON_LOW"
echo "season_high=$BASE_SEASON_HIGH"
state_json "$PROBLEM" | jq '{state, count:.attributes.count, problems:.attributes.problems}'

say "3. CREATE CLIMATE-APP-ONLY BASELINE BACKUP"

BACKUP_JSON="$(
  curl -fsS \
    -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$(jq -cn --arg app "$APP" '{
      name:"DH Climate bundled acceptance baseline",
      addons:[$app],
      compressed:true,
      background:false
    }')" \
    "${SUPERVISOR}/backups/new/partial"
)"
echo "$BACKUP_JSON" | jq .
echo "$BACKUP_JSON" | jq -e '.result == "ok"' >/dev/null ||
  fail "Climate App partial backup creation failed"
BACKUP_SLUG="$(echo "$BACKUP_JSON" | jq -r '.data.slug // .slug // empty')"
[ -n "$BACKUP_SLUG" ] || fail "Backup slug is empty"
echo "baseline_backup=$BACKUP_SLUG"

say "4. CREATE SYNTHETIC HA FIXTURES"

publish_fixture_discovery

for entity in   "$OUTDOOR_SENSOR"   "$HUMIDITY_SENSOR"   "$WINDOW_SENSOR"   "$REVERSIBLE"   "$NARROW"   "$STUBBORN"   "$SLOW"   "$PHYSICAL_HUMIDIFIER"
do
  state_json "$entity" | jq '{
    entity_id,
    state,
    temperature:.attributes.temperature,
    min_temp:.attributes.min_temp,
    max_temp:.attributes.max_temp,
    humidity:.attributes.humidity,
    min_humidity:.attributes.min_humidity,
    max_humidity:.attributes.max_humidity,
    hvac_modes:.attributes.hvac_modes
  }'
done

say "5. APPLY ACCEPTANCE OPTIONS"

TEST_OPTIONS_FILE="${WORKDIR}/test_options.json"

jq '
  .outdoor_temperature_sources = "sensor.dh_climate_accept_outdoor" |
  .outdoor_humidity_sources = "sensor.dh_climate_accept_humidity" |
  .night_mode = "" |
  .we_at_home = "" |
  .ac_min_outdoor_temperature = -10 |
  .rooms |= map(
    if .id == "livingroom" then
      .temperature_sensors = "sensor.dh_climate_test_livingroom_temperature" |
      .humidity_sensors = "sensor.dh_climate_accept_humidity" |
      .window_sensors = "binary_sensor.dh_climate_accept_window" |
      .window_off_devices = "climate.dh_climate_accept_reversible" |
      .fast_heat = "climate.dh_climate_accept_narrow, climate.dh_climate_accept_stubborn, climate.dh_climate_accept_reversible" |
      .fast_cool = "climate.dh_climate_accept_reversible" |
      .slow_heat = "climate.dh_climate_accept_slow" |
      .slow_target = 27 |
      .humidity_mode = "humidifier" |
      .humidity_target = 50 |
      .humidity_actuator = "humidifier.dh_climate_accept_humidifier"
    else .
    end
  )
' "$BASE_OPTIONS_FILE" > "$TEST_OPTIONS_FILE"

jq '.rooms[] | select(.id=="livingroom")' "$TEST_OPTIONS_FILE"
apply_options_file "$TEST_OPTIONS_FILE"

wait_entity "$HUMIDITY_FACADE" 30

set_number "$HEAT_DAY" 23
wait_number "$HEAT_DAY" 23 20

mqtt_pub "dh_climate_accept/outdoor/state" "5.0" true
mqtt_pub "dh_climate_accept/humidity/state" "40.0" true
mqtt_pub "dh_climate_accept/window/state" "OFF" true
mqtt_pub "dh_climate_accept/stubborn/mode/state" "heat" true
mqtt_pub "dh_climate_accept/stubborn/temp/state" "23.0" true

say "5B. ROOM CLIMATE · NATIVE HVAC / ACTION / PRESET"

set_input_number "$ROOM_TEMP_HELPER" 20
force_heat
wait_state "$ROOM_CLIMATE" "heat" 30
wait_attr "$ROOM_CLIMATE" "hvac_action" "heating" 30
wait_attr "$ROOM_CLIMATE" "preset_mode" "day" 30
state_json "$ROOM_CLIMATE" | jq -e '
  (.attributes.hvac_modes == ["off","heat"]) and
  ((.attributes.preset_modes | index("day")) != null) and
  ((.attributes.preset_modes | index("night")) != null) and
  ((.attributes.preset_modes | index("away")) != null) and
  ((.attributes.preset_modes | index("none")) != null)
' >/dev/null || fail "room climate HEAT/preset capability contract mismatch"
echo "PASS room climate HEAT + heating + day preset"

set_climate_preset "$ROOM_CLIMATE" "night"
wait_attr "$ROOM_CLIMATE" "preset_mode" "night" 20
wait_numeric_attr "$ROOM_CLIMATE" "temperature" 20 20
echo "PASS native night preset exposes night target"

set_climate_preset "$ROOM_CLIMATE" "none"
wait_attr "$ROOM_CLIMATE" "preset_mode" "day" 20
wait_numeric_attr "$ROOM_CLIMATE" "temperature" 23 20
echo "PASS preset none returns to automatic effective profile"

set_input_number "$ROOM_TEMP_HELPER" 30
force_cool
wait_state "$ROOM_CLIMATE" "cool" 30
wait_attr "$ROOM_CLIMATE" "hvac_action" "cooling" 30
wait_attr "$ROOM_CLIMATE" "preset_mode" "day" 30
state_json "$ROOM_CLIMATE" | jq -e '
  .attributes.hvac_modes == ["off","cool"]
' >/dev/null || fail "room climate COOL capability contract mismatch"
echo "PASS room climate COOL + cooling"

force_off
wait_state "$ROOM_CLIMATE" "off" 30
wait_attr "$ROOM_CLIMATE" "hvac_action" "off" 30
state_json "$ROOM_CLIMATE" | jq -e '
  .attributes.hvac_modes == ["off"]
' >/dev/null || fail "room climate OFF capability contract mismatch"
echo "PASS room climate interseason OFF"

say "6. TARGET_OUT_OF_RANGE · LIVE"

set_input_number "$ROOM_TEMP_HELPER" 20
force_heat
wait_state "$ROOM_CLIMATE" "heat" 30
wait_attr "$ROOM_CLIMATE" "control_action" "heating" 30

wait_problem "device_target_out_of_range" "$NARROW" 30
echo "PASS target_out_of_range started"
state_json "$PROBLEM" | jq '{state,problems:.attributes.problems}'
state_json "$EVENT" | jq '{
  state,
  event_type:.attributes.event_type,
  problem_id:.attributes.problem_id,
  room_id:.attributes.room_id,
  entity_id:.attributes.entity_id,
  details:.attributes.details
}'

ha apps logs "$APP" | tail -n 300 |   grep -F "$NARROW" | tail -n 30 || true

relax_narrow_range
wait_no_problem "device_target_out_of_range" "$NARROW" 30
wait_state "$NARROW" "heat" 30
wait_numeric_attr "$NARROW" "temperature" 23 30
echo "PASS target_out_of_range recovered"

say "7. NO_CONFIRMATION -> RETRY -> COOLDOWN -> RECOVERY"

mqtt_pub "dh_climate_accept/stubborn/mode/state" "off" true
mqtt_pub "dh_climate_accept/stubborn/temp/state" "23.0" true
restart_app

wait_problem "device_no_confirmation" "$STUBBORN" 50
echo "PASS no_confirmation reached cooldown"
state_json "$PROBLEM" | jq '{state,problems:.attributes.problems}'

STUBBORN_LOG="$(ha apps logs "$APP" | tail -n 500 | grep -F "$STUBBORN" || true)"
echo "$STUBBORN_LOG" | tail -n 80
echo "$STUBBORN_LOG" | grep -q "RETRY 2/3" || fail "missing RETRY 2/3"
echo "$STUBBORN_LOG" | grep -q "RETRY 3/3" || fail "missing RETRY 3/3"
echo "$STUBBORN_LOG" | grep -q "COOLDOWN 300s" || fail "missing COOLDOWN 300s"

mqtt_pub "dh_climate_accept/stubborn/mode/state" "heat" true
mqtt_pub "dh_climate_accept/stubborn/temp/state" "23.0" true
wait_no_problem "device_no_confirmation" "$STUBBORN" 20
sleep 6

STUBBORN_LOG="$(ha apps logs "$APP" | tail -n 500 | grep -F "$STUBBORN" || true)"
echo "$STUBBORN_LOG" | grep -q "VERIFIED_HA" ||
  fail "stubborn actuator did not reach VERIFIED_HA"
echo "PASS no_confirmation recovered"

say "8. SLOW FLOOR · SEASON-DRIVEN"

set_input_number "$ROOM_TEMP_HELPER" 30
wait_number "$ROOM_TEMP_HELPER" 30 10
wait_attr "$ROOM_CLIMATE" "control_action" "idle" 30
wait_state "$SLOW" "heat" 30
wait_numeric_attr "$SLOW" "temperature" 27 30

echo "PASS SLOW remains heat at target 27 while room demand is idle"

force_off
wait_state "$SLOW" "off" 30
echo "PASS SLOW turns off outside HEAT season"

say "9. WINDOW CONTEXT / window_off_devices"

force_heat
set_input_number "$ROOM_TEMP_HELPER" 20
wait_attr "$ROOM_CLIMATE" "control_action" "heating" 30

mqtt_pub "dh_climate_accept/window/state" "ON" true
wait_attr "$ROOM_CLIMATE" "window_state" "open" 30
wait_attr "$ROOM_CLIMATE" "control_action" "heating" 30
wait_state "$REVERSIBLE" "off" 30
wait_state "$NARROW" "heat" 30
wait_state "$STUBBORN" "heat" 30

echo "PASS window is context-only and inhibits only selected reversible actuator"

mqtt_pub "dh_climate_accept/window/state" "OFF" true
wait_attr "$ROOM_CLIMATE" "window_state" "closed" 30
wait_state "$REVERSIBLE" "heat" 30
echo "PASS window close restores selected actuator"

say "10. COLD-WEATHER REVERSIBLE CLIMATE PROTECTION"

mqtt_pub "dh_climate_accept/outdoor/state" "-15.0" true
wait_number "$OUTDOOR_SENSOR" -15 15
wait_state "$REVERSIBLE" "off" 30
wait_state "$NARROW" "heat" 30
wait_state "$STUBBORN" "heat" 30
wait_state "$SLOW" "heat" 30
echo "PASS reversible heat is blocked below -10 while other heat sources continue"

mqtt_pub "dh_climate_accept/outdoor/state" "5.0" true
wait_number "$OUTDOOR_SENSOR" 5 15
wait_state "$REVERSIBLE" "heat" 30
echo "PASS reversible heat restores above threshold"

mqtt_pub "dh_climate_accept/outdoor/state" "-15.0" true
set_input_number "$ROOM_TEMP_HELPER" 30
force_cool
wait_attr "$ROOM_CLIMATE" "control_action" "cooling" 30
wait_state "$REVERSIBLE" "cool" 30
wait_state "$SLOW" "off" 30
echo "PASS cooling is not blocked by heating-only cold protection"

say "11. HUMIDITY ACTIVE PATH + SAFE SHUTDOWN"

force_off
mqtt_pub "dh_climate_accept/humidity/state" "40.0" true
wait_number "$HUMIDITY_SENSOR" 40 15

wait_state "$HUMIDITY_FACADE" "on" 30
wait_state "$PHYSICAL_HUMIDIFIER" "on" 30
wait_attr "$PHYSICAL_HUMIDIFIER" "humidity" "50" 30 ||   wait_attr "$PHYSICAL_HUMIDIFIER" "humidity" "50.0" 10
echo "PASS humidity active path"

restrict_humidifier_range
wait_problem "device_target_out_of_range" "$PHYSICAL_HUMIDIFIER" 30
echo "PASS humidifier target range problem reproduced while active"

# Keep the physical device definitely ON with a valid local target. The App's
# persisted 50% target is deliberately outside the new 60..80% device range.
# Turning the DigitalHouses humidity controller OFF must still send power-off;
# target validation must not be allowed to block that safety action.
set_humidifier_target "$PHYSICAL_HUMIDIFIER" 60
set_humidifier_power "$PHYSICAL_HUMIDIFIER" "turn_on"
wait_state "$PHYSICAL_HUMIDIFIER" "on" 15

set_humidifier_power "$HUMIDITY_FACADE" "turn_off"
wait_state "$HUMIDITY_FACADE" "off" 30
wait_state "$PHYSICAL_HUMIDIFIER" "off" 30
wait_no_problem "device_target_out_of_range" "$PHYSICAL_HUMIDIFIER" 30
echo "PASS out-of-range target does not block humidifier turn_off"

say "12. RESTORE REAL APP BACKUP"

restore_backup

RESTORED_INFO="$(ha apps info "$APP" --no-progress --raw-json)"
echo "$RESTORED_INFO" | jq '{
  state:.data.state,
  version:.data.version,
  options:.data.options
}'

RESTORED_VERSION="$(echo "$RESTORED_INFO" | jq -r '.data.version')"
[ "$RESTORED_VERSION" = "$EXPECTED_VERSION" ] ||
  fail "version changed after restore: $RESTORED_VERSION"

echo "$RESTORED_INFO" | jq '.data.options' > "${WORKDIR}/restored_options.json"
jq -S . "$BASE_OPTIONS_FILE" > "${WORKDIR}/baseline_options.sorted.json"
jq -S . "${WORKDIR}/restored_options.json" > "${WORKDIR}/restored_options.sorted.json"
cmp -s   "${WORKDIR}/baseline_options.sorted.json"   "${WORKDIR}/restored_options.sorted.json" ||
  fail "App options were not restored exactly"

wait_number "$HEAT_DAY" "$BASE_HEAT_DAY" 30
wait_number "$COOL_DAY" "$BASE_COOL_DAY" 30

CURRENT_LOW="$(attr_value "$SEASON_CLIMATE" "target_temp_low")"
CURRENT_HIGH="$(attr_value "$SEASON_CLIMATE" "target_temp_high")"

awk -v a="$CURRENT_LOW" -v b="$BASE_SEASON_LOW"   'BEGIN{exit !((a-b<0?b-a:a-b)<0.051)}' ||
  fail "season low not restored: $CURRENT_LOW vs $BASE_SEASON_LOW"
awk -v a="$CURRENT_HIGH" -v b="$BASE_SEASON_HIGH"   'BEGIN{exit !((a-b<0?b-a:a-b)<0.051)}' ||
  fail "season high not restored: $CURRENT_HIGH vs $BASE_SEASON_HIGH"

echo "PASS Climate-App-only Supervisor backup -> restore preserved options and /data"

say "13. FINAL CLEANUP + BASELINE"

set_input_number "$ROOM_TEMP_HELPER" "$BASE_ROOM_TEMP"
wait_number "$ROOM_TEMP_HELPER" "$BASE_ROOM_TEMP" 15

clear_fixture_topics
sleep 5

wait_state "$PROBLEM" "off" 30

FINAL_INFO="$(ha apps info "$APP" --no-progress --raw-json)"
FINAL_VERSION="$(echo "$FINAL_INFO" | jq -r '.data.version')"
FINAL_STATE="$(echo "$FINAL_INFO" | jq -r '.data.state')"

[ "$FINAL_VERSION" = "$EXPECTED_VERSION" ] || fail "final version=$FINAL_VERSION"
[ "$FINAL_STATE" = "started" ] || fail "final app state=$FINAL_STATE"

state_json "$ROOM_CLIMATE" | jq '{
  state,
  current_temperature:.attributes.current_temperature,
  temperature:.attributes.temperature,
  season:.attributes.season,
  control_action:.attributes.control_action,
  window_state:.attributes.window_state
}'
state_json "$PROBLEM" | jq '{
  state,
  count:.attributes.count,
  problems:.attributes.problems
}'

curl -fsS   -X DELETE   -H "Authorization: Bearer ${TOKEN}"   "${SUPERVISOR}/backups/${BACKUP_SLUG}" >/dev/null
BACKUP_SLUG=""

echo
echo "============================================================"
echo "DH CLIMATE 0.1.16 · BUNDLED LIVE ACCEPTANCE = PASS"
echo "============================================================"
echo "PASS room climate native heat/cool + action + presets"
echo "PASS device_target_out_of_range"
echo "PASS no_confirmation -> RETRY -> COOLDOWN -> recovery"
echo "PASS SLOW floor execution"
echo "PASS window context / window_off_devices"
echo "PASS cold-weather reversible climate protection"
echo "PASS humidity active + safe shutdown"
echo "PASS Climate-App-only Supervisor backup -> restore"
echo "PASS baseline restored"
echo
echo "Acceptance log: $LOG"
