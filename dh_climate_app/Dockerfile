ARG TARGETARCH
FROM ghcr.io/home-assistant/base:latest AS base

ARG BUILD_VERSION="0.1.0"

ENV APP_VERSION="${BUILD_VERSION}" \
    PYTHONUNBUFFERED="1" \
    PYTHONPATH="/app"

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app"

RUN apk add --no-cache \
        py3-paho-mqtt \
        py3-websockets \
        python3 \
        tzdata

COPY src/dh_climate_app /app/dh_climate_app
COPY rootfs/run.sh /run.sh

RUN chmod a+x /run.sh \
    && python3 -m compileall -q /app/dh_climate_app

FROM base AS image-amd64
LABEL io.hass.arch="amd64"

FROM base AS image-arm64
LABEL io.hass.arch="aarch64"

FROM image-${TARGETARCH} AS final

CMD ["/run.sh"]
