#!/usr/bin/with-contenv bashio
set -eu
bashio::log.info "Universal Remote Relay v0.1.7 starting"
exec python3 -u /app/safe_scan.py
