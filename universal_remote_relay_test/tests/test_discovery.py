"""Tests for provider-neutral discovery results."""

import asyncio
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from discovery import (
    APPLE_TV,
    DiscoveredDevice,
    discover_apple_tvs,
    normalize_platform,
)


class DiscoveryTest(unittest.TestCase):
    def test_supported_platforms_only(self):
        self.assertEqual(normalize_platform("apple_tv"), "apple_tv")
        self.assertEqual(normalize_platform("android_tv"), "android_tv")
        with self.assertRaises(ValueError):
            normalize_platform("roku")

    def test_device_serializes_identifiers_as_list(self):
        device = DiscoveredDevice(
            APPLE_TV, "Living Room", "192.0.2.2", "id", ("id", "alt")
        )
        self.assertEqual(device.as_dict()["all_identifiers"], ["id", "alt"])

    def test_apple_discovery_normalizes_and_sorts(self):
        second = type(
            "Device",
            (),
            {
                "name": "Bedroom",
                "address": "192.0.2.3",
                "identifier": "id-b",
                "all_identifiers": {"id-b", None},
            },
        )()
        first = type(
            "Device",
            (),
            {
                "name": "Apple TV",
                "address": "192.0.2.2",
                "identifier": "id-a",
                "all_identifiers": {"alt-a", "id-a"},
            },
        )()

        async def scan(loop, **options):
            self.assertTrue(loop.is_running())
            self.assertEqual(options["timeout"], 3)
            return [second, first]

        devices = asyncio.run(discover_apple_tvs(timeout=3, scan_func=scan))
        self.assertEqual([device.name for device in devices], ["Apple TV", "Bedroom"])
        self.assertEqual(devices[0].all_identifiers, ("alt-a", "id-a"))


if __name__ == "__main__":
    unittest.main()
