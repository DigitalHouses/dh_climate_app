#!/usr/bin/env bash
# DH Climate 0.1.32-rc1: install ONLY the safe local Supervisor UI probe.
# The running DigitalHouses Climate App and its SQLite are never touched.
set -Eeuo pipefail

SOURCE_COMMIT='ae6c392c39797545e1dd8e6d5b244f85ad745970'
REPO='DigitalHouses/dh_climate_app'
NAME='dh_climate_schema_probe'

command -v curl >/dev/null || { echo 'ERROR: curl required'; exit 1; }
command -v ha >/dev/null || { echo 'ERROR: Home Assistant CLI required'; exit 1; }

if [[ -n "${LOCAL_APPS_DIR:-}" ]]; then
  ROOT="$LOCAL_APPS_DIR"
elif [[ -d /addons ]]; then
  ROOT=/addons
elif [[ -d /config/addons ]]; then
  ROOT=/config/addons
else
  echo 'ERROR: local Apps directory not found. Set LOCAL_APPS_DIR explicitly.'
  exit 1
fi

[[ -d "$ROOT" ]] || { echo "ERROR: missing local Apps directory $ROOT"; exit 1; }
DEST="${ROOT%/}/$NAME"
[[ ! -e "$DEST" ]] || { echo "ERROR: $DEST exists; refusing overwrite"; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
for file in config.yaml Dockerfile README.md; do
  curl -fsSL --retry 2 \
    "https://raw.githubusercontent.com/$REPO/$SOURCE_COMMIT/$NAME/$file" \
    -o "$TMP/$file"
done

grep -q '^slug: dh_climate_schema_probe$' "$TMP/config.yaml" || exit 1
grep -q '^boot: manual$' "$TMP/config.yaml" || exit 1
if grep -Eq '^(homeassistant_api|hassio_api|services|devices|host_network|full_access):' "$TMP/config.yaml"; then
  echo 'ERROR: unexpected runtime privileges in test manifest'
  exit 1
fi

mkdir "$DEST"
cp "$TMP/config.yaml" "$TMP/Dockerfile" "$TMP/README.md" "$DEST/"
echo "Created $DEST"
ha store reload
printf '\nSAFE_LOCAL_SCHEMA_PROBE=INSTALLED_NOT_STARTED\n'
echo 'Find DigitalHouses Climate UI Schema Probe in Settings -> Apps -> Store.'
echo 'Its settings editor can be tested without starting the App.'
