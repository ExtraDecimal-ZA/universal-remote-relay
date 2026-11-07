"""Persistent Google TV phone receiver with bounded new pairing."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import secrets
import select
import socket
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from androidtvremote2.polo_pb2 import Options, OuterMessage
from androidtvremote2.remotemessage_pb2 import (
    RemoteDirection,
    RemoteKeyCode,
    RemoteMessage,
)
from apple_tv import AppleTVRelayError
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from OpenSSL import SSL, crypto
from zeroconf import IPVersion, ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

LOG = logging.getLogger("universal_remote_relay")
PAIRING_PORT = 6467
REMOTE_PORT = 6466
SERVICE_TYPE = "_androidtvremote2._tcp.local."
DEFAULT_PAIRING_WINDOW = 600
MAX_FRAME_SIZE = 1024 * 1024
REMOTE_FEATURES = 0b11  # Ping and key injection only.


class PairingProbeError(RuntimeError):
    """Raised when the phone receiver or bounded pairing window fails."""


@dataclass(frozen=True, slots=True)
class ProbeState:
    """Non-secret state safe to return through authenticated Home Assistant Ingress."""

    state: str = "idle"
    message: str = "Pairing test is stopped."
    pairing_code: str = ""
    client_name: str = ""
    paired: bool = False
    remote_connected: bool = False
    last_command: str = ""
    pairing_expires_at: float = 0.0


def _int_bytes(value: int) -> bytes:
    return value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")


def _public_numbers(certificate: x509.Certificate) -> tuple[int, int]:
    key = certificate.public_key()
    if not isinstance(key, rsa.RSAPublicKey):
        raise PairingProbeError("Phone and relay certificates must use RSA keys")
    numbers = key.public_numbers()
    return numbers.n, numbers.e


def pairing_secret(
    client_certificate: x509.Certificate,
    server_certificate: x509.Certificate,
    nonce: bytes,
) -> bytes:
    """Return the certificate-bound Polo pairing secret."""
    client_modulus, client_exponent = _public_numbers(client_certificate)
    server_modulus, server_exponent = _public_numbers(server_certificate)
    digest = hashlib.sha256()
    for value in (
        client_modulus,
        client_exponent,
        server_modulus,
        server_exponent,
    ):
        digest.update(_int_bytes(value))
    digest.update(nonce)
    return digest.digest()


def pairing_code(
    client_certificate: x509.Certificate,
    server_certificate: x509.Certificate,
    nonce: bytes,
) -> str:
    """Return the six-character code shown to the phone user."""
    if len(nonce) != 2:
        raise ValueError("Pairing nonce must be two bytes")
    secret = pairing_secret(client_certificate, server_certificate, nonce)
    return f"{secret[0]:02X}{nonce.hex().upper()}"


def encode_varint(value: int) -> bytes:
    """Encode a non-negative protobuf-style variable-length integer."""
    if value < 0:
        raise ValueError("Varint cannot be negative")
    encoded = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        encoded.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(encoded)


def _wait_for_tls(connection: SSL.Connection, *, write: bool, deadline: float) -> None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("TLS operation timed out")
    readable = [] if write else [connection]
    writable = [connection] if write else []
    ready_read, ready_write, _ = select.select(readable, writable, [], remaining)
    if not ready_read and not ready_write:
        raise TimeoutError("TLS operation timed out")


def _recv_exact(connection: SSL.Connection, size: int, *, deadline: float) -> bytes:
    payload = bytearray()
    while len(payload) < size:
        if not connection.pending():
            _wait_for_tls(connection, write=False, deadline=deadline)
        try:
            chunk = connection.recv(size - len(payload))
        except SSL.WantReadError:
            continue
        if not chunk:
            raise EOFError("Connection closed while reading a protocol frame")
        payload.extend(chunk)
    return bytes(payload)


def read_delimited(connection: SSL.Connection, *, timeout: int = 15) -> bytes:
    """Read one varint-length-prefixed protocol frame."""
    deadline = time.monotonic() + timeout
    length = 0
    shift = 0
    while shift < 35:
        byte = _recv_exact(connection, 1, deadline=deadline)[0]
        length |= (byte & 0x7F) << shift
        if not byte & 0x80:
            if length > MAX_FRAME_SIZE:
                raise PairingProbeError("Protocol frame is too large")
            return _recv_exact(connection, length, deadline=deadline)
        shift += 7
    raise PairingProbeError("Invalid protocol frame length")


def write_delimited(connection: SSL.Connection, payload: bytes) -> None:
    """Write one varint-length-prefixed protocol frame."""
    framed = encode_varint(len(payload)) + payload
    offset = 0
    deadline = time.monotonic() + 15
    while offset < len(framed):
        try:
            offset += connection.send(framed[offset:])
        except SSL.WantWriteError:
            _wait_for_tls(connection, write=True, deadline=deadline)


def _polo_message() -> OuterMessage:
    message = OuterMessage()
    message.protocol_version = 2
    message.status = OuterMessage.Status.STATUS_OK
    return message


def _load_pem_certificate(path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(path.read_bytes())


def _certificate_fingerprint(certificate: crypto.X509) -> str:
    der = crypto.dump_certificate(crypto.FILETYPE_ASN1, certificate)
    return hashlib.sha256(der).hexdigest()


def _generate_identity(cert_path: Path, key_path: Path, common_name: str) -> None:
    """Create a persistent self-signed RSA identity if one does not exist."""
    if cert_path.exists() and key_path.exists():
        return
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(private_key, hashes.SHA256())
    )
    key_bytes = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    cert_bytes = certificate.public_bytes(serialization.Encoding.PEM)
    key_tmp = key_path.with_name(f"{key_path.name}.tmp")
    cert_tmp = cert_path.with_name(f"{cert_path.name}.tmp")
    key_tmp.write_bytes(key_bytes)
    cert_tmp.write_bytes(cert_bytes)
    os.chmod(key_tmp, 0o600)
    os.chmod(cert_tmp, 0o600)
    key_tmp.replace(key_path)
    cert_tmp.replace(cert_path)


def _local_ipv4_address() -> str:
    """Return the IPv4 address used to reach the local network."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        return str(probe.getsockname()[0])
    finally:
        probe.close()


class PairingProbe:
    """Run a persistent trusted-phone receiver with bounded new pairing."""

    def __init__(
        self,
        *,
        data_dir: Path = Path("/data/pairing_probe"),
        receiver_name: str = "Universal Remote Relay Test",
        pairing_port: int = PAIRING_PORT,
        remote_port: int = REMOTE_PORT,
        command_handler: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.receiver_name = receiver_name
        self.pairing_port = pairing_port
        self.remote_port = remote_port
        self.command_handler = command_handler
        self.cert_path = data_dir / "relay_cert.pem"
        self.key_path = data_dir / "relay_key.pem"
        self.client_cert_path = data_dir / "paired_phone_cert.pem"
        self._state = ProbeState()
        self._state_lock = threading.Lock()
        self._session_lock = threading.Lock()
        self._trusted_fingerprints: set[str] = set()
        self._listeners: list[socket.socket] = []
        self._accept_tasks: list[asyncio.Task[None]] = []
        self._pair_listener: socket.socket | None = None
        self._pair_accept_task: asyncio.Task[None] | None = None
        self._client_tasks: set[asyncio.Task[None]] = set()
        self._client_sockets: set[socket.socket] = set()
        self._client_socket_lock = threading.Lock()
        self._pairing_expiry_task: asyncio.Task[None] | None = None
        self._zeroconf: AsyncZeroconf | None = None
        self._service_info: ServiceInfo | None = None
        self._active = False
        self._pairing_enabled = False
        self._loop: asyncio.AbstractEventLoop | None = None

    def status(self) -> dict[str, object]:
        """Return authenticated-UI state without exposing certificates or keys."""
        with self._state_lock:
            state = self._state
        remaining = (
            max(0, int(state.pairing_expires_at - time.monotonic()))
            if state.pairing_expires_at
            else 0
        )
        return {
            "state": state.state,
            "message": state.message,
            "pairing_code": state.pairing_code,
            "client_name": state.client_name,
            "paired": state.paired,
            "remote_connected": state.remote_connected,
            "last_command": state.last_command,
            "seconds_remaining": remaining,
            "active": self._active,
            "pairing_active": self._pairing_enabled,
            "receiver_name": self.receiver_name,
        }

    def _update_state(self, **changes: object) -> None:
        with self._state_lock:
            self._state = replace(self._state, **changes)

    async def start(self) -> None:
        """Start the receiver for the lifetime of the add-on."""
        if self._active:
            raise PairingProbeError("Phone remote receiver is already running")
        await asyncio.to_thread(
            _generate_identity,
            self.cert_path,
            self.key_path,
            self.receiver_name,
        )
        await asyncio.to_thread(self._load_trusted_phone)

        remote_listener = self._create_listener(self.remote_port)
        self._listeners = [remote_listener]

        try:
            address = _local_ipv4_address()
            self._zeroconf = AsyncZeroconf(ip_version=IPVersion.V4Only)
            self._service_info = ServiceInfo(
                SERVICE_TYPE,
                f"{self.receiver_name}.{SERVICE_TYPE}",
                addresses=[socket.inet_aton(address)],
                port=self.remote_port,
                properties={"fn": self.receiver_name, "md": "Home Assistant"},
                server="universal-remote-relay.local.",
            )
            # Google's service type exceeds the DNS-SD 15-byte label limit used by
            # strict validators, but it is the deployed Android TV Remote v2 type.
            await self._zeroconf.async_register_service(
                self._service_info, strict=False
            )
        except Exception:
            for listener in self._listeners:
                listener.close()
            self._listeners.clear()
            if self._zeroconf is not None:
                await self._zeroconf.async_close()
                await asyncio.sleep(0)
            self._zeroconf = None
            self._service_info = None
            raise

        self._active = True
        self._loop = asyncio.get_running_loop()
        already_paired = bool(self._trusted_fingerprints)
        self._update_state(
            state="receiver_ready",
            message=(
                "Waiting for the paired phone remote to reconnect."
                if already_paired
                else "Receiver ready. Open a pairing window to link a phone."
            ),
            pairing_code="",
            client_name="",
            paired=already_paired,
            remote_connected=False,
            last_command="",
            pairing_expires_at=0.0,
        )
        self._accept_tasks = [
            self._loop.create_task(self._accept_loop(remote_listener, pairing=False)),
        ]
        LOG.info("Persistent phone-remote receiver started on the local network")

    async def open_pairing_window(
        self, *, duration: int = DEFAULT_PAIRING_WINDOW
    ) -> None:
        """Allow one new phone pairing session for a bounded interval."""
        if not self._active:
            raise PairingProbeError("Phone remote receiver is not running")
        if self._pairing_enabled:
            raise PairingProbeError("A phone pairing window is already open")
        if not 60 <= duration <= 900:
            raise ValueError("Pairing duration must be between 60 and 900 seconds")
        pair_listener = self._create_listener(self.pairing_port)
        self._pair_listener = pair_listener
        self._listeners.append(pair_listener)
        self._pair_accept_task = asyncio.create_task(
            self._accept_loop(pair_listener, pairing=True)
        )
        self._accept_tasks.append(self._pair_accept_task)
        self._pairing_enabled = True
        self._update_state(
            state="pairing_available",
            message="Pairing is open. Select this relay in the Google TV remote.",
            pairing_code="",
            pairing_expires_at=time.monotonic() + duration,
        )
        self._pairing_expiry_task = asyncio.create_task(
            self._expire_pairing_after(duration)
        )
        LOG.info("Phone pairing window opened for %d seconds", duration)

    async def close_pairing_window(
        self, *, reason: str = "New phone pairing is closed."
    ) -> None:
        """Close new pairing without disconnecting an already trusted phone."""
        self._pairing_enabled = False
        if self._pair_listener is not None:
            self._pair_listener.close()
            with suppress(ValueError):
                self._listeners.remove(self._pair_listener)
            self._pair_listener = None
        if self._pair_accept_task is not None:
            self._pair_accept_task.cancel()
            with suppress(ValueError):
                self._accept_tasks.remove(self._pair_accept_task)
            self._pair_accept_task = None
        current = asyncio.current_task()
        if (
            self._pairing_expiry_task is not None
            and self._pairing_expiry_task is not current
        ):
            self._pairing_expiry_task.cancel()
        self._pairing_expiry_task = None
        self._update_state(
            state="receiver_ready",
            message=reason,
            pairing_code="",
            pairing_expires_at=0.0,
        )
        LOG.info("Phone pairing window closed; trusted reconnect remains available")

    async def stop(self, *, reason: str = "Phone remote receiver is stopped.") -> None:
        """Stop the persistent receiver during add-on shutdown."""
        self._active = False
        self._pairing_enabled = False
        self._pair_listener = None
        self._pair_accept_task = None
        current = asyncio.current_task()
        if (
            self._pairing_expiry_task is not None
            and self._pairing_expiry_task is not current
        ):
            self._pairing_expiry_task.cancel()
        self._pairing_expiry_task = None
        for listener in self._listeners:
            listener.close()
        self._listeners.clear()
        for task in self._accept_tasks:
            task.cancel()
        self._accept_tasks.clear()
        with self._client_socket_lock:
            client_sockets = tuple(self._client_sockets)
        for client_socket in client_sockets:
            with suppress(OSError):
                client_socket.shutdown(socket.SHUT_RDWR)
            client_socket.close()
        if self._service_info is not None and self._zeroconf is not None:
            with suppress(Exception):
                await self._zeroconf.async_unregister_service(self._service_info)
        if self._zeroconf is not None:
            await self._zeroconf.async_close()
            await asyncio.sleep(0)
        self._zeroconf = None
        self._service_info = None
        self._update_state(
            state="idle",
            message=reason,
            pairing_code="",
            remote_connected=False,
            pairing_expires_at=0.0,
        )
        LOG.info("Phone-remote receiver stopped")

    async def _expire_pairing_after(self, duration: int) -> None:
        try:
            await asyncio.sleep(duration)
            await self.close_pairing_window(
                reason="Pairing window expired; paired phones can still reconnect."
            )
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _create_listener(port: int) -> socket.socket:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("0.0.0.0", port))
        listener.listen(5)
        listener.setblocking(False)
        return listener

    async def _accept_loop(self, listener: socket.socket, *, pairing: bool) -> None:
        loop = asyncio.get_running_loop()
        try:
            while self._active:
                client_socket, address = await loop.sock_accept(listener)
                client_socket.setblocking(True)
                with self._client_socket_lock:
                    self._client_sockets.add(client_socket)
                handler = (
                    self._run_pairing_session if pairing else self._run_remote_session
                )
                task = loop.create_task(
                    asyncio.to_thread(
                        self._guard_client, handler, client_socket, address
                    )
                )
                self._client_tasks.add(task)
                task.add_done_callback(self._client_tasks.discard)
        except (asyncio.CancelledError, OSError):
            pass

    def _guard_client(self, handler, client_socket: socket.socket, address) -> None:
        try:
            handler(client_socket, address)
        except (EOFError, OSError, PairingProbeError, SSL.Error) as error:
            LOG.info("Phone-remote connection ended: %s", error)
        except Exception:
            LOG.exception("Phone-remote connection failed")
        finally:
            with self._client_socket_lock:
                self._client_sockets.discard(client_socket)
            client_socket.close()

    def _server_context(self, *, pairing: bool) -> SSL.Context:
        context = SSL.Context(SSL.TLS_SERVER_METHOD)
        context.use_certificate_file(str(self.cert_path))
        context.use_privatekey_file(str(self.key_path))
        context.check_privatekey()
        context.set_options(SSL.OP_NO_TLSv1 | SSL.OP_NO_TLSv1_1)

        def verify(_connection, certificate, _error_number, depth, _ok):
            if pairing:
                return True
            if depth != 0:
                return True
            return _certificate_fingerprint(certificate) in self._trusted_fingerprints

        context.set_verify(SSL.VERIFY_PEER | SSL.VERIFY_FAIL_IF_NO_PEER_CERT, verify)
        context.set_verify_depth(2)
        return context

    @staticmethod
    def _tls_connection(
        context: SSL.Context, client_socket: socket.socket
    ) -> SSL.Connection:
        client_socket.setblocking(False)
        connection = SSL.Connection(context, client_socket)
        connection.set_accept_state()
        deadline = time.monotonic() + 15
        while True:
            try:
                connection.do_handshake()
                break
            except SSL.WantReadError:
                _wait_for_tls(connection, write=False, deadline=deadline)
            except SSL.WantWriteError:
                _wait_for_tls(connection, write=True, deadline=deadline)
        return connection

    def _run_pairing_session(self, client_socket: socket.socket, _address) -> None:
        if not self._pairing_enabled:
            raise PairingProbeError("New phone pairing is not currently enabled")
        if not self._session_lock.acquire(blocking=False):
            raise PairingProbeError("Another phone pairing session is already active")
        connection: SSL.Connection | None = None
        try:
            connection = self._tls_connection(
                self._server_context(pairing=True), client_socket
            )
            peer = connection.get_peer_certificate()
            if peer is None:
                raise PairingProbeError("Phone did not present a pairing certificate")
            peer_der = crypto.dump_certificate(crypto.FILETYPE_ASN1, peer)
            client_certificate = x509.load_der_x509_certificate(peer_der)
            server_certificate = _load_pem_certificate(self.cert_path)

            request = self._read_polo(connection, "pairing_request")
            client_name = request.pairing_request.client_name.strip() or "Phone remote"
            self._update_state(
                state="pairing",
                message="Phone found. Negotiating a pairing code…",
                client_name=client_name,
                pairing_code="",
            )
            response = _polo_message()
            response.pairing_request_ack.server_name = self.receiver_name
            self._write_polo(connection, response)

            self._read_polo(connection, "options")
            response = _polo_message()
            response.options.preferred_role = Options.RoleType.ROLE_TYPE_OUTPUT
            encoding = response.options.output_encodings.add()
            encoding.type = Options.Encoding.ENCODING_TYPE_HEXADECIMAL
            encoding.symbol_length = 6
            self._write_polo(connection, response)

            configuration = self._read_polo(connection, "configuration")
            if (
                configuration.configuration.client_role
                != Options.RoleType.ROLE_TYPE_INPUT
                or configuration.configuration.encoding.type
                != Options.Encoding.ENCODING_TYPE_HEXADECIMAL
                or configuration.configuration.encoding.symbol_length != 6
            ):
                raise PairingProbeError("Phone proposed an unsupported pairing format")
            response = _polo_message()
            response.configuration_ack.SetInParent()
            self._write_polo(connection, response)

            nonce = secrets.token_bytes(2)
            code = pairing_code(client_certificate, server_certificate, nonce)
            expected = pairing_secret(client_certificate, server_certificate, nonce)
            self._update_state(
                state="code_ready",
                message="Enter this code in the Google TV phone remote.",
                pairing_code=code,
            )

            secret_message = self._read_polo(connection, "secret", timeout=120)
            if not hmac.compare_digest(secret_message.secret.secret, expected):
                error = _polo_message()
                error.status = OuterMessage.Status.STATUS_BAD_SECRET
                self._write_polo(connection, error)
                self._update_state(
                    state="error",
                    message="The phone rejected the pairing code. Stop and try again.",
                    pairing_code="",
                )
                return

            fingerprint = hashlib.sha256(peer_der).hexdigest()
            self._save_trusted_phone(peer, fingerprint)
            self._pairing_enabled = False
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._close_pairing_after_success)
            response = _polo_message()
            response.secret_ack.secret = expected
            self._write_polo(connection, response)
            self._update_state(
                state="paired",
                message="Phone paired permanently. Reconnects remain enabled.",
                pairing_code="",
                paired=True,
                pairing_expires_at=0.0,
            )
            LOG.info("Phone remote paired and trusted for future reconnects")
        finally:
            if connection is not None:
                with suppress(Exception):
                    connection.shutdown()
                connection.close()
            self._session_lock.release()

    @staticmethod
    def _read_polo(
        connection: SSL.Connection, expected_field: str, *, timeout: int = 15
    ) -> OuterMessage:
        message = OuterMessage()
        message.ParseFromString(read_delimited(connection, timeout=timeout))
        if not 2 <= message.protocol_version <= 9:
            raise PairingProbeError("Unsupported phone pairing protocol version")
        if message.status != OuterMessage.Status.STATUS_OK:
            raise PairingProbeError("Phone returned a pairing error")
        if not message.HasField(expected_field):
            raise PairingProbeError(f"Expected {expected_field} during phone pairing")
        return message

    @staticmethod
    def _write_polo(connection: SSL.Connection, message: OuterMessage) -> None:
        write_delimited(connection, message.SerializeToString())

    def _save_trusted_phone(self, certificate: crypto.X509, fingerprint: str) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.client_cert_path.with_name(f"{self.client_cert_path.name}.tmp")
        temporary.write_bytes(crypto.dump_certificate(crypto.FILETYPE_PEM, certificate))
        os.chmod(temporary, 0o600)
        temporary.replace(self.client_cert_path)
        self._trusted_fingerprints = {fingerprint}

    def _load_trusted_phone(self) -> None:
        if not self.client_cert_path.exists():
            self._trusted_fingerprints.clear()
            return
        certificate = crypto.load_certificate(
            crypto.FILETYPE_PEM, self.client_cert_path.read_bytes()
        )
        self._trusted_fingerprints = {_certificate_fingerprint(certificate)}

    def _close_pairing_after_success(self) -> None:
        asyncio.create_task(
            self.close_pairing_window(
                reason="Phone paired permanently; trusted reconnect remains available."
            )
        )

    def _run_remote_session(self, client_socket: socket.socket, _address) -> None:
        if not self._trusted_fingerprints:
            raise PairingProbeError("No paired phone is trusted yet")
        connection = self._tls_connection(
            self._server_context(pairing=False), client_socket
        )
        try:
            self._update_state(
                state="remote_connected",
                message="Phone remote connected. Commands will be sent to Apple TV.",
                remote_connected=True,
            )
            self._send_remote_configuration(connection)
            while self._active:
                try:
                    message = RemoteMessage()
                    message.ParseFromString(read_delimited(connection, timeout=10))
                except TimeoutError:
                    ping = RemoteMessage()
                    ping.remote_ping_request.val1 = int(time.monotonic()) & 0x7FFFFFFF
                    write_delimited(connection, ping.SerializeToString())
                    continue
                except (EOFError, SSL.Error):
                    break
                self._handle_remote_message(message)
        finally:
            with suppress(Exception):
                connection.shutdown()
            connection.close()
            self._update_state(
                state="receiver_ready",
                message="Phone disconnected; waiting for its trusted reconnect.",
                remote_connected=False,
            )

    def _send_remote_configuration(self, connection: SSL.Connection) -> None:
        message = RemoteMessage()
        message.remote_configure.code1 = REMOTE_FEATURES
        info = message.remote_configure.device_info
        info.model = self.receiver_name
        info.vendor = "Home Assistant"
        info.unknown1 = 1
        info.unknown2 = "1"
        info.package_name = "com.google.android.tv.remote.service"
        info.app_version = "0.4.0"
        write_delimited(connection, message.SerializeToString())

        active = RemoteMessage()
        active.remote_set_active.active = REMOTE_FEATURES
        write_delimited(connection, active.SerializeToString())

        started = RemoteMessage()
        started.remote_start.started = True
        write_delimited(connection, started.SerializeToString())

    def _handle_remote_message(self, message: RemoteMessage) -> None:
        if message.HasField("remote_key_inject"):
            key = RemoteKeyCode.Name(message.remote_key_inject.key_code).removeprefix(
                "KEYCODE_"
            )
            direction = RemoteDirection.Name(
                message.remote_key_inject.direction
            ).removesuffix("_DIRECTION")
            summary = f"{key} ({direction})"
            if direction != "SHORT":
                self._update_state(
                    state="command_ignored",
                    message="Long-press commands are not enabled yet.",
                    last_command=summary,
                )
                return
            self._schedule_forward(key, summary)
            return
        elif message.HasField("remote_app_link_launch_request"):
            summary = "APP_LINK (address withheld)"
        elif message.HasField("remote_ime_batch_edit"):
            summary = "TEXT_INPUT (content withheld)"
        elif message.HasField("remote_ping_response"):
            return
        else:
            return
        self._update_state(
            state="command_received",
            message="Command captured but this command type is not forwarded.",
            last_command=summary,
        )
        LOG.info("Captured non-navigation phone command type=%s", summary)

    def _schedule_forward(self, key: str, summary: str) -> None:
        if self.command_handler is None or self._loop is None:
            self._update_state(
                state="command_error",
                message="Apple TV forwarding is not configured.",
                last_command=summary,
            )
            return
        self._update_state(
            state="command_forwarding",
            message="Sending command to the selected Apple TV…",
            last_command=summary,
        )
        future = asyncio.run_coroutine_threadsafe(self.command_handler(key), self._loop)

        def completed(result) -> None:
            try:
                action = result.result()
            except AppleTVRelayError as error:
                self._update_state(
                    state="command_error",
                    message=f"Apple TV command failed: {error}",
                )
                LOG.warning(
                    "Apple TV command forwarding failed: %s", type(error).__name__
                )
            else:
                self._update_state(
                    state="command_forwarded",
                    message=f"Command sent to Apple TV ({action}).",
                )
                LOG.info("Forwarded phone remote command action=%s", action)

        future.add_done_callback(completed)
