"""Tests for bounded phone pairing and command capture."""

from __future__ import annotations

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
from OpenSSL import SSL
from pairing_probe import (
    PairingProbe,
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

    def test_phone_pairs_and_navigation_command_is_captured_without_forwarding(self):
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

            code = str(self.probe.status()["pairing_code"])
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

        self.probe._active = True
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
            key.remote_key_inject.key_code = RemoteKeyCode.KEYCODE_DPAD_UP
            key.remote_key_inject.direction = RemoteDirection.SHORT
            write_delimited(connection, key.SerializeToString())
            deadline = time.monotonic() + 2
            while not self.probe.status()["last_command"]:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            self.assertEqual(self.probe.status()["last_command"], "DPAD_UP (SHORT)")
        finally:
            self.probe._active = False
            connection.close()
        remote_server.join(timeout=5)
        self.assertFalse(remote_server.is_alive())


if __name__ == "__main__":
    unittest.main()
