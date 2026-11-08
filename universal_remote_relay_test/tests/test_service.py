"""Regression tests for Home Assistant ingress startup."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestServer

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from service import (
    clean_legacy_options,
    configured_log_level,
    resolve_ingress_port,
    validate_ingress_port,
)


class IngressPortTest(unittest.IsolatedAsyncioTestCase):
    def test_log_level_defaults_to_info(self):
        self.assertEqual(configured_log_level({}), "info")

    def test_invalid_log_level_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "log_level"):
            configured_log_level({"log_level": "verbose"})

    async def test_reads_dynamic_port_from_supervisor_self_info(self):
        captured = {}

        async def info(request):
            captured["authorization"] = request.headers.get("Authorization")
            return web.json_response({"result": "ok", "data": {"ingress_port": 62345}})

        app = web.Application()
        app.router.add_get("/addons/self/info", info)
        server = TestServer(app)
        await server.start_server()
        try:
            with patch.dict(
                "os.environ",
                {
                    "SUPERVISOR_TOKEN": "test-token",
                    "SUPERVISOR_URL": str(server.make_url("/")).rstrip("/"),
                },
                clear=True,
            ):
                self.assertEqual(await resolve_ingress_port(), 62345)
        finally:
            await server.close()
        self.assertEqual(captured["authorization"], "Bearer test-token")

    async def test_explicit_zero_port_supports_container_smoke_test(self):
        with patch.dict("os.environ", {"INGRESS_PORT": "0"}, clear=True):
            self.assertEqual(await resolve_ingress_port(), 0)

    async def test_missing_supervisor_token_fails_clearly(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            self.assertRaisesRegex(RuntimeError, "token is unavailable"),
        ):
            await resolve_ingress_port()

    async def test_invalid_override_fails_clearly(self):
        with (
            patch.dict("os.environ", {"INGRESS_PORT": "not-a-port"}, clear=True),
            self.assertRaisesRegex(RuntimeError, "TCP port number"),
        ):
            await resolve_ingress_port()

    async def test_null_supervisor_port_is_rejected(self):
        async def info(request):
            del request
            return web.json_response({"result": "ok", "data": {"ingress_port": None}})

        app = web.Application()
        app.router.add_get("/addons/self/info", info)
        server = TestServer(app)
        await server.start_server()
        try:
            with (
                patch.dict(
                    "os.environ",
                    {
                        "SUPERVISOR_TOKEN": "test-token",
                        "SUPERVISOR_URL": str(server.make_url("/")).rstrip("/"),
                    },
                    clear=True,
                ),
                self.assertRaisesRegex(TypeError, "invalid ingress port"),
            ):
                await resolve_ingress_port()
        finally:
            await server.close()

    def test_boolean_is_not_accepted_as_a_port(self):
        with self.assertRaisesRegex(TypeError, "invalid ingress port"):
            validate_ingress_port(True)

    async def test_legacy_fields_are_removed_through_supervisor(self):
        captured = {}

        async def update_options(request):
            captured["authorization"] = request.headers.get("Authorization")
            captured["payload"] = await request.json()
            return web.json_response({"result": "ok"})

        app = web.Application()
        app.router.add_post("/addons/self/options", update_options)
        server = TestServer(app)
        await server.start_server()
        try:
            with patch.dict(
                "os.environ",
                {
                    "SUPERVISOR_TOKEN": "test-token",
                    "SUPERVISOR_URL": str(server.make_url("/")).rstrip("/"),
                },
                clear=True,
            ):
                changed = await clean_legacy_options(
                    {
                        "log_level": "debug",
                        "target_platform": "apple_tv",
                        "target_name": "Living Room",
                        "target_identifier": "stable-id",
                        "target_address": "192.0.2.10",
                        "enable_single_scan": False,
                    }
                )
        finally:
            await server.close()
        self.assertTrue(changed)
        self.assertEqual(captured["authorization"], "Bearer test-token")
        self.assertEqual(captured["payload"], {"options": {"log_level": "debug"}})

    async def test_cleanup_is_skipped_when_no_legacy_fields_exist(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(await clean_legacy_options({"log_level": "info"}))


if __name__ == "__main__":
    unittest.main()
