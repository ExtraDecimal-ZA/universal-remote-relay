#!/usr/bin/with-contenv bashio
set -eu
bashio::log.info "Universal Remote Relay v0.2.1 starting"
exec python3 -u /app/service.py
