"""Universal Remote Relay experimental service and private selector UI."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from aiohttp import ClientError, ClientSession, ClientTimeout, web
from apple_tv import AppleTVController
from bluetooth_pairing import BluetoothPairing
from pairing_probe import PairingProbe
from selector import create_app
from target_store import LEGACY_OPTION_KEYS, migrate_legacy_target, read_options

LOG = logging.getLogger("universal_remote_relay")
VERSION = "0.4.8"
LOG_LEVELS = {"debug", "info", "warning", "error"}


def configured_log_level(options: dict[str, object]) -> str:
    """Return a supported log level from the Home Assistant options."""
    value = options.get("log_level", "info")
    if not isinstance(value, str) or value not in LOG_LEVELS:
        raise ValueError("log_level must be debug, info, warning, or error")
    return value


def validate_ingress_port(value: object, *, allow_zero: bool = False) -> int:
    """Return a safe TCP port supplied by Home Assistant Supervisor."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("Supervisor returned an invalid ingress port")
    minimum = 0 if allow_zero else 1
    if not minimum <= value <= 65535:
        raise ValueError("Supervisor returned an invalid ingress port")
    return value


async def resolve_ingress_port() -> int:
    """Read the assigned ingress port without depending on a Bashio version."""
    override = os.environ.get("INGRESS_PORT")
    if override is not None:
        try:
            value = int(override)
        except ValueError as error:
            raise RuntimeError("INGRESS_PORT must be a TCP port number") from error
        return validate_ingress_port(value, allow_zero=True)

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise RuntimeError("Supervisor token is unavailable")
    url = (
        os.environ.get("SUPERVISOR_URL", "http://supervisor").rstrip("/")
        + "/addons/self/info"
    )
    timeout = ClientTimeout(total=15)
    async with (
        ClientSession(timeout=timeout) as session,
        session.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
        ) as response,
    ):
        if response.status >= 300:
            raise RuntimeError(f"Supervisor ingress lookup failed ({response.status})")
        payload = await response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise TypeError("Supervisor returned an invalid app-info response")
    return validate_ingress_port(payload["data"].get("ingress_port"))


async def clean_legacy_options(options: dict[str, object]) -> bool:
    """Remove retired target fields only after their data has been migrated."""
    if not any(key in options for key in LEGACY_OPTION_KEYS):
        return False
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        LOG.warning("Legacy Configuration fields remain: Supervisor token unavailable")
        return False
    cleaned = {
        key: value for key, value in options.items() if key not in LEGACY_OPTION_KEYS
    }
    url = (
        os.environ.get("SUPERVISOR_URL", "http://supervisor").rstrip("/")
        + "/addons/self/options"
    )
    try:
        timeout = ClientTimeout(total=15)
        async with (
            ClientSession(timeout=timeout) as session,
            session.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json={"options": cleaned},
            ) as response,
        ):
            if response.status >= 300:
                LOG.warning(
                    "Legacy Configuration cleanup failed with HTTP %s",
                    response.status,
                )
                return False
    except (ClientError, OSError, TimeoutError):
        LOG.warning("Legacy Configuration cleanup could not reach Supervisor")
        return False
    LOG.info("Removed retired target fields from the Configuration tab")
    return True


async def run() -> None:
    data_dir = Path(os.environ.get("DATA_PATH", "/data"))
    options_path = data_dir / "options.json"
    target_path = data_dir / "target.json"
    options = read_options(options_path)
    log_level = configured_log_level(options)
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(levelname)s %(message)s",
    )
    if migrate_legacy_target(options_path, target_path):
        LOG.info("Migrated the saved Web UI target to protected add-on data")
    if target_path.exists() or not options.get("target_identifier"):
        await clean_legacy_options(options)
    else:
        LOG.warning("Legacy target is incomplete; retained options for recovery")
    LOG.info(
        "Universal Remote Relay v%s; web UI discovery only; target configured=%s",
        VERSION,
        target_path.exists(),
    )
    port = await resolve_ingress_port()
    LOG.info("No startup device scan is scheduled")

    apple_tv = AppleTVController(
        target_path=target_path,
        data_dir=data_dir / "apple_tv",
    )
    await apple_tv.initialize()
    pairing_probe = PairingProbe(
        data_dir=data_dir / "pairing_probe",
        command_handler=apple_tv.send_key,
    )
    bluetooth_pairing = BluetoothPairing()
    runner = web.AppRunner(
        create_app(
            target_path=target_path,
            pairing_probe=pairing_probe,
            apple_tv_controller=apple_tv,
            bluetooth_pairing=bluetooth_pairing,
        ),
        access_log=None,
    )
    try:
        await pairing_probe.start()
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        LOG.info("Private Home Assistant target selector is ready")
        await asyncio.Event().wait()
    finally:
        try:
            await asyncio.wait_for(bluetooth_pairing.close(), timeout=4)
        except Exception:  # noqa: BLE001 - keep relay cleanup independent of host Bluetooth
            LOG.warning("Bluetooth cleanup did not complete; continuing relay shutdown")
        await pairing_probe.stop()
        await apple_tv.close()
        await runner.cleanup()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        LOG.info("Universal Remote Relay stopped")


if __name__ == "__main__":
    main()
