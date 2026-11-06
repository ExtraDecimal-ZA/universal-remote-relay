"""Tests for safe scan options without importing pyatv."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "app" / "safe_scan.py"
spec = importlib.util.spec_from_file_location("safe_scan", MODULE)
safe_scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(safe_scan)


class SafeScanOptionsTest(unittest.TestCase):
    def test_default_options(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                safe_scan.load_options(Path(directory) / "missing.json"),
                (False, "info", "", ""),
            )

    def test_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(
                json.dumps(
                    {
                        "enable_single_scan": True,
                        "log_level": "debug",
                        "target_name": " Living Room ",
                        "target_identifier": " target-id ",
                    }
                )
            )
            self.assertEqual(
                safe_scan.load_options(path),
                (True, "debug", "Living Room", "target-id"),
            )

    def test_reject_invalid_boolean(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text('{"enable_single_scan": "true"}')
            with self.assertRaises(ValueError):
                safe_scan.load_options(path)

    def test_reject_invalid_target_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text('{"target_name": 91}')
            with self.assertRaises(ValueError):
                safe_scan.load_options(path)

    def test_exact_target_name_match(self):
        device = type("Device", (), {"name": "Living Room"})()
        self.assertTrue(safe_scan.matches_target(device, "Living Room"))
        self.assertFalse(safe_scan.matches_target(device, "Office Connect+"))
        self.assertTrue(safe_scan.matches_target(device, ""))

    def test_identifiers_are_sorted_and_empty_values_removed(self):
        device = type("Device", (), {"all_identifiers": {"id-b", None, "id-a"}})()
        self.assertEqual(safe_scan.identifiers_for(device), ["id-a", "id-b"])


if __name__ == "__main__":
    unittest.main()
