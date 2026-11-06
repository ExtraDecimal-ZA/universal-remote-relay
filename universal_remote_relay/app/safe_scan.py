"""Opt-in, single Apple TV discovery; no pairing or remote commands."""
import asyncio
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
LOG = logging.getLogger("relay")
OPTIONS = Path("/data/options.json")

async def scan():
    import pyatv
    LOG.info("Starting one Apple TV scan (10 second timeout)")
    try:
        devices = await asyncio.wait_for(
            pyatv.scan(asyncio.get_running_loop(), timeout=10), timeout=20
        )
        LOG.info("Discovery complete; devices found: %d", len(devices))
        for device in devices:
            LOG.info("Apple TV discovered: name=%r address=%s", device.name, device.address)
    except Exception:
        LOG.exception("Single discovery attempt failed")
    LOG.info("Scan finished; remaining idle without further network activity")

def main():
    options = json.loads(OPTIONS.read_text()) if OPTIONS.exists() else {}
    if not isinstance(options, dict):
        raise ValueError("Invalid add-on options")
    enabled = options.get("enable_single_scan", False)
    if not isinstance(enabled, bool):
        raise ValueError("enable_single_scan must be boolean")
    LOG.info("Universal Remote Relay v0.1.4; single scan enabled=%s", enabled)
    if enabled:
        asyncio.run(scan())
    else:
        LOG.info("Safe idle mode: discovery disabled")
    import time
    while True:
        time.sleep(3600)

if __name__ == "__main__":
    main()
