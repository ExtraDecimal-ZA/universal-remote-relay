"""Tests for protected single-target storage and legacy migration."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from target_store import SavedTarget, migrate_legacy_target


class TargetStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.options = self.root / "options.json"
        self.target = self.root / "target.json"

    def tearDown(self):
        self.directory.cleanup()

    def test_saved_target_round_trip(self):
        expected = SavedTarget("apple_tv", "Living Room", "192.0.2.10", "stable-id")
        expected.save(self.target)
        self.assertEqual(SavedTarget.load(self.target), expected)

    def test_complete_legacy_target_is_migrated_once(self):
        self.options.write_text(
            json.dumps(
                {
                    "log_level": "info",
                    "target_platform": "apple_tv",
                    "target_name": "Living Room",
                    "target_identifier": "stable-id",
                    "target_address": "192.0.2.10",
                }
            ),
            encoding="utf-8",
        )
        self.assertTrue(migrate_legacy_target(self.options, self.target))
        self.assertEqual(SavedTarget.load(self.target).identifier, "stable-id")
        self.assertFalse(migrate_legacy_target(self.options, self.target))

    def test_existing_target_is_never_overwritten(self):
        original = SavedTarget("apple_tv", "Current", "192.0.2.20", "current-id")
        original.save(self.target)
        self.options.write_text(
            json.dumps(
                {
                    "target_platform": "apple_tv",
                    "target_name": "Legacy",
                    "target_identifier": "legacy-id",
                    "target_address": "192.0.2.10",
                }
            ),
            encoding="utf-8",
        )
        self.assertFalse(migrate_legacy_target(self.options, self.target))
        self.assertEqual(SavedTarget.load(self.target), original)

    def test_incomplete_legacy_target_is_not_migrated(self):
        self.options.write_text(
            json.dumps({"target_platform": "apple_tv", "target_name": "TV"}),
            encoding="utf-8",
        )
        self.assertFalse(migrate_legacy_target(self.options, self.target))
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
