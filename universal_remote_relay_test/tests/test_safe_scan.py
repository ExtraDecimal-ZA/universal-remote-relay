"""Tests for bounded target validation without live network access."""

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from discovery import APPLE_TV, DiscoveredDevice
from safe_scan import Settings, load_options, matches_target, scan_once


class SafeScanOptionsTest(unittest.TestCase):
    def test_default_options(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_options(Path(directory) / "missing.json"), Settings())

    def test_loads_saved_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(
                json.dumps(
                    {
                        "enable_single_scan": True,
                        "log_level": "debug",
                        "target_platform": "android_tv",
                        "target_name": " Lounge TV ",
                        "target_identifier": " service-id ",
                        "target_address": " 192.0.2.10 ",
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                load_options(path),
                Settings(
                    True, "debug", "android_tv", "Lounge TV", "service-id", "192.0.2.10"
                ),
            )

    def test_rejects_invalid_boolean(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text('{"enable_single_scan": "true"}', encoding="utf-8")
            with self.assertRaises(TypeError):
                load_options(path)

    def test_rejects_invalid_platform(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text('{"target_platform": "television"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_options(path)

    def test_stable_identifier_ignores_changed_name_and_address(self):
        device = DiscoveredDevice(
            platform=APPLE_TV,
            name="New Name",
            address="192.0.2.22",
            identifier="stable-id",
            all_identifiers=("stable-id", "alternate-id"),
        )
        settings = Settings(
            target_name="Old Name",
            target_identifier="alternate-id",
            target_address="192.0.2.10",
        )
        self.assertTrue(matches_target(device, settings))

    def test_platform_must_match(self):
        device = DiscoveredDevice("android_tv", "TV", "192.0.2.5", "id")
        self.assertFalse(matches_target(device, Settings(target_identifier="id")))

    def test_scan_logs_only_selected_target(self):
        devices = [
            DiscoveredDevice(APPLE_TV, "Other", "192.0.2.1", "other"),
            DiscoveredDevice(APPLE_TV, "Renamed", "192.0.2.2", "selected"),
        ]

        async def discover(platform, *, timeout):
            self.assertEqual(platform, APPLE_TV)
            self.assertEqual(timeout, 10)
            return devices

        settings = Settings(target_name="Old Name", target_identifier="selected")
        with self.assertLogs("universal_remote_relay", level="INFO") as captured:
            result = asyncio.run(scan_once(settings, discover))
        self.assertTrue(result)
        output = "\n".join(captured.output)
        self.assertIn("name='Renamed'", output)
        self.assertNotIn("name='Other'", output)

    def test_scan_failure_returns_false(self):
        async def failed_discovery(*args, **kwargs):
            raise RuntimeError("boom")

        self.assertFalse(asyncio.run(scan_once(Settings(), failed_discovery)))


if __name__ == "__main__":
    unittest.main()
