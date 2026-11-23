"""Regression checks for interrupted frames and bounded receiver workers."""

from __future__ import annotations

import asyncio
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from pairing_probe import (
    MAX_FRAME_SIZE,
    MAX_PAIRING_CLIENTS,
    MAX_REMOTE_CLIENTS,
    FrameReader,
    PairingProbe,
    PairingProbeError,
    encode_varint,
)


class FragmentedConnection:
    def __init__(self):
        self.data = bytearray()

    def pending(self):
        return len(self.data)

    def recv(self, size):
        data = bytes(self.data[:size])
        del self.data[:size]
        return data


class FrameReaderTest(unittest.TestCase):
    def test_partial_header_and_body_resume_without_losing_next_frame(self):
        connection = FragmentedConnection()
        reader = FrameReader()
        payload = b"x" * 130
        header = encode_varint(len(payload))
        with patch("pairing_probe._wait_for_tls", side_effect=TimeoutError):
            connection.data.extend(header[:1])
            with self.assertRaises(TimeoutError):
                reader.read(connection, timeout=1)
            connection.data.extend(header[1:] + payload[:30])
            with self.assertRaises(TimeoutError):
                reader.read(connection, timeout=1)
            connection.data.extend(payload[30:] + b"\x03end")
            self.assertEqual(reader.read(connection, timeout=1), payload)
            self.assertEqual(reader.read(connection, timeout=1), b"end")
            self.assertEqual(connection.data, b"")

    def test_oversize_and_invalid_headers_are_rejected_before_reading_body(self):
        for header in (encode_varint(MAX_FRAME_SIZE + 1), b"\x80" * 5):
            with self.subTest(header=header):
                connection = FragmentedConnection()
                connection.data.extend(header)
                with self.assertRaises(PairingProbeError):
                    FrameReader().read(connection, timeout=1)

    def test_empty_frame_does_not_consume_next_header(self):
        connection = FragmentedConnection()
        connection.data.extend(b"\x00\x01x")
        reader = FrameReader()
        self.assertEqual(reader.read(connection, timeout=1), b"")
        self.assertEqual(reader.read(connection, timeout=1), b"x")


class ReceiverCapacityTest(unittest.IsolatedAsyncioTestCase):
    async def test_excess_clients_are_closed_and_shared_io_remains_available(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = PairingProbe(data_dir=Path(directory))
            probe._active = True
            clients = []

            def wait_for_close(client, _address):
                # Real sockets keep workers occupied until stop shuts them down.
                client.recv(1)

            async def wait_until(predicate):
                async with asyncio.timeout(3):
                    while not predicate():
                        await asyncio.sleep(0.01)

            async def connect(listener):
                client = socket.socket()
                client.setblocking(False)
                clients.append(client)
                await asyncio.get_running_loop().sock_connect(
                    client, listener.getsockname()
                )
                return client

            with (
                patch.object(probe, "_run_remote_session", side_effect=wait_for_close),
                patch.object(probe, "_run_pairing_session", side_effect=wait_for_close),
            ):
                try:
                    listeners = []
                    for pairing in (False, True):
                        listener = socket.socket()
                        listener.bind(("127.0.0.1", 0))
                        listener.listen(8)
                        listener.setblocking(False)
                        listeners.append(listener)
                        probe._listeners.append(listener)
                        probe._accept_tasks.append(
                            asyncio.create_task(
                                probe._accept_loop(listener, pairing=pairing)
                            )
                        )
                    for _ in range(MAX_REMOTE_CLIENTS):
                        await connect(listeners[0])
                    for _ in range(MAX_PAIRING_CLIENTS):
                        await connect(listeners[1])
                    total = MAX_REMOTE_CLIENTS + MAX_PAIRING_CLIENTS
                    await wait_until(lambda: len(probe._client_sockets) == total)
                    for listener in listeners:
                        excess = await connect(listener)
                        self.assertEqual(
                            await asyncio.wait_for(
                                asyncio.get_running_loop().sock_recv(excess, 1), 2
                            ),
                            b"",
                        )
                    self.assertEqual(len(probe._client_sockets), total)
                    self.assertEqual(len(probe._client_tasks), total)
                    # Storage/discovery work uses this shared executor. It must
                    # remain available when all phone workers are blocked.
                    self.assertEqual(
                        await asyncio.wait_for(asyncio.to_thread(lambda: "ready"), 1),
                        "ready",
                    )
                    # A freed slot must accept a reconnect without restarting.
                    clients[0].close()
                    await wait_until(lambda: len(probe._client_sockets) == total - 1)
                    await connect(listeners[0])
                    await wait_until(lambda: len(probe._client_sockets) == total)
                finally:
                    await probe.stop()
                    for client in clients:
                        client.close()
            self.assertEqual(probe._client_sockets, set())
            self.assertEqual(probe._pairing_client_sockets, set())
            self.assertEqual(probe._client_tasks, set())
            self.assertIsNone(probe._client_executor)
