#!/usr/bin/with-contenv bashio
set -eu
bashio::log.info "Universal Remote Relay v0.3.0 starting"
exec python3 -u /app/service.py
