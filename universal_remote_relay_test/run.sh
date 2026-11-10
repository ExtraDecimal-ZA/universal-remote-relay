#!/usr/bin/with-contenv bashio
set -eu
bashio::log.info "Universal Remote Relay v0.4.5 starting"
exec python3 -u /app/service.py
