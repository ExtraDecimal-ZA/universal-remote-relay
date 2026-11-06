ARG BUILD_FROM=ghcr.io/home-assistant/base:3.24-2026.08.0
FROM ${BUILD_FROM}

ARG BUILD_ARCH=aarch64
ARG BUILD_VERSION=0.1.3
LABEL io.hass.arch="${BUILD_ARCH}" io.hass.type="app" io.hass.version="${BUILD_VERSION}"

COPY run.sh /run.sh
RUN chmod 0755 /run.sh
CMD ["/run.sh"]
