"""Universal Remote Relay experimental service and private selector UI."""

from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import ClientSession, ClientTimeout, web
from safe_scan import load_options, scan_once
from selector import create_app

LOG = logging.getLogger("universal_remote_relay")
VERSION = "0.2.1"


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


async def run() -> None:
    settings = load_options()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(levelname)s %(message)s",
    )
    LOG.info(
        "Universal Remote Relay v%s; single scan enabled=%s platform=%s",
        VERSION,
        settings.enable_single_scan,
        settings.target_platform,
    )
    port = await resolve_ingress_port()
    if settings.enable_single_scan:
        if not await scan_once(settings):
            LOG.error("The requested one-shot discovery did not find its target")
            raise SystemExit(1)
    else:
        LOG.info("Safe idle mode; automatic discovery disabled")

    runner = web.AppRunner(create_app(), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    LOG.info("Private Home Assistant target selector is ready")
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        LOG.info("Universal Remote Relay stopped")


if __name__ == "__main__":
    main()
