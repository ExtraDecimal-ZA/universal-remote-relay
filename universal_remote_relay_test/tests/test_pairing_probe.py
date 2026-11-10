"""Tests for bounded phone pairing and command capture."""

from __future__ import annotations

import asyncio
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from androidtvremote2.polo_pb2 import Options, OuterMessage
from androidtvremote2.remotemessage_pb2 import (
    RemoteDirection,
    RemoteKeyCode,
    RemoteMessage,
)
from OpenSSL import SSL, crypto
from pairing_probe import (
    PairingProbe,
    PairingProbeError,
    _generate_identity,
    _load_pem_certificate,
    _polo_message,
    encode_varint,
    pairing_code,
    pairing_secret,
    read_delimited,
    write_delimited,
)


def _client_connection(
    client_socket: socket.socket, cert_path: Path, key_path: Path
) -> SSL.Connection:
    context = SSL.Context(SSL.TLS_CLIENT_METHOD)
    context.use_certificate_file(str(cert_path))
    context.use_privatekey_file(str(key_path))
    context.set_verify(SSL.VERIFY_NONE, lambda *_args: True)
    connection = SSL.Connection(context, client_socket)
    connection.set_connect_state()
    connection.do_handshake()
    return connection


def _send_polo(connection: SSL.Connection, field: str, **values: object) -> None:
    message = _polo_message()
    payload = getattr(message, field)
    for name, value in values.items():
        setattr(payload, name, value)
    if not values:
        payload.SetInParent()
    write_delimited(connection, message.SerializeToString())


def _receive_polo(connection: SSL.Connection, field: str) -> OuterMessage:
    message = OuterMessage()
    message.ParseFromString(read_delimited(connection))
    if not message.HasField(field):
        raise AssertionError(f"Expected {field}, got {message}")
    return message


class PairingPrimitiveTest(unittest.TestCase):
    def test_varint_crosses_single_byte_boundary(self):
        self.assertEqual(encode_varint(127), b"\x7f")
        self.assertEqual(encode_varint(128), b"\x80\x01")

    def test_pairing_code_binds_both_certificates_and_nonce(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client_cert = root / "client.pem"
            client_key = root / "client.key"
            server_cert = root / "server.pem"
            server_key = root / "server.key"
            _generate_identity(client_cert, client_key, "Client")
            _generate_identity(server_cert, server_key, "Server")
            client = _load_pem_certificate(client_cert)
            server = _load_pem_certificate(server_cert)

            code = pairing_code(client, server, b"\xab\xcd")

            self.assertEqual(len(code), 6)
            self.assertEqual(code[2:], "ABCD")
            self.assertEqual(
                int(code[:2], 16), pairing_secret(client, server, b"\xab\xcd")[0]
            )

    def test_receiver_rename_preserves_existing_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cert_path = root / "relay.pem"
            key_path = root / "relay.key"
            _generate_identity(cert_path, key_path, "Universal Remote Relay Test")
            original_cert = cert_path.read_bytes()
            original_key = key_path.read_bytes()

            _generate_identity(cert_path, key_path, "Universal Remote Relay")

            self.assertEqual(cert_path.read_bytes(), original_cert)
            self.assertEqual(key_path.read_bytes(), original_key)


class PairingRoundTripTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.probe = PairingProbe(data_dir=self.root / "relay")
        _generate_identity(
            self.probe.cert_path,
            self.probe.key_path,
            self.probe.receiver_name,
        )
        self.client_cert = self.root / "phone.pem"
        self.client_key = self.root / "phone.key"
        _generate_identity(self.client_cert, self.client_key, "Phone")

    def tearDown(self):
        self.directory.cleanup()

    def _run_remote_command(self, key_code, expected):
        server_socket, client_socket = socket.socketpair()
        remote_server = threading.Thread(
            target=self.probe._run_remote_session,
            args=(server_socket, None),
            daemon=True,
        )
        remote_server.start()
        connection = _client_connection(
            client_socket, self.client_cert, self.client_key
        )
        try:
            messages = []
            for _ in range(3):
                message = RemoteMessage()
                message.ParseFromString(read_delimited(connection))
                messages.append(message)
            self.assertTrue(messages[0].HasField("remote_configure"))
            self.assertTrue(messages[1].HasField("remote_set_active"))
            self.assertTrue(messages[2].HasField("remote_start"))

            key = RemoteMessage()
            key.remote_key_inject.key_code = key_code
            key.remote_key_inject.direction = RemoteDirection.SHORT
            write_delimited(connection, key.SerializeToString())
            deadline = time.monotonic() + 2
            while self.probe.status()["last_command"] != expected:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
        finally:
            connection.close()
        remote_server.join(timeout=5)
        self.assertFalse(remote_server.is_alive())

    def test_phone_pairs_once_and_reconnects_with_saved_trust(self):
        self.probe._pairing_enabled = True
        server_socket, client_socket = socket.socketpair()
        server = threading.Thread(
            target=self.probe._run_pairing_session,
            args=(server_socket, None),
            daemon=True,
        )
        server.start()
        connection = _client_connection(
            client_socket, self.client_cert, self.client_key
        )
        try:
            _send_polo(
                connection,
                "pairing_request",
                service_name="atvremote",
                client_name="Samsung phone",
            )
            _receive_polo(connection, "pairing_request_ack")

            options = _polo_message()
            options.options.preferred_role = Options.RoleType.ROLE_TYPE_INPUT
            encoding = options.options.input_encodings.add()
            encoding.type = Options.Encoding.ENCODING_TYPE_HEXADECIMAL
            encoding.symbol_length = 6
            write_delimited(connection, options.SerializeToString())
            _receive_polo(connection, "options")

            configuration = _polo_message()
            configuration.configuration.client_role = Options.RoleType.ROLE_TYPE_INPUT
            configuration.configuration.encoding.type = (
                Options.Encoding.ENCODING_TYPE_HEXADECIMAL
            )
            configuration.configuration.encoding.symbol_length = 6
            write_delimited(connection, configuration.SerializeToString())
            _receive_polo(connection, "configuration_ack")

            deadline = time.monotonic() + 2
            code = ""
            while time.monotonic() < deadline:
                code = str(self.probe.status()["pairing_code"])
                if len(code) == 6:
                    break
                time.sleep(0.01)
            self.assertEqual(len(code), 6)
            nonce = bytes.fromhex(code[2:])
            secret = pairing_secret(
                _load_pem_certificate(self.client_cert),
                _load_pem_certificate(self.probe.cert_path),
                nonce,
            )
            _send_polo(connection, "secret", secret=secret)
            acknowledgement = _receive_polo(connection, "secret_ack")
            self.assertEqual(acknowledgement.secret_ack.secret, secret)
        finally:
            connection.close()
        server.join(timeout=5)
        self.assertFalse(server.is_alive())
        self.assertTrue(self.probe.status()["paired"])
        self.assertTrue(self.probe.client_cert_path.exists())

        replacement = PairingProbe(data_dir=self.root / "relay")
        replacement._load_trusted_phone()
        self.assertTrue(replacement._trusted_fingerprints)
        self.probe = replacement
        self.probe._active = True
        self._run_remote_command(
            RemoteKeyCode.KEYCODE_DPAD_UP,
            "DPAD_UP (SHORT)",
        )
        self._run_remote_command(
            RemoteKeyCode.KEYCODE_DPAD_DOWN,
            "DPAD_DOWN (SHORT)",
        )
        self.probe._active = False


class PersistentReceiverTest(unittest.IsolatedAsyncioTestCase):
    async def test_closing_pairing_window_keeps_receiver_available(self):
        probe = PairingProbe(pairing_port=0)
        probe._active = True

        await probe.open_pairing_window(duration=60)
        await probe.close_pairing_window()

        status = probe.status()
        self.assertTrue(status["active"])
        self.assertFalse(status["pairing_active"])
        self.assertEqual(status["seconds_remaining"], 0)

    async def test_closing_pairing_window_ends_only_in_progress_pairing(self):
        probe = PairingProbe()
        probe._active = True
        pairing_socket, pairing_peer = socket.socketpair()
        remote_socket, remote_peer = socket.socketpair()
        try:
            with probe._client_socket_lock:
                probe._client_sockets.update((pairing_socket, remote_socket))
                probe._pairing_client_sockets.add(pairing_socket)

            await probe.close_pairing_window()

            pairing_peer.settimeout(1)
            self.assertEqual(pairing_peer.recv(1), b"")
            remote_peer.sendall(b"x")
            self.assertEqual(remote_socket.recv(1), b"x")
        finally:
            for active_socket in (
                pairing_socket,
                pairing_peer,
                remote_socket,
                remote_peer,
            ):
                active_socket.close()

    async def test_closed_window_cannot_save_phone_trust(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cert_path = root / "phone.pem"
            key_path = root / "phone.key"
            _generate_identity(cert_path, key_path, "Phone")
            certificate = crypto.load_certificate(
                crypto.FILETYPE_PEM, cert_path.read_bytes()
            )
            probe = PairingProbe(data_dir=root / "probe")

            with self.assertRaisesRegex(PairingProbeError, "Pairing window closed"):
                probe._save_trusted_phone(certificate, "fingerprint")

            self.assertFalse(probe.client_cert_path.exists())

    async def test_short_key_is_forwarded_on_receiver_loop(self):
        forwarded = []

        async def send(key):
            forwarded.append(key)
            return "up"

        probe = PairingProbe(command_handler=send)
        probe._loop = asyncio.get_running_loop()
        message = RemoteMessage()
        message.remote_key_inject.key_code = RemoteKeyCode.KEYCODE_DPAD_UP
        message.remote_key_inject.direction = RemoteDirection.SHORT

        probe._handle_remote_message(message)
        for _ in range(20):
            if forwarded:
                break
            await asyncio.sleep(0.01)

        self.assertEqual(forwarded, ["DPAD_UP"])
        self.assertEqual(probe.status()["last_command"], "DPAD_UP (SHORT)")

    async def test_press_and_release_is_forwarded_exactly_once(self):
        forwarded = []

        async def send(key):
            forwarded.append(key)
            return "select"

        probe = PairingProbe(command_handler=send)
        probe._loop = asyncio.get_running_loop()
        for direction in (RemoteDirection.START_LONG, RemoteDirection.END_LONG):
            message = RemoteMessage()
            message.remote_key_inject.key_code = RemoteKeyCode.KEYCODE_DPAD_CENTER
            message.remote_key_inject.direction = direction
            probe._handle_remote_message(message)
        for _ in range(20):
            if forwarded:
                break
            await asyncio.sleep(0.01)

        self.assertEqual(forwarded, ["DPAD_CENTER"])
        self.assertEqual(probe.status()["last_command"], "DPAD_CENTER (END_LONG)")

    async def test_press_start_alone_is_not_forwarded(self):
        forwarded = []

        async def send(key):
            forwarded.append(key)
            return "up"

        probe = PairingProbe(command_handler=send)
        probe._loop = asyncio.get_running_loop()
        message = RemoteMessage()
        message.remote_key_inject.key_code = RemoteKeyCode.KEYCODE_DPAD_UP
        message.remote_key_inject.direction = RemoteDirection.START_LONG
        probe._handle_remote_message(message)
        await asyncio.sleep(0)

        self.assertEqual(forwarded, [])
        self.assertEqual(probe.status()["state"], "command_pending")

    async def test_power_press_release_is_forwarded_once(self):
        forwarded = []

        async def send(key):
            forwarded.append(key)
            return "unused"

        probe = PairingProbe(command_handler=send)
        probe._loop = asyncio.get_running_loop()
        message = RemoteMessage()
        message.remote_key_inject.key_code = RemoteKeyCode.KEYCODE_POWER
        for direction in (RemoteDirection.START_LONG, RemoteDirection.END_LONG):
            message.remote_key_inject.direction = direction
            probe._handle_remote_message(message)
        for _ in range(20):
            if forwarded:
                break
            await asyncio.sleep(0.01)

        self.assertEqual(forwarded, ["POWER"])

    async def test_text_input_is_captured_but_never_forwarded(self):
        forwarded = []

        async def send(key):
            forwarded.append(key)
            return "unused"

        probe = PairingProbe(command_handler=send)
        probe._loop = asyncio.get_running_loop()
        message = RemoteMessage()
        message.remote_ime_batch_edit.SetInParent()

        probe._handle_remote_message(message)
        await asyncio.sleep(0)

        self.assertEqual(forwarded, [])
        self.assertEqual(
            probe.status()["last_command"], "TEXT_INPUT (content withheld)"
        )


if __name__ == "__main__":
    unittest.main()
