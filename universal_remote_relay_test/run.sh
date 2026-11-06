#!/usr/bin/with-contenv bashio
set -eu
bashio::log.info "Universal Remote Relay v0.2.0 starting"
INGRESS_PORT="$(bashio::app.ingress_port)"
export INGRESS_PORT
exec python3 -u /app/service.py
