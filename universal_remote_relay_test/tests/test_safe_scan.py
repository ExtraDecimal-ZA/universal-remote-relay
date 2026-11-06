"""Tests for safe scan options without importing pyatv."""
import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
                        "target_name": " Media Room ",
                        "target_identifier": " target-id ",
                    }
                )
            )
            self.assertEqual(
                safe_scan.load_options(path),
                (True, "debug", "Media Room", "target-id"),
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
        device = type("Device", (), {"name": "Media Room"})()
        self.assertTrue(safe_scan.matches_target(device, "Media Room"))
        self.assertFalse(safe_scan.matches_target(device, "Office Connect+"))
        self.assertTrue(safe_scan.matches_target(device, ""))

    def test_identifiers_are_sorted_and_empty_values_removed(self):
        device = type("Device", (), {"all_identifiers": {"id-b", None, "id-a"}})()
        self.assertEqual(safe_scan.identifiers_for(device), ["id-a", "id-b"])

    def test_stable_identifier_ignores_changed_name(self):
        device = type(
            "Device",
            (),
            {
                "name": "Cinema",
                "address": "192.0.2.10",
                "identifier": "stable-id",
                "all_identifiers": {"stable-id"},
            },
        )()
        captured_options = {}

        async def scan(loop, **options):
            captured_options.update(options)
            return [device]

        with self.assertLogs(safe_scan.LOG, level="INFO") as captured:
            result = asyncio.run(safe_scan.scan_once("Old Name", "stable-id", scan))
        self.assertTrue(result)
        self.assertEqual(captured_options["identifier"], "stable-id")
        self.assertIn("name='Cinema'", "\n".join(captured.output))

    def test_scan_failure_returns_false(self):
        async def failed_scan(*args, **kwargs):
            raise RuntimeError("boom")

        result = asyncio.run(safe_scan.scan_once(scan_func=failed_scan))
        self.assertFalse(result)

    def test_enabled_scan_failure_exits_unsuccessfully(self):
        options = (True, "info", "", "stable-id")

        def failed_run(coroutine):
            coroutine.close()
            return False

        with patch.object(safe_scan, "load_options", return_value=options):
            with patch.object(safe_scan.asyncio, "run", side_effect=failed_run):
                with self.assertRaises(SystemExit) as raised:
                    safe_scan.main()
        self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
