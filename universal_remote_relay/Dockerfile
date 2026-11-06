ARG BUILD_FROM
FROM ${BUILD_FROM}
ARG BUILD_ARCH=aarch64
ARG BUILD_VERSION=0.1.4
LABEL io.hass.arch="${BUILD_ARCH}" io.hass.type="addon" io.hass.version="${BUILD_VERSION}"
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --only-binary=:all: -r /tmp/requirements.txt
COPY app /app
COPY run.sh /run.sh
RUN chmod 0755 /run.sh
CMD ["/run.sh"]
