ARG BUILD_FROM=ghcr.io/home-assistant/base-python:3.14-alpine3.24-2026.08.0
FROM ${BUILD_FROM}
ARG BUILD_ARCH=aarch64
ARG BUILD_VERSION=0.4.3
LABEL io.hass.arch="${BUILD_ARCH}" \
      io.hass.type="app" \
      io.hass.version="${BUILD_VERSION}" \
      org.opencontainers.image.title="Universal Remote Relay Experimental" \
      org.opencontainers.image.description="Persistent phone remote relay with private Apple TV pairing" \
      org.opencontainers.image.source="https://github.com/ExtraDecimal-ZA/universal-remote-relay"
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --only-binary=:all: -r /tmp/requirements.txt
COPY app /app
COPY run.sh /run.sh
RUN chmod 0755 /run.sh
CMD ["/run.sh"]
