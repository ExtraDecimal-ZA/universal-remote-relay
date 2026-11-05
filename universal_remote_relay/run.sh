#!/usr/bin/with-contenv bashio
set -eu

bashio::log.info "Universal Remote Relay v0.1.3: safe diagnostic mode"
bashio::log.info "No Apple TV discovery, remote listener, or commands are enabled."
bashio::log.info "No additional Python packages are installed in this build."
exec sleep infinity
