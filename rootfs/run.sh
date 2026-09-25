#!/usr/bin/with-contenv bashio

set -Eeuo pipefail

bashio::log.info "Starting DigitalHouses Climate App ${APP_VERSION:-unknown}"

export TZ="$(bashio::supervisor.timezone)"
export MQTT_HOST="$(bashio::services mqtt host)"
export MQTT_PORT="$(bashio::services mqtt port)"
export MQTT_USER="$(bashio::services mqtt username)"
export MQTT_PASSWORD="$(bashio::services mqtt password)"

if [[ -z "${SUPERVISOR_TOKEN:-}" ]]; then
    bashio::log.fatal "SUPERVISOR_TOKEN is missing."
    exit 1
fi

if [[ -z "${MQTT_HOST}" || -z "${MQTT_PORT}" ]]; then
    bashio::log.fatal "MQTT service information is incomplete."
    exit 1
fi

exec python3 -m dh_climate_app
