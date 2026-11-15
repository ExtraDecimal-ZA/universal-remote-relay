"""Bluetooth host pairing lifecycle and narrow agent authorization tests."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from aiohttp.test_utils import TestClient, TestServer
from bluetooth_pairing import (
    ADAPTER,
    AGENT_PATH,
    DEVICE,
    BluetoothError,
    BluetoothPairing,
    BluetoothTimeoutError,
    BlueZBackend,
    BlueZRequestError,
)
from dbus_next import Message, MessageType, Variant
from selector import create_app

ADAPTER_PATH = "/org/bluez/hci0"
DEVICE_PATH = ADAPTER_PATH + "/dev_AA_BB_CC_DD_EE_FF"


class FakeBackend:
    def __init__(self):
        self.objects = AsyncMock(
            return_value={
                ADAPTER_PATH: {ADAPTER: {"Alias": "Pi", "Powered": True}},
                DEVICE_PATH: {DEVICE: {"Alias": "Xiaomi remote", "Paired": False}},
            }
        )
        self.start_scan = AsyncMock()
        self.stop_scan = AsyncMock()
        self.pair = AsyncMock(
            return_value="Paired with Pi; input forwarding is not enabled."
        )
        self.close = AsyncMock()


class BluetoothLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = FakeBackend()
        self.controller = BluetoothPairing(self.backend, scan_seconds=0.05)

    async def asyncTearDown(self):
        await self.controller.close()

    async def test_status_does_not_scan_or_pair(self):
        status = await self.controller.status()
        self.assertTrue(status["available"])
        self.assertFalse(status["input_forwarding"])
        self.backend.start_scan.assert_not_awaited()
        self.backend.pair.assert_not_awaited()

    async def test_scan_expires_and_releases_only_our_discovery_session(self):
        await self.controller.scan()
        await asyncio.sleep(0.08)
        self.backend.start_scan.assert_awaited_once_with(ADAPTER_PATH)
        self.backend.stop_scan.assert_awaited_once_with(ADAPTER_PATH)
        self.assertFalse((await self.controller.status())["scanning"])

    async def test_no_powered_adapter_is_not_automatically_enabled(self):
        self.backend.objects.return_value[ADAPTER_PATH][ADAPTER]["Powered"] = False
        with self.assertRaisesRegex(BluetoothError, "No powered"):
            await self.controller.scan()
        self.backend.start_scan.assert_not_awaited()

    async def test_unscanned_path_is_rejected(self):
        with self.assertRaisesRegex(BluetoothError, "Scan first"):
            await self.controller.pair(DEVICE_PATH)
        self.backend.pair.assert_not_awaited()

    async def test_selected_device_pairs_and_stops_scan(self):
        await self.controller.scan()
        await self.controller.status()
        await self.controller.pair(DEVICE_PATH)
        await self.controller.pair_task
        self.backend.pair.assert_awaited_once_with(DEVICE_PATH)
        self.assertEqual(self.controller.state, "paired")
        self.backend.stop_scan.assert_awaited_once_with(ADAPTER_PATH)

    async def test_pair_failure_is_reported_without_affecting_other_services(self):
        self.backend.pair.side_effect = BluetoothError("Pairing rejected")
        await self.controller.scan()
        await self.controller.status()
        await self.controller.pair(DEVICE_PATH)
        await self.controller.pair_task
        self.assertEqual(self.controller.state, "error")
        self.assertIn("rejected", self.controller.message)

    async def test_missing_host_service_returns_clear_unavailable_status(self):
        self.backend.objects.side_effect = BluetoothError("Pi Bluetooth is unavailable")
        status = await self.controller.status()
        self.assertFalse(status["available"])
        self.assertEqual(status["devices"], [])

    async def test_old_expiry_cannot_stop_restarted_scan(self):
        await self.controller.scan()
        old_task = self.controller.scan_task
        await self.controller.stop_scan()
        self.assertTrue(old_task.cancelled())
        await self.controller.scan()
        self.assertTrue(self.controller.scan_adapter)

    async def test_close_releases_scan_and_bus(self):
        await self.controller.scan()
        await self.controller.close()
        self.backend.stop_scan.assert_awaited_once()
        self.backend.close.assert_awaited_once()

    async def test_other_adapter_devices_cannot_be_selected_from_this_scan(self):
        other = "/org/bluez/hci1/dev_11_22_33_44_55_66"
        self.backend.objects.return_value[other] = {
            DEVICE: {"Alias": "Other adapter remote"}
        }
        await self.controller.scan()
        status = await self.controller.status()
        self.assertFalse(
            next(item for item in status["devices"] if item["id"] == other)[
                "selectable"
            ]
        )
        with self.assertRaisesRegex(BluetoothError, "Scan first"):
            await self.controller.pair(other)

    async def test_expired_scan_selection_requires_a_new_scan(self):
        await self.controller.scan()
        await self.controller.stop_scan()
        self.controller.selection_expires = asyncio.get_running_loop().time() - 1
        with self.assertRaisesRegex(BluetoothError, "Scan first"):
            await self.controller.pair(DEVICE_PATH)
        self.backend.pair.assert_not_awaited()

    async def test_failed_stop_disconnects_our_bus_and_allows_retry(self):
        await self.controller.scan()
        self.backend.stop_scan.side_effect = BluetoothError("host unavailable")
        with self.assertRaisesRegex(BluetoothError, "connection was reset"):
            await self.controller.stop_scan()
        self.backend.close.assert_awaited_once()
        self.assertFalse(self.controller.scan_adapter)
        self.assertEqual(self.controller.state, "error")
        self.backend.stop_scan.side_effect = None
        await self.controller.scan()
        self.assertTrue(self.controller.scan_adapter)

    async def test_closed_controller_does_not_reopen_the_bus(self):
        await self.controller.close()
        await self.controller.close()
        self.assertFalse((await self.controller.status())["available"])
        self.backend.objects.assert_not_awaited()
        self.backend.close.assert_awaited_once()
        with self.assertRaisesRegex(BluetoothError, "stopped"):
            await self.controller.scan()

    async def test_adapter_power_loss_prevents_pairing_from_old_scan(self):
        await self.controller.scan()
        await self.controller.stop_scan()
        self.backend.objects.return_value[ADAPTER_PATH][ADAPTER]["Powered"] = False
        with self.assertRaisesRegex(BluetoothError, "no longer powered"):
            await self.controller.pair(DEVICE_PATH)


class BlueZAgentTest(unittest.TestCase):
    def setUp(self):
        self.backend = BlueZBackend()
        self.backend.owner = ":1.5"
        self.backend.selected = DEVICE_PATH

    def message(self, member, path=DEVICE_PATH, sender=":1.5"):
        return Message(
            path=AGENT_PATH,
            interface="org.bluez.Agent1",
            member=member,
            sender=sender,
            signature="o",
            body=[path],
            serial=1,
        )

    def test_only_selected_remote_can_be_authorized(self):
        reply = self.backend.agent_message(self.message("RequestAuthorization"))
        self.assertEqual(reply.message_type, MessageType.METHOD_RETURN)
        reply = self.backend.agent_message(
            self.message("RequestAuthorization", path="/other")
        )
        self.assertEqual(reply.message_type, MessageType.ERROR)

    def test_other_bus_senders_are_ignored(self):
        self.assertIsNone(
            self.backend.agent_message(
                self.message("RequestAuthorization", sender=":1.9")
            )
        )

    def test_pin_request_is_rejected_instead_of_inventing_a_pin(self):
        reply = self.backend.agent_message(self.message("RequestPinCode"))
        self.assertEqual(reply.message_type, MessageType.ERROR)
        self.assertEqual(self.backend.last_agent_event, "RequestPinCode")

    def test_agent_diagnostics_never_log_passkeys(self):
        message = Message(
            path=AGENT_PATH,
            interface="org.bluez.Agent1",
            member="RequestConfirmation",
            sender=":1.5",
            signature="ou",
            body=[DEVICE_PATH, 654321],
            serial=1,
        )
        with self.assertLogs("universal_remote_relay", level="INFO") as captured:
            reply = self.backend.agent_message(message)
        self.assertEqual(reply.message_type, MessageType.ERROR)
        self.assertEqual(self.backend.last_agent_event, "RequestConfirmation")
        self.assertIn("step=RequestConfirmation", " ".join(captured.output))
        self.assertNotIn("654321", " ".join(captured.output))
        self.assertNotIn(DEVICE_PATH, " ".join(captured.output))

    def test_other_devices_cannot_change_agent_diagnostics(self):
        self.backend.agent_message(self.message("RequestPinCode", path="/other"))
        self.assertEqual(self.backend.last_agent_event, "none")


class BlueZBackendTest(unittest.IsolatedAsyncioTestCase):
    def pairing_backend(self, failure_member, error, device_state=None):
        backend = BlueZBackend()
        backend.bus = Mock()
        backend.bus.call = AsyncMock(
            return_value=Mock(message_type=MessageType.METHOD_RETURN, body=[":1.5"])
        )

        async def call(path, interface, member, *args, **kwargs):
            if member == failure_member:
                raise error
            if member == "GetAll":
                return [device_state or {}]
            return [{}]

        backend.call = AsyncMock(side_effect=call)
        return backend

    async def test_method_timeouts_name_operation_and_duration(self):
        for member, seconds in (("Pair", 60), ("RegisterAgent", 8)):
            with self.subTest(member=member):
                backend = BlueZBackend()
                backend.bus = Mock(connected=True)
                backend.bus.call = AsyncMock(
                    side_effect=TimeoutError("provider secret")
                )
                with self.assertRaises(BluetoothTimeoutError) as raised:
                    await backend.call(DEVICE_PATH, DEVICE, member, timeout=seconds)
                self.assertEqual(raised.exception.member, member)
                self.assertEqual(raised.exception.seconds, seconds)
                self.assertIn(
                    f"{member} timed out after {seconds} seconds", str(raised.exception)
                )
                self.assertNotIn("provider secret", str(raised.exception))
                if member != "Pair":
                    self.assertNotIn("pairing mode", str(raised.exception))

    async def test_owner_lookup_timeout_has_operation_context(self):
        backend = self.pairing_backend("unused", BluetoothError("unused"))
        backend.bus.call.side_effect = TimeoutError()
        with self.assertRaisesRegex(BluetoothTimeoutError, "GetNameOwner.*8 seconds"):
            await backend.pair(DEVICE_PATH)
        methods = [call.args[2] for call in backend.call.await_args_list]
        self.assertNotIn("Pair", methods)

    async def test_pair_timeout_keeps_confirmed_connected_bond(self):
        backend = self.pairing_backend(
            "Pair",
            BluetoothTimeoutError("Pair", 60),
            {"Paired": Variant("b", True), "Connected": Variant("b", True)},
        )
        result = await backend.pair(DEVICE_PATH)
        self.assertIn("Paired and connected", result)
        methods = [call.args[2] for call in backend.call.await_args_list]
        self.assertIn("GetAll", methods)
        self.assertIn("Set", methods)
        self.assertNotIn("CancelPairing", methods)
        self.assertNotIn("Connect", methods)
        self.assertIsNone(backend.selected)

    async def test_pair_timeout_keeps_bond_and_attempts_missing_connection(self):
        backend = self.pairing_backend(
            "Pair",
            BluetoothTimeoutError("Pair", 60),
            {"Paired": True, "Connected": False},
        )
        result = await backend.pair(DEVICE_PATH)
        self.assertIn("Paired and connected", result)
        methods = [call.args[2] for call in backend.call.await_args_list]
        self.assertIn("Connect", methods)
        self.assertNotIn("CancelPairing", methods)

    async def test_pair_timeout_without_bond_cancels_and_reports_safe_state(self):
        backend = self.pairing_backend(
            "Pair",
            BluetoothTimeoutError("Pair", 60),
            {"Paired": False, "Connected": False},
        )
        with self.assertRaises(BluetoothTimeoutError) as raised:
            await backend.pair(DEVICE_PATH)
        self.assertIn("paired=False, connected=False", str(raised.exception))
        self.assertIn("agent step=none", str(raised.exception))
        methods = [call.args[2] for call in backend.call.await_args_list]
        self.assertEqual(methods.count("CancelPairing"), 1)
        self.assertNotIn("Set", methods)
        self.assertNotIn("Connect", methods)

    async def test_pair_timeout_unknown_state_is_never_reported_as_paired(self):
        backend = self.pairing_backend(
            "Pair",
            BluetoothTimeoutError("Pair", 60),
            {"Paired": "private detail", "Connected": "private detail"},
        )
        with self.assertRaises(BluetoothTimeoutError) as raised:
            await backend.pair(DEVICE_PATH)
        self.assertIn("paired=None, connected=None", str(raised.exception))
        self.assertNotIn("private detail", str(raised.exception))
        methods = [call.args[2] for call in backend.call.await_args_list]
        self.assertIn("CancelPairing", methods)

    async def test_pair_timeout_state_lookup_failure_preserves_original_failure(self):
        backend = self.pairing_backend("Pair", BluetoothTimeoutError("Pair", 60))
        original = backend.call.side_effect

        async def call(path, interface, member, *args, **kwargs):
            if member == "GetAll":
                raise BluetoothTimeoutError("GetAll", 8)
            return await original(path, interface, member, *args, **kwargs)

        backend.call.side_effect = call
        with self.assertRaisesRegex(BluetoothTimeoutError, "Pair timed out after 60"):
            await backend.pair(DEVICE_PATH)
        methods = [call.args[2] for call in backend.call.await_args_list]
        self.assertIn("CancelPairing", methods)
        self.assertNotIn("Set", methods)

    async def test_busy_reply_preserves_operation_without_exposing_provider_body(self):
        backend = BlueZBackend()
        backend.bus = Mock(connected=True)
        backend.bus.call = AsyncMock(
            return_value=Mock(
                message_type=MessageType.ERROR,
                error_name="org.bluez.Error.InProgress",
                body=["private provider detail"],
            )
        )
        with self.assertRaises(BlueZRequestError) as raised:
            await backend.call(DEVICE_PATH, DEVICE, "Pair")
        self.assertEqual(raised.exception.member, "Pair")
        self.assertEqual(raised.exception.error_name, "org.bluez.Error.InProgress")
        self.assertIn("already pairing or connecting", str(raised.exception))
        self.assertNotIn("permissions", str(raised.exception))
        self.assertNotIn("private provider detail", str(raised.exception))

    async def test_busy_scan_releases_own_client_and_retries_once(self):
        backend = BlueZBackend()
        backend.call = AsyncMock(
            side_effect=[
                BlueZRequestError("StartDiscovery", "org.bluez.Error.InProgress"),
                [],
            ]
        )
        backend.close = AsyncMock()
        with patch("bluetooth_pairing.asyncio.sleep", new_callable=AsyncMock):
            await backend.start_scan(ADAPTER_PATH)
        backend.close.assert_awaited_once()
        self.assertEqual(backend.call.await_count, 2)
        self.assertTrue(
            all(
                call.args[2] == "StartDiscovery"
                for call in backend.call.await_args_list
            )
        )

    async def test_persistently_busy_scan_is_bounded_and_releases_client(self):
        backend = BlueZBackend()
        backend.call = AsyncMock(
            side_effect=BlueZRequestError(
                "StartDiscovery", "org.bluez.Error.InProgress"
            )
        )
        backend.close = AsyncMock()
        with (
            patch("bluetooth_pairing.asyncio.sleep", new_callable=AsyncMock),
            self.assertRaisesRegex(BluetoothError, "busy.*StartDiscovery"),
        ):
            await backend.start_scan(ADAPTER_PATH)
        self.assertEqual(backend.call.await_count, 2)
        self.assertEqual(backend.close.await_count, 2)

    async def test_denied_scan_is_not_retried(self):
        backend = BlueZBackend()
        backend.call = AsyncMock(
            side_effect=BlueZRequestError(
                "StartDiscovery", "org.bluez.Error.NotAuthorized"
            )
        )
        backend.close = AsyncMock()
        with self.assertRaisesRegex(BluetoothError, "NotAuthorized"):
            await backend.start_scan(ADAPTER_PATH)
        backend.call.assert_awaited_once()
        backend.close.assert_not_awaited()

    async def test_unanswered_scan_releases_untracked_discovery(self):
        for failure in (BluetoothError("timed out"), asyncio.CancelledError()):
            with self.subTest(failure=type(failure).__name__):
                backend = BlueZBackend()
                backend.call = AsyncMock(side_effect=failure)
                backend.close = AsyncMock()
                with self.assertRaises(type(failure)):
                    await backend.start_scan(ADAPTER_PATH)
                backend.close.assert_awaited_once()

    async def test_retry_timeout_also_releases_client(self):
        backend = BlueZBackend()
        backend.call = AsyncMock(
            side_effect=[
                BlueZRequestError("StartDiscovery", "org.bluez.Error.InProgress"),
                BluetoothError("timed out"),
            ]
        )
        backend.close = AsyncMock()
        with (
            patch("bluetooth_pairing.asyncio.sleep", new_callable=AsyncMock),
            self.assertRaisesRegex(BluetoothError, "timed out"),
        ):
            await backend.start_scan(ADAPTER_PATH)
        self.assertEqual(backend.close.await_count, 2)

    async def test_rejected_pair_never_cancels_an_existing_pairing(self):
        for name in ("InProgress", "AuthenticationRejected", "AlreadyExists"):
            with self.subTest(error=name):
                backend = self.pairing_backend(
                    "Pair", BlueZRequestError("Pair", f"org.bluez.Error.{name}")
                )
                with self.assertRaises(BlueZRequestError):
                    await backend.pair(DEVICE_PATH)
                methods = [call.args[2] for call in backend.call.await_args_list]
                self.assertNotIn("CancelPairing", methods)
                self.assertNotIn("Set", methods)
                self.assertNotIn("Connect", methods)
                self.assertIsNone(backend.selected)

    async def test_unanswered_pair_cancels_own_attempt(self):
        for failure in (BluetoothError("timed out"), asyncio.CancelledError()):
            with self.subTest(failure=type(failure).__name__):
                backend = self.pairing_backend("Pair", failure)
                with self.assertRaises(type(failure)):
                    await backend.pair(DEVICE_PATH)
                methods = [call.args[2] for call in backend.call.await_args_list]
                self.assertEqual(methods.count("CancelPairing"), 1)
                self.assertNotIn("Set", methods)
                self.assertIsNone(backend.selected)

    async def test_trust_failure_does_not_cancel_completed_pairing(self):
        backend = self.pairing_backend("Set", BluetoothError("trust denied"))
        with self.assertRaisesRegex(BluetoothError, "trust denied"):
            await backend.pair(DEVICE_PATH)
        methods = [call.args[2] for call in backend.call.await_args_list]
        self.assertNotIn("CancelPairing", methods)
        self.assertNotIn("Connect", methods)

    async def test_busy_connect_keeps_successful_pairing(self):
        backend = self.pairing_backend(
            "Connect", BlueZRequestError("Connect", "org.bluez.Error.InProgress")
        )
        result = await backend.pair(DEVICE_PATH)
        self.assertIn("Paired with the Pi; connection is not ready", result)
        methods = [call.args[2] for call in backend.call.await_args_list]
        self.assertNotIn("CancelPairing", methods)

    async def test_pair_registers_application_agent_and_trusts_only_selected_device(
        self,
    ):
        backend = BlueZBackend()
        backend.bus = Mock()
        backend.bus.call = AsyncMock(
            return_value=Mock(message_type=MessageType.METHOD_RETURN, body=[":1.5"])
        )
        backend.call = AsyncMock(return_value=[{}])
        await backend.pair(DEVICE_PATH)
        methods = [call.args[2] for call in backend.call.await_args_list]
        self.assertEqual(
            methods, ["GetManagedObjects", "RegisterAgent", "Pair", "Set", "Connect"]
        )
        self.assertNotIn("RequestDefaultAgent", methods)
        pair_call = backend.call.await_args_list[2]
        self.assertEqual(pair_call.args[0], DEVICE_PATH)
        self.assertIsNone(backend.selected)

    async def test_unavailable_system_bus_is_recoverable(self):
        with (
            patch("bluetooth_pairing.MessageBus", side_effect=OSError("no bus")),
            self.assertRaises(BluetoothError),
        ):
            await BlueZBackend().objects()

    async def test_failed_connect_disconnects_and_forgets_candidate(self):
        backend = BlueZBackend()
        bus = Mock()
        bus.connect = AsyncMock(side_effect=OSError("authentication failure"))
        with (
            patch("bluetooth_pairing.MessageBus", return_value=bus),
            self.assertRaises(BluetoothError),
        ):
            await backend.objects()
        bus.disconnect.assert_called_once()
        self.assertIsNone(backend.bus)

    async def test_cancelled_connect_disconnects_and_preserves_cancellation(self):
        backend = BlueZBackend()
        bus = Mock()
        bus.connect = AsyncMock(side_effect=asyncio.CancelledError)
        with (
            patch("bluetooth_pairing.MessageBus", return_value=bus),
            self.assertRaises(asyncio.CancelledError),
        ):
            await backend.objects()
        bus.disconnect.assert_called_once()
        self.assertIsNone(backend.bus)

    async def test_close_disconnects_even_when_agent_cleanup_is_cancelled(self):
        backend = BlueZBackend()
        bus = backend.bus = Mock()
        backend.agent_registered = True
        backend.call = AsyncMock(side_effect=asyncio.CancelledError)
        with self.assertRaises(asyncio.CancelledError):
            await backend.close()
        bus.disconnect.assert_called_once()
        self.assertIsNone(backend.bus)
        self.assertFalse(backend.agent_registered)

    async def test_dead_connection_is_replaced_on_next_request(self):
        backend = BlueZBackend()
        dead = backend.bus = Mock(connected=False)
        fresh = Mock(connected=True)
        fresh.connect = AsyncMock(return_value=fresh)
        fresh.call = AsyncMock(
            return_value=Mock(message_type=MessageType.METHOD_RETURN, body=[{}])
        )
        with patch("bluetooth_pairing.MessageBus", return_value=fresh):
            self.assertEqual(await backend.objects(), {})
        dead.disconnect.assert_called_once()
        self.assertIs(backend.bus, fresh)

    async def test_bluez_restart_reregisters_agent_for_new_owner(self):
        backend = BlueZBackend()
        backend.bus = Mock()
        backend.bus.call = AsyncMock(
            side_effect=[
                Mock(message_type=MessageType.METHOD_RETURN, body=[":1.5"]),
                Mock(message_type=MessageType.METHOD_RETURN, body=[":1.8"]),
            ]
        )
        backend.call = AsyncMock(return_value=[{}])
        await backend.pair(DEVICE_PATH)
        await backend.pair(DEVICE_PATH)
        self.assertEqual(backend.owner, ":1.8")
        registrations = [
            call
            for call in backend.call.await_args_list
            if call.args[2] == "RegisterAgent"
        ]
        self.assertEqual(len(registrations), 2)


class BluetoothEndpointTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.controller = BluetoothPairing(FakeBackend())
        self.client = TestClient(
            TestServer(
                create_app(allowed_remote=None, bluetooth_pairing=self.controller)
            )
        )
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.controller.close()

    async def test_scan_then_pair_through_private_api(self):
        response = await self.client.post("/api/bluetooth/scan")
        self.assertEqual(response.status, 200)
        self.assertTrue((await response.json())["scanning"])
        response = await self.client.post(
            "/api/bluetooth/pair", json={"id": DEVICE_PATH}
        )
        self.assertEqual(response.status, 200)
        await self.controller.pair_task
        self.assertEqual(self.controller.state, "paired")

    async def test_invalid_selection_returns_json_error(self):
        response = await self.client.post("/api/bluetooth/pair", json=[])
        self.assertEqual(response.status, 409)
        self.assertIn("error", await response.json())

    async def test_ingress_guard_also_protects_bluetooth_mutations(self):
        client = TestClient(TestServer(create_app(bluetooth_pairing=self.controller)))
        await client.start_server()
        try:
            response = await client.post("/api/bluetooth/scan")
            self.assertEqual(response.status, 403)
            self.controller.backend.start_scan.assert_not_awaited()
        finally:
            await client.close()
