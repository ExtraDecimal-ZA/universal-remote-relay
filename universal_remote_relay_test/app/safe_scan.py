"""Opt-in one-shot Apple TV discovery. No pairing, listener, or remote commands."""
import asyncio
import json
import logging
import time
from pathlib import Path

LOG = logging.getLogger("universal_remote_relay")
OPTIONS = Path("/data/options.json")


def load_options(path=OPTIONS):
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(raw, dict):
        raise ValueError("Options must be an object")
    enabled = raw.get("enable_single_scan", False)
    if type(enabled) is not bool:
        raise ValueError("enable_single_scan must be a boolean")
    level = raw.get("log_level", "info")
    if level not in ("debug", "info", "warning", "error"):
        raise ValueError("Unsupported log_level")
    return enabled, level


async def scan_once():
    import pyatv

    LOG.info("Starting one Apple TV discovery scan")
    try:
        devices = await asyncio.wait_for(
            pyatv.scan(asyncio.get_running_loop(), timeout=10),
            timeout=20,
        )
    except asyncio.TimeoutError:
        LOG.warning("Apple TV discovery timed out")
    except Exception:
        LOG.exception("Apple TV discovery failed")
    else:
        LOG.info("Discovery completed: %d device(s)", len(devices))
        for device in devices:
            LOG.info("Apple TV: name=%r address=%s", device.name, device.address)
    LOG.info("Discovery ended; no further scans scheduled")


def main():
    enabled, level = load_options()
    logging.basicConfig(level=getattr(logging, level.upper()), format="%(levelname)s %(message)s")
    LOG.info("Universal Remote Relay v0.1.4; single scan enabled=%s", enabled)
    if enabled:
        asyncio.run(scan_once())
    else:
        LOG.info("Safe idle mode; discovery disabled")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
