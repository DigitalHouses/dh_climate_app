#!/usr/bin/env bash
# DH Climate System Tree preflight: read-only, safe before App release.
set -u
APP="${1:-8d59ce70_dh_climate_app}"

echo "=== DH CLIMATE SYSTEM TREE / HAOS PREFLIGHT ==="
echo "APP=$APP"
if ! command -v ha >/dev/null 2>&1; then
  echo "HA_CLI=FAIL (ha command not found)"
  exit 2
fi

INFO="$(ha apps info "$APP" 2>&1)"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "APP_LOOKUP=FAIL (ha apps info returned $RC)"
  printf '%s\n' "$INFO" | tail -n 10
  exit 1
fi
echo "APP_LOOKUP=PASS"
printf '%s\n' "$INFO" | grep -E '^state:|^version:|^version_latest:|^update_available:' || true

echo
echo "=== HOME ASSISTANT ==="
ha core info 2>/dev/null | grep -E '^version:|^machine:|^boot:' || true

echo
echo "=== LOCAL FRONTEND RESOURCE ==="
if [ -d /config/www ]; then
  echo "WWW_DIRECTORY=PASS"
else
  echo "WWW_DIRECTORY=NOT_READY (not found; Home Assistant restart required after first creation)"
fi
if [ -s /config/www/dh-climate-tree-card.js ]; then
  echo "TREE_CARD_FILE=PRESENT"
  ls -lh /config/www/dh-climate-tree-card.js
else
  echo "TREE_CARD_FILE=NOT_INSTALLED"
fi

echo
echo "=== RECORDER POLICY ==="
if [ -f /config/configuration.yaml ]; then
  echo "HA_CONFIG=AVAILABLE"
  echo "RECORDER_TOPOLOGY_EXCLUSION=NOT_VERIFIED (check include/exclude policy for sensor.dh_climate_app_topology)"
else
  echo "HA_CONFIG=NOT_ACCESSIBLE"
fi

echo
echo "PREFLIGHT_COMPLETE=YES"
echo "LIVE_TREE_ACCEPTANCE=NOT_RUN"
echo "No service calls, updates, restarts, MQTT writes or file modifications were made."
