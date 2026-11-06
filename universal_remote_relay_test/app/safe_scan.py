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
    target_name = raw.get("target_name", "")
    if not isinstance(target_name, str):
        raise ValueError("target_name must be a string")
    target_name = target_name.strip()
    target_identifier = raw.get("target_identifier", "")
    if not isinstance(target_identifier, str):
        raise ValueError("target_identifier must be a string")
    target_identifier = target_identifier.strip()
    return enabled, level, target_name, target_identifier


def matches_target(device, target_name):
    """Return whether a discovered device matches an optional exact name."""
    return not target_name or device.name == target_name


def identifiers_for(device):
    """Return sorted non-empty discovery identifiers without credentials."""
    return sorted(str(identifier) for identifier in device.all_identifiers if identifier)


async def scan_once(target_name="", target_identifier="", scan_func=None):
    if scan_func is None:
        import pyatv

        scan_func = pyatv.scan

    if target_identifier and target_name:
        LOG.info("Stable identifier configured; target_name is ignored")
    LOG.info(
        "Starting one Apple TV discovery scan; target_name=%r identifier_filter=%s",
        target_name or None,
        "set" if target_identifier else "unset",
    )
    try:
        scan_options = {"timeout": 10}
        if target_identifier:
            scan_options["identifier"] = target_identifier
        devices = await asyncio.wait_for(
            scan_func(asyncio.get_running_loop(), **scan_options),
            timeout=20,
        )
    except asyncio.TimeoutError:
        LOG.error("Apple TV discovery timed out")
        LOG.info("Discovery ended; no further scans scheduled")
        return False
    except Exception:
        LOG.exception("Apple TV discovery failed")
        LOG.info("Discovery ended; no further scans scheduled")
        return False

    LOG.info("Discovery completed: %d device(s)", len(devices))
    matches = devices if target_identifier else [
        device for device in devices if matches_target(device, target_name)
    ]
    if target_identifier and not matches:
        LOG.warning("No device matched the configured stable identifier")
    elif target_name and not matches:
        LOG.warning("No device matched target name %r", target_name)
    for device in matches:
        LOG.info(
            "Apple TV: name=%r address=%s identifier=%r all_identifiers=%s",
            device.name,
            device.address,
            device.identifier,
            identifiers_for(device),
        )
    LOG.info("Discovery ended; no further scans scheduled")
    return bool(matches)


def main():
    enabled, level, target_name, target_identifier = load_options()
    logging.basicConfig(level=getattr(logging, level.upper()), format="%(levelname)s %(message)s")
    LOG.info("Universal Remote Relay v0.1.6; single scan enabled=%s", enabled)
    if enabled:
        if not asyncio.run(scan_once(target_name, target_identifier)):
            LOG.error("The requested one-shot discovery did not find its target")
            raise SystemExit(1)
    else:
        LOG.info("Safe idle mode; discovery disabled")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
