"""Tests for the single-target selector configuration contract."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from selector import (
    INDEX_HTML,
    Selection,
    create_app,
    options_with_selection,
    public_target_options,
    save_supervisor_options,
)


class SelectorTest(unittest.TestCase):
    def test_exactly_one_radio_group_auto_saves(self):
        self.assertIn("type = 'radio'", INDEX_HTML)
        self.assertIn("name = 'target'", INDEX_HTML)
        self.assertIn("saveTarget(device, radio)", INDEX_HTML)

    def test_save_failure_is_reported_and_controls_are_restored(self):
        self.assertIn("saveTarget(device, radio).catch(showError)", INDEX_HTML)
        self.assertIn("radio.checked = false", INDEX_HTML)
        self.assertIn("item.disabled = false", INDEX_HTML)

    def test_selection_requires_complete_device_identity(self):
        with self.assertRaises(ValueError):
            Selection.from_payload({"platform": "apple_tv", "name": "TV"})

    def test_selection_replaces_one_target_and_preserves_other_options(self):
        current = {
            "log_level": "info",
            "enable_single_scan": False,
            "target_platform": "apple_tv",
            "target_name": "Old",
            "target_identifier": "old-id",
            "target_address": "192.0.2.1",
        }
        selected = Selection("android_tv", "New TV", "192.0.2.2", "new-id")
        updated = options_with_selection(current, selected)
        self.assertEqual(updated["log_level"], "info")
        self.assertEqual(updated["target_platform"], "android_tv")
        self.assertEqual(updated["target_identifier"], "new-id")
        self.assertNotIn("old-id", updated.values())

    def test_public_config_excludes_unrelated_options(self):
        output = public_target_options(
            {
                "target_identifier": "device-id",
                "log_level": "debug",
                "secret": "do-not-return",
            }
        )
        self.assertEqual(output["target_identifier"], "device-id")
        self.assertEqual(output["target_platform"], "apple_tv")
        self.assertNotIn("secret", output)
        self.assertNotIn("log_level", output)


class SelectorEndpointTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.options_path = Path(self.directory.name) / "options.json"
        self.options_path.write_text(
            json.dumps({"log_level": "info", "enable_single_scan": False}),
            encoding="utf-8",
        )
        self.saved = None

        async def discover(platform, *, timeout):
            self.assertEqual(timeout, 10)
            return [
                __import__("discovery").DiscoveredDevice(
                    platform,
                    "Living Room",
                    "192.0.2.10",
                    "stable-id",
                    ("stable-id",),
                )
            ]

        async def save(options):
            self.saved = options

        app = create_app(
            options_path=self.options_path,
            allowed_remote=None,
            discover_func=discover,
            save_func=save,
        )
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.directory.cleanup()

    async def test_discovery_returns_single_choice_data(self):
        response = await self.client.post(
            "/api/discover", json={"platform": "apple_tv"}
        )
        self.assertEqual(response.status, 200)
        payload = await response.json()
        self.assertEqual(payload["devices"][0]["identifier"], "stable-id")

    async def test_select_auto_saves_one_target(self):
        discovery = await self.client.post(
            "/api/discover", json={"platform": "apple_tv"}
        )
        self.assertEqual(discovery.status, 200)
        response = await self.client.post(
            "/api/select",
            json={
                "platform": "apple_tv",
                "name": "Living Room",
                "address": "192.0.2.10",
                "identifier": "stable-id",
            },
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(self.saved["target_identifier"], "stable-id")
        self.assertEqual(self.saved["log_level"], "info")

    async def test_rejects_target_not_in_current_scan(self):
        response = await self.client.post(
            "/api/select",
            json={
                "platform": "apple_tv",
                "name": "Invented",
                "address": "192.0.2.99",
                "identifier": "invented-id",
            },
        )
        self.assertEqual(response.status, 400)
        self.assertIsNone(self.saved)

    async def test_rejects_non_object_selection(self):
        response = await self.client.post("/api/select", json=["not", "a", "device"])
        self.assertEqual(response.status, 400)
        self.assertIsNone(self.saved)

    async def test_supervisor_save_uses_self_options_endpoint(self):
        captured = {}

        async def receive(request):
            captured["authorization"] = request.headers.get("Authorization")
            captured["payload"] = await request.json()
            return web.json_response({"result": "ok"})

        app = web.Application()
        app.router.add_post("/addons/self/options", receive)
        server = TestServer(app)
        await server.start_server()
        try:
            with patch.dict(
                "os.environ",
                {
                    "SUPERVISOR_TOKEN": "test-token",
                    "SUPERVISOR_URL": str(server.make_url("/")).rstrip("/"),
                },
            ):
                await save_supervisor_options({"target_identifier": "stable-id"})
        finally:
            await server.close()
        self.assertEqual(captured["authorization"], "Bearer test-token")
        self.assertEqual(
            captured["payload"], {"options": {"target_identifier": "stable-id"}}
        )


if __name__ == "__main__":
    unittest.main()
