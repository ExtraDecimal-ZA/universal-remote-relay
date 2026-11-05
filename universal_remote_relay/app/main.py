"""Observation-only service for the Universal Remote Relay v0.1 add-on."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

OPTIONS_PATH = Path(os.environ.get("OPTIONS_PATH", "/data/options.json"))
LOGGER = logging.getLogger("universal_remote_relay")
VALID_LOG_LEVELS = {"debug", "info", "warning", "error"}


@dataclass(frozen=True)
class Settings:
    """Validated add-on options."""

    log_level: str = "info"
    apple_tv_identifier: str = ""
    scan_interval: int = 300

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "Settings":
        log_level = str(raw.get("log_level", "info")).lower()
        if log_level not in VALID_LOG_LEVELS:
            raise ValueError(f"Invalid log_level: {log_level!r}")

        scan_interval = int(raw.get("scan_interval", 300))
        if not 30 <= scan_interval <= 3600:
            raise ValueError("scan_interval must be between 30 and 3600 seconds")

        return cls(
            log_level=log_level,
            apple_tv_identifier=str(raw.get("apple_tv_identifier", "")).strip(),
            scan_interval=scan_interval,
        )


def load_settings(path: Path = OPTIONS_PATH) -> Settings:
    """Read options managed by Home Assistant Supervisor."""

    if not path.exists():
        LOGGER.warning("Options file not found at %s; using safe defaults", path)
        return Settings()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Options file must contain a JSON object")
    return Settings.from_mapping(raw)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    LOGGER.setLevel(getattr(logging, level.upper()))


def identifiers_for(device: Any) -> list[str]:
    """Return public device identifiers without logging credentials."""

    return sorted(str(identifier) for identifier in device.all_identifiers)


async def scan_once(settings: Settings) -> None:
    """Discover Apple TVs. This does not connect, pair, or send commands."""

    import pyatv

    kwargs: dict[str, Any] = {"timeout": 10}
    if settings.apple_tv_identifier:
        kwargs["identifier"] = settings.apple_tv_identifier

    devices = await pyatv.scan(asyncio.get_running_loop(), **kwargs)
    if not devices:
        LOGGER.warning("No matching Apple TV discovered on the local network")
        return

    for device in devices:
        LOGGER.info(
            "Discovered Apple TV name=%r address=%s identifiers=%s deep_sleep=%s",
            device.name,
            device.address,
            identifiers_for(device),
            device.deep_sleep,
        )


async def run(settings: Settings) -> None:
    LOGGER.info(
        "Starting Universal Remote Relay version=0.1.0 architecture=%s mode=observation-only",
        platform.machine(),
    )
    LOGGER.warning(
        "Google TV receiver discovery/pairing is not implemented or verified; no listener is running"
    )
    while True:
        try:
            await scan_once(settings)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            LOGGER.error("Apple TV discovery failed: %s", type(err).__name__)
        await asyncio.sleep(settings.scan_interval)


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        LOGGER.info("Universal Remote Relay stopped")


if __name__ == "__main__":
    main()
