"""Tests for persistent Apple TV pairing and command forwarding."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from apple_tv import AppleTVController, AppleTVRelayError


class FakeStorage:
    def __init__(self, filename, loop):
        del filename, loop
        self.loaded = False
        self.saved = False

    async def load(self):
        self.loaded = True

    async def save(self):
        self.saved = True


class FakeService:
    credentials = None


class FakeConfig:
    def __init__(self):
        self.service = FakeService()

    def get_service(self, protocol):
        del protocol
        return self.service


class FakePairing:
    device_provides_pin = True

    def __init__(self):
        self.has_paired = False
        self.pin_value = None
        self.closed = False

    async def begin(self):
        return None

    def pin(self, pin):
        self.pin_value = pin

    async def finish(self):
        self.has_paired = True

    async def close(self):
        self.closed = True


class FakeRemote:
    def __init__(self):
        self.actions = []

    async def up(self):
        self.actions.append("up")


class FakeConnection:
    def __init__(self):
        self.remote_control = FakeRemote()
        self.closed = False

    def close(self):
        self.closed = True
        return set()


class AppleTVControllerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.options = self.root / "options.json"
        self.options.write_text(
            json.dumps(
                {
                    "target_platform": "apple_tv",
                    "target_name": "Living Room",
                    "target_identifier": "stable-id",
                    "target_address": "192.0.2.10",
                }
            ),
            encoding="utf-8",
        )
        self.config = FakeConfig()
        self.pairing = FakePairing()
        self.connection = FakeConnection()
        self.scan_calls = []

        async def scan(loop, **options):
            del loop
            self.scan_calls.append(options)
            return [self.config]

        async def pair(config, protocol, loop, **options):
            del config, protocol, loop, options
            return self.pairing

        async def connect(config, loop, **options):
            del config, loop, options
            return self.connection

        self.controller = AppleTVController(
            options_path=self.options,
            data_dir=self.root / "apple_tv",
            scan_func=scan,
            pair_func=pair,
            connect_func=connect,
            storage_factory=FakeStorage,
        )
        await self.controller.initialize()

    async def asyncTearDown(self):
        await self.controller.close()
        self.directory.cleanup()

    async def test_pairing_pin_is_saved_once(self):
        await self.controller.start_pairing()
        self.assertEqual(self.controller.status()["state"], "waiting_for_pin")

        await self.controller.finish_pairing("1234")

        self.assertTrue(self.pairing.has_paired)
        self.assertEqual(self.pairing.pin_value, 1234)
        self.assertTrue(self.pairing.closed)
        self.assertTrue(self.controller._storage.saved)
        self.assertTrue(self.controller.status()["paired"])

    async def test_existing_credential_file_is_loaded_as_paired(self):
        await self.controller.close()
        self.controller.storage_path.write_text("{}", encoding="utf-8")
        controller = AppleTVController(
            options_path=self.options,
            data_dir=self.root / "apple_tv",
            scan_func=self.controller.scan_func,
            pair_func=self.controller.pair_func,
            connect_func=self.controller.connect_func,
            storage_factory=FakeStorage,
        )

        await controller.initialize()

        self.assertTrue(controller.status()["paired"])
        await controller.close()

    async def test_saved_identifier_and_address_are_used_for_command(self):
        action = await self.controller.send_key("DPAD_UP")

        self.assertEqual(action, "up")
        self.assertEqual(self.connection.remote_control.actions, ["up"])
        self.assertEqual(self.scan_calls[0]["identifier"], "stable-id")
        self.assertEqual(self.scan_calls[0]["hosts"], ["192.0.2.10"])

    async def test_unknown_button_is_not_sent(self):
        with self.assertRaisesRegex(AppleTVRelayError, "Unsupported"):
            await self.controller.send_key("POWER")
        self.assertEqual(self.connection.remote_control.actions, [])

    async def test_target_name_can_change_without_changing_identity(self):
        payload = json.loads(self.options.read_text(encoding="utf-8"))
        payload["target_name"] = "Renamed Apple TV"
        self.options.write_text(json.dumps(payload), encoding="utf-8")

        await self.controller.send_key("DPAD_UP")

        self.assertEqual(self.scan_calls[0]["identifier"], "stable-id")

    async def test_changed_address_falls_back_to_stable_identifier(self):
        calls = []

        async def scan(loop, **options):
            del loop
            calls.append(options)
            return [] if "hosts" in options else [self.config]

        controller = AppleTVController(
            options_path=self.options,
            data_dir=self.root / "fallback",
            scan_func=scan,
            connect_func=self.controller.connect_func,
            storage_factory=FakeStorage,
        )
        await controller.initialize()

        action = await controller.send_key("DPAD_UP")

        self.assertEqual(action, "up")
        self.assertEqual(calls[0]["hosts"], ["192.0.2.10"])
        self.assertNotIn("hosts", calls[1])
        self.assertEqual(calls[1]["identifier"], "stable-id")
        await controller.close()

    async def test_android_target_is_rejected(self):
        payload = json.loads(self.options.read_text(encoding="utf-8"))
        payload["target_platform"] = "android_tv"
        self.options.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(AppleTVRelayError, "not an Apple TV"):
            await self.controller.send_key("DPAD_UP")


if __name__ == "__main__":
    unittest.main()
