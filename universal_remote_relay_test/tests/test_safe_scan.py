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
            self.assertEqual(safe_scan.load_options(Path(directory) / "missing.json"), (False, "info"))

    def test_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(json.dumps({"enable_single_scan": True, "log_level": "debug"}))
            self.assertEqual(safe_scan.load_options(path), (True, "debug"))

    def test_reject_invalid_boolean(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text('{"enable_single_scan": "true"}')
            with self.assertRaises(ValueError):
                safe_scan.load_options(path)


if __name__ == "__main__":
    unittest.main()
