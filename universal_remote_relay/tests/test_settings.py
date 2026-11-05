import json
import tempfile
import unittest
from pathlib import Path

from app.main import Settings, load_settings


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(Settings(), Settings.from_mapping({}))

    def test_loads_options_file(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            options = Path(directory) / "options.json"
            options.write_text(
                json.dumps(
                    {
                        "log_level": "debug",
                        "apple_tv_identifier": "living-room-id",
                        "scan_interval": 60,
                    }
                ),
                encoding="utf-8",
            )

            settings = load_settings(options)

        self.assertEqual("debug", settings.log_level)
        self.assertEqual("living-room-id", settings.apple_tv_identifier)
        self.assertEqual(60, settings.scan_interval)

    def test_rejects_unsafe_scan_interval(self):
        with self.assertRaisesRegex(ValueError, "scan_interval"):
            Settings.from_mapping({"scan_interval": 1})


if __name__ == "__main__":
    unittest.main()
