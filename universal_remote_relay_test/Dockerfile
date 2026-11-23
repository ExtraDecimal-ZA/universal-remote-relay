ARG BUILD_FROM=ghcr.io/home-assistant/base-python:3.14-alpine3.24-2026.08.0
FROM ${BUILD_FROM} AS protobuf-builder
# PyPI has no native ARM64 musl wheel for this version. Build the C parser in
# CI rather than shipping compilers or silently using the Python fallback.
RUN apk add --no-cache build-base \
    && CFLAGS="-O2 -g0" pip3 wheel --no-cache-dir --no-deps \
        --no-binary=protobuf protobuf==7.36.2 --wheel-dir=/wheels

FROM ${BUILD_FROM}
ARG BUILD_ARCH=aarch64
ARG BUILD_VERSION=0.4.17
LABEL io.hass.arch="${BUILD_ARCH}" \
      io.hass.type="app" \
      io.hass.version="${BUILD_VERSION}" \
      org.opencontainers.image.title="Universal Remote Relay" \
      org.opencontainers.image.description="Persistent phone remote relay with private Apple TV pairing" \
      org.opencontainers.image.source="https://github.com/ExtraDecimal-ZA/universal-remote-relay"
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=bind,from=protobuf-builder,source=/wheels,target=/wheels \
    pip3 install --no-cache-dir --only-binary=:all: --find-links=/wheels -r /tmp/requirements.txt \
    && python3 -c "from google.protobuf.internal import api_implementation; assert api_implementation.Type() == 'upb', 'Native protobuf parser is required'"
COPY app /app
COPY run.sh /run.sh
RUN chmod 0755 /run.sh
CMD ["/run.sh"]
