FROM ghcr.io/home-assistant/base:latest
ARG BUILD_VERSION="0.1.32-rc1"
ARG BUILD_ARCH="amd64"
LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}"
CMD ["sh", "-c", "echo 'DH Climate schema probe: no Home Assistant API, no MQTT, no physical outputs'; exec sleep infinity"]
