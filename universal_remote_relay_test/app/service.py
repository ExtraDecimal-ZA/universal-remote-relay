"""Universal Remote Relay experimental service and private selector UI."""

from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web
from safe_scan import load_options, scan_once
from selector import create_app

LOG = logging.getLogger("universal_remote_relay")
VERSION = "0.2.0"


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
    if settings.enable_single_scan:
        if not await scan_once(settings):
            LOG.error("The requested one-shot discovery did not find its target")
            raise SystemExit(1)
    else:
        LOG.info("Safe idle mode; automatic discovery disabled")

    port = int(os.environ["INGRESS_PORT"])
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
