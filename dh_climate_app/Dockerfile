FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION="0.1.13"
ARG BUILD_ARCH="amd64"

ENV APP_VERSION="${BUILD_VERSION}" \
    PYTHONUNBUFFERED="1" \
    PYTHONPATH="/app"

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache \
        py3-paho-mqtt \
        py3-websockets \
        python3 \
        tzdata

COPY src/dh_climate_app /app/dh_climate_app
COPY rootfs/run.sh /run.sh

RUN chmod a+x /run.sh \
    && python3 -m compileall -q /app/dh_climate_app

CMD ["/run.sh"]
