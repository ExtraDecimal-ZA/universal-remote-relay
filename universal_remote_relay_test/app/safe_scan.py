"""Opt-in one-shot discovery with stable device matching."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from discovery import APPLE_TV, DiscoveredDevice, discover_devices, normalize_platform

LOG = logging.getLogger("universal_remote_relay")
OPTIONS = Path("/data/options.json")


@dataclass(frozen=True, slots=True)
class Settings:
    enable_single_scan: bool = False
    log_level: str = "info"
    target_platform: str = APPLE_TV
    target_name: str = ""
    target_identifier: str = ""
    target_address: str = ""


def load_options(path: Path = OPTIONS) -> Settings:
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(raw, dict):
        raise TypeError("Options must be an object")
    enabled = raw.get("enable_single_scan", False)
    if type(enabled) is not bool:
        raise TypeError("enable_single_scan must be a boolean")
    level = raw.get("log_level", "info")
    if level not in ("debug", "info", "warning", "error"):
        raise ValueError("Unsupported log_level")
    platform = normalize_platform(raw.get("target_platform", APPLE_TV))
    strings: dict[str, str] = {}
    for key in ("target_name", "target_identifier", "target_address"):
        value = raw.get(key, "")
        if not isinstance(value, str):
            raise TypeError(f"{key} must be a string")
        strings[key] = value.strip()
    return Settings(
        enable_single_scan=enabled,
        log_level=level,
        target_platform=platform,
        target_name=strings["target_name"],
        target_identifier=strings["target_identifier"],
        target_address=strings["target_address"],
    )


def matches_target(device: DiscoveredDevice, settings: Settings) -> bool:
    if device.platform != settings.target_platform:
        return False
    if settings.target_identifier:
        return settings.target_identifier in (
            device.identifier,
            *device.all_identifiers,
        )
    if settings.target_name:
        return device.name == settings.target_name
    if settings.target_address:
        return device.address == settings.target_address
    return True


async def scan_once(settings: Settings, discover_func=discover_devices) -> bool:
    if settings.target_identifier and settings.target_name:
        LOG.info("Stable identifier configured; target_name is informational only")
    LOG.info(
        "Starting one %s discovery scan; identifier_filter=%s",
        settings.target_platform,
        "set" if settings.target_identifier else "unset",
    )
    try:
        devices = await discover_func(settings.target_platform, timeout=10)
    except TimeoutError:
        LOG.error("Device discovery timed out")
        LOG.info("Discovery ended; no further scans scheduled")
        return False
    except Exception:
        LOG.exception("Device discovery failed")
        LOG.info("Discovery ended; no further scans scheduled")
        return False

    matches = [device for device in devices if matches_target(device, settings)]
    LOG.info(
        "Discovery completed: %d device(s), %d match(es)", len(devices), len(matches)
    )
    if not matches:
        LOG.warning("No device matched the saved target")
    for device in matches:
        LOG.info(
            "%s: name=%r address=%s identifier=%r all_identifiers=%s",
            "Apple TV" if device.platform == APPLE_TV else "Android TV",
            device.name,
            device.address,
            device.identifier,
            list(device.all_identifiers),
        )
    LOG.info("Discovery ended; no further scans scheduled")
    return bool(matches)
