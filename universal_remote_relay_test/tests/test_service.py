"""Regression tests for Home Assistant ingress startup."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestServer

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from service import resolve_ingress_port, validate_ingress_port


class IngressPortTest(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
