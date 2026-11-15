"""Bounded local-network discovery for supported television platforms."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass

APPLE_TV = "apple_tv"
ANDROID_TV = "android_tv"
SUPPORTED_PLATFORMS = (APPLE_TV, ANDROID_TV)


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    """A non-secret device identity suitable for display and configuration."""

    platform: str
    name: str
    address: str
    identifier: str
    all_identifiers: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, str | list[str]]:
        payload = asdict(self)
        payload["all_identifiers"] = list(self.all_identifiers)
        return payload


def normalize_platform(value: object) -> str:
    if value not in SUPPORTED_PLATFORMS:
        raise ValueError("target_platform must be apple_tv or android_tv")
    return str(value)


def _clean_identifiers(values: object) -> tuple[str, ...]:
    if not values:
        return ()
    return tuple(sorted(str(value) for value in values if value))


async def discover_apple_tvs(
    *, timeout: float = 10, scan_func=None
) -> list[DiscoveredDevice]:
    """Discover Apple TVs with pyatv without pairing or connecting."""
    if scan_func is None:
        import pyatv

        scan_func = pyatv.scan

    devices = await asyncio.wait_for(
        scan_func(asyncio.get_running_loop(), timeout=timeout),
        timeout=timeout + 5,
    )
    discovered: list[DiscoveredDevice] = []
    for device in devices:
        identifiers = _clean_identifiers(getattr(device, "all_identifiers", ()))
        primary = str(getattr(device, "identifier", "") or "")
        if not primary and identifiers:
            primary = identifiers[0]
        discovered.append(
            DiscoveredDevice(
                platform=APPLE_TV,
                name=str(getattr(device, "name", "Apple TV")),
                address=str(getattr(device, "address", "")),
                identifier=primary,
                all_identifiers=identifiers,
            )
        )
    return sorted(discovered, key=lambda item: (item.name.casefold(), item.address))


def _android_display_name(service_name: str, properties: dict[bytes, bytes]) -> str:
    for key in (b"name", b"fn", b"md"):
        value = properties.get(key)
        if value:
            return value.decode("utf-8", errors="replace").strip()
    return service_name.removesuffix("._androidtvremote2._tcp.local.").strip()


async def discover_android_tvs(*, timeout: float = 5) -> list[DiscoveredDevice]:
    """Discover Android/Google TV Remote v2 services without pairing."""
    from zeroconf import ServiceStateChange
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

    service_type = "_androidtvremote2._tcp.local."
    names: set[str] = set()

    def on_service_state_change(zeroconf, type_: str, name: str, state_change) -> None:
        del zeroconf, type_
        if state_change is ServiceStateChange.Added:
            names.add(name)

    zeroconf = AsyncZeroconf()
    browser = AsyncServiceBrowser(
        zeroconf.zeroconf,
        [service_type],
        handlers=[on_service_state_change],
    )
    browser_cancelled = False
    try:
        await asyncio.sleep(timeout)
        await browser.async_cancel()
        browser_cancelled = True
        discovered: list[DiscoveredDevice] = []
        for service_name in sorted(names):
            info = AsyncServiceInfo(service_type, service_name)
            if not await info.async_request(zeroconf.zeroconf, 3000):
                continue
            addresses = info.parsed_scoped_addresses()
            if not addresses:
                continue
            discovered.append(
                DiscoveredDevice(
                    platform=ANDROID_TV,
                    name=_android_display_name(service_name, info.properties),
                    address=addresses[0],
                    identifier=service_name,
                    all_identifiers=(service_name,),
                )
            )
        return sorted(discovered, key=lambda item: (item.name.casefold(), item.address))
    finally:
        if not browser_cancelled:
            await browser.async_cancel()
        await zeroconf.async_close()


async def discover_devices(
    platform: str, *, timeout: float = 10
) -> list[DiscoveredDevice]:
    platform = normalize_platform(platform)
    if platform == APPLE_TV:
        return await discover_apple_tvs(timeout=timeout)
    return await discover_android_tvs(timeout=min(timeout, 10))
