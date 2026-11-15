"""User-initiated host BlueZ pairing; Bluetooth button input is separate."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from functools import partial

from dbus_next import BusType, Message, MessageType, Variant
from dbus_next.aio import MessageBus

ADAPTER = "org.bluez.Adapter1"
DEVICE = "org.bluez.Device1"
AGENT_PATH = "/com/universal_remote_relay/agent"
HID_UUIDS = {
    "00001124-0000-1000-8000-00805f9b34fb",
    "00001812-0000-1000-8000-00805f9b34fb",
}
LOG = logging.getLogger("universal_remote_relay")


class BluetoothError(RuntimeError):
    """A recoverable host Bluetooth error safe to display in Ingress."""


class BluetoothConnectionChanged(BluetoothError):
    """The host bus changed during an operation bound to a pairing agent."""

    def __init__(self):
        super().__init__(
            "Pi Bluetooth connection changed. Retry pairing once it is ready."
        )


class BluetoothTimeoutError(BluetoothError):
    """A timeout identified by operation, without provider or device secrets."""

    def __init__(self, member, seconds, detail=""):
        self.member = member
        self.seconds = seconds
        guidance = (
            "Wake the remote, put it back in pairing mode, scan again, and retry once."
            if member == "Pair"
            else "The Pi Bluetooth service did not respond. Check its status before retrying."
        )
        super().__init__(
            f"Bluetooth {member} timed out after {seconds:g} seconds. {guidance}"
            + (f" {detail}" if detail else "")
        )


class BlueZRequestError(BluetoothError):
    """A rejected D-Bus method, distinct from an unanswered request."""

    def __init__(self, member, error_name):
        self.member = member
        self.error_name = error_name
        if error_name == "org.bluez.Error.InProgress":
            if member == "Pair":
                message = (
                    "The Pi is already pairing or connecting this remote. "
                    "Wait for that attempt to finish, then retry pairing."
                )
            else:
                message = (
                    f"Pi Bluetooth is busy ({member}). Wait a few seconds, then retry."
                )
        else:
            message = (
                f"Bluetooth {member} failed ({error_name}). "
                "Check pairing mode and host permissions."
            )
        super().__init__(message)


class BlueZBackend:
    def __init__(self):
        self.bus = None
        self.owner = ""
        self.selected = None
        self.agent_registered = False
        self.last_agent_event = "none"
        self.bus_lock = asyncio.Lock()

    def _disconnect(self):
        bus, self.bus = self.bus, None
        self.owner = ""
        self.selected = None
        self.agent_registered = False
        if bus is not None:
            with suppress(ValueError):
                bus.remove_message_handler(self.agent_message)
            bus.disconnect()
        return bus

    def _check_connection(self, bus):
        if self.bus is not bus or bus.connected is False:
            raise BluetoothConnectionChanged()

    async def call(
        self,
        path,
        interface,
        member,
        signature="",
        body=None,
        timeout=8,
        *,
        session_bus=None,
    ):
        async with self.bus_lock:
            if session_bus is not None:
                self._check_connection(session_bus)
            elif self.bus is not None and self.bus.connected is False:
                self._disconnect()
            if self.bus is None:
                try:
                    self.bus = MessageBus(bus_type=BusType.SYSTEM)
                    await asyncio.wait_for(self.bus.connect(), 8)
                except asyncio.CancelledError:
                    self._disconnect()
                    raise
                except Exception as error:
                    self._disconnect()
                    raise BluetoothError(
                        "Pi Bluetooth is unavailable. Check host Bluetooth and add-on D-Bus access."
                    ) from error
            bus = self.bus
        try:
            reply = await asyncio.wait_for(
                bus.call(
                    Message(
                        destination="org.bluez",
                        path=path,
                        interface=interface,
                        member=member,
                        signature=signature,
                        body=body or [],
                    )
                ),
                timeout,
            )
        except TimeoutError as error:
            LOG.warning("Bluetooth %s timed out after %g seconds", member, timeout)
            raise BluetoothTimeoutError(member, timeout) from error
        except Exception as error:
            raise BluetoothError(
                "Could not communicate with Pi Bluetooth. Restart the add-on and retry."
            ) from error
        if session_bus is not None:
            self._check_connection(session_bus)
        if reply.message_type == MessageType.ERROR:
            LOG.warning("Bluetooth %s rejected: %s", member, reply.error_name)
            raise BlueZRequestError(member, reply.error_name)
        return reply.body

    async def objects(self):
        return (
            await self.call(
                "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"
            )
        )[0]

    async def start_scan(self, adapter):
        for attempt in range(2):
            try:
                await self.call(adapter, ADAPTER, "StartDiscovery")
                return
            except BlueZRequestError as error:
                if error.error_name == "org.bluez.Error.InProgress":
                    # An unanswered StartDiscovery can leave our session active.
                    # Release our client only, never another application's scan.
                    await self.close()
                    if attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                raise
            except BaseException:
                # A timeout/cancellation does not prove BlueZ rejected the scan.
                # Release any session that may succeed after we stop waiting.
                await self.close()
                raise

    async def stop_scan(self, adapter):
        await self.call(adapter, ADAPTER, "StopDiscovery")

    def agent_message(self, message):
        if (
            message.message_type != MessageType.METHOD_CALL
            or message.path != AGENT_PATH
            or message.interface != "org.bluez.Agent1"
            or message.sender != self.owner
        ):
            return None
        if message.member in {"Release", "Cancel"}:
            if message.member == "Release":
                self.agent_registered = False
            return Message.new_method_return(message)
        selected = bool(message.body and message.body[0] == self.selected)
        if selected and message.member in {
            "RequestAuthorization",
            "AuthorizeService",
            "RequestPinCode",
            "RequestPasskey",
            "DisplayPinCode",
            "DisplayPasskey",
            "RequestConfirmation",
        }:
            self.last_agent_event = message.member
            LOG.info("Bluetooth pairing agent step=%s", message.member)
        if selected and (
            message.member == "RequestAuthorization"
            or (
                message.member == "AuthorizeService"
                and len(message.body) == 2
                and message.body[1].lower() in HID_UUIDS
            )
        ):
            return Message.new_method_return(message)
        return Message.new_error(
            message,
            "org.bluez.Error.Rejected",
            "Only the selected no-PIN remote can pair. PIN/passkey pairing is not supported.",
        )

    async def _prepare_agent(self):
        # Retry setup once if the bus changed before registration completed.
        for attempt in range(2):
            try:
                return await self._register_agent()
            except BluetoothConnectionChanged:
                if attempt:
                    raise

    async def _register_agent(self):
        # Register only our application agent, never replace the host default.
        await self.objects()
        bus = self.bus
        try:
            reply = await asyncio.wait_for(
                bus.call(
                    Message(
                        destination="org.freedesktop.DBus",
                        path="/org/freedesktop/DBus",
                        interface="org.freedesktop.DBus",
                        member="GetNameOwner",
                        signature="s",
                        body=["org.bluez"],
                    )
                ),
                8,
            )
        except TimeoutError as error:
            raise BluetoothTimeoutError("GetNameOwner", 8) from error
        self._check_connection(bus)
        if reply.message_type == MessageType.ERROR:
            raise BluetoothError("The Pi Bluetooth service is unavailable.")
        owner = reply.body[0]
        if not self.agent_registered or owner != self.owner:
            self.agent_registered = False
            self.owner = owner
            with suppress(ValueError):
                bus.remove_message_handler(self.agent_message)
            bus.add_message_handler(self.agent_message)
            try:
                await self.call(
                    "/org/bluez",
                    "org.bluez.AgentManager1",
                    "RegisterAgent",
                    "os",
                    [AGENT_PATH, "NoInputNoOutput"],
                    session_bus=bus,
                )
            except BaseException:
                with suppress(ValueError):
                    bus.remove_message_handler(self.agent_message)
                raise
            self.agent_registered = True
        return bus

    async def pair(self, path):
        bus = await self._prepare_agent()
        # Never reconnect silently halfway through a pairing session: the
        # replacement bus would not own this agent or its callback handler.
        request = partial(self.call, session_bus=bus)
        self.selected = path
        self.last_agent_event = "none"
        paired_state = None
        try:
            try:
                await request(path, DEVICE, "Pair", timeout=60)
            except BlueZRequestError:
                # BlueZ rejected our request. InProgress may belong to a
                # different application, so do not cancel its pairing.
                raise
            except BluetoothTimeoutError as error:
                # Pair includes service discovery. The bond may already exist
                # even though the method has not returned; check before cancel.
                with suppress(BluetoothError):
                    paired_state = (
                        await request(
                            path,
                            "org.freedesktop.DBus.Properties",
                            "GetAll",
                            "s",
                            [DEVICE],
                        )
                    )[0]
                paired = value(paired_state or {}, "Paired", None)
                connected = value(paired_state or {}, "Connected", None)
                paired = paired if isinstance(paired, bool) else None
                connected = connected if isinstance(connected, bool) else None
                detail = (
                    f"Host state: paired={paired}, connected={connected}, "
                    f"bonded={boolean_value(paired_state or {}, 'Bonded')}; "
                    f"agent step={self.last_agent_event}."
                )
                LOG.warning("Bluetooth Pair timeout state: %s", detail)
                if paired is not True:
                    with suppress(BluetoothError):
                        await request(path, DEVICE, "CancelPairing")
                    raise BluetoothTimeoutError(
                        "Pair", error.seconds, detail
                    ) from error
                LOG.info(
                    "Bluetooth pairing confirmed after Pair timeout; checking saved bond"
                )
            except BaseException:
                # Our accepted request may still be running after a timeout
                # or cancellation. Only this case needs CancelPairing.
                with suppress(BluetoothError):
                    await request(path, DEVICE, "CancelPairing")
                raise
            if paired_state is None:
                with suppress(BluetoothError):
                    paired_state = (
                        await request(
                            path,
                            "org.freedesktop.DBus.Properties",
                            "GetAll",
                            "s",
                            [DEVICE],
                        )
                    )[0]
            bonded = boolean_value(paired_state or {}, "Bonded")
            await request(
                path,
                "org.freedesktop.DBus.Properties",
                "Set",
                "ssv",
                [DEVICE, "Trusted", Variant("b", True)],
            )
            if value(paired_state or {}, "Connected", False) is True:
                return pairing_result(True, bonded)
            try:
                await request(path, DEVICE, "Connect", timeout=15)
            except BluetoothError:
                return pairing_result(False, bonded)
            return pairing_result(True, bonded)
        finally:
            self.selected = None

    async def close(self):
        try:
            if self.agent_registered:
                with suppress(BluetoothError):
                    await self.call(
                        "/org/bluez",
                        "org.bluez.AgentManager1",
                        "UnregisterAgent",
                        "o",
                        [AGENT_PATH],
                    )
        finally:
            bus = self._disconnect()
        if bus is not None:
            with suppress(Exception):
                await asyncio.wait_for(bus.wait_for_disconnect(), timeout=1)


def value(properties, key, default=None):
    item = properties.get(key, default)
    return item.value if isinstance(item, Variant) else item


def boolean_value(properties, key):
    result = value(properties, key)
    return result if isinstance(result, bool) else None


def pairing_result(connected, bonded):
    connection = (
        "Paired and connected to the Pi."
        if connected
        else "Paired with the Pi; connection is not ready."
    )
    persistence = (
        "Pairing saved by the Pi."
        if bonded is True
        else "This pairing is temporary; the Pi has not saved a bond."
        if bonded is False
        else "Saved pairing is unverified; check it again after a Pi restart."
    )
    return f"{connection} {persistence} Bluetooth button forwarding is not enabled yet."


class BluetoothPairing:
    def __init__(self, backend=None, scan_seconds=30):
        self.backend = backend or BlueZBackend()
        self.scan_seconds = scan_seconds
        self.scan_adapter = None
        self.scan_task = None
        self.pair_task = None
        self.seen = set()
        self.lock = asyncio.Lock()
        self.state = "idle"
        self.message = "Put your remote in Bluetooth pairing mode, then select Scan for Bluetooth devices."
        self.devices = []
        self.adapters = []
        self.closed = False
        self.selection_adapter = None
        self.selection_expires = 0

    def _selectable(self, path):
        return (
            path in self.seen
            and asyncio.get_running_loop().time() < self.selection_expires
        )

    async def status(self):
        if self.closed:
            return self._snapshot(False, "Bluetooth pairing is stopped.")
        try:
            objects = await self.backend.objects()
            self.adapters = [
                {
                    "id": path,
                    "name": value(interfaces[ADAPTER], "Alias", "Bluetooth adapter"),
                    "powered": value(interfaces[ADAPTER], "Powered", False),
                }
                for path, interfaces in objects.items()
                if ADAPTER in interfaces
            ]
            self.devices = [
                {
                    "id": path,
                    "name": value(
                        interfaces[DEVICE], "Alias", "Unnamed Bluetooth device"
                    ),
                    "address": value(interfaces[DEVICE], "Address", ""),
                    "paired": value(interfaces[DEVICE], "Paired", False),
                    "bonded": boolean_value(interfaces[DEVICE], "Bonded"),
                    "connected": value(interfaces[DEVICE], "Connected", False),
                }
                for path, interfaces in objects.items()
                if DEVICE in interfaces
            ]
            if self.scan_adapter:
                self.seen.update(
                    item["id"]
                    for item in self.devices
                    if item["id"].startswith(self.scan_adapter + "/dev_")
                )
            for device in self.devices:
                device["selectable"] = self._selectable(device["id"])
            available = any(item["powered"] for item in self.adapters)
        except (BluetoothError, OSError) as error:
            available = False
            self.devices = []
            self.adapters = []
            self.seen.clear()
            return self._snapshot(available, str(error))
        return self._snapshot(
            available,
            self.message
            if available
            else "No powered Bluetooth adapter is available on the Pi.",
        )

    def _snapshot(self, available, message):
        return {
            "available": available,
            "scanning": bool(self.scan_adapter),
            "pairing": self.pair_task is not None and not self.pair_task.done(),
            "state": self.state,
            "message": message,
            "devices": self.devices,
            "adapters": self.adapters,
            "input_forwarding": False,
        }

    async def scan(self):
        async with self.lock:
            if self.closed:
                raise BluetoothError("Bluetooth pairing is stopped.")
            if self.pair_task is not None and not self.pair_task.done():
                raise BluetoothError("Wait for Bluetooth pairing to finish.")
            await self.status()
            adapter = next((item for item in self.adapters if item["powered"]), None)
            if adapter is None:
                raise BluetoothError(
                    "No powered Bluetooth adapter is available on the Pi."
                )
            if self.scan_adapter:
                return
            self.seen.clear()
            await self.backend.start_scan(adapter["id"])
            self.scan_adapter = adapter["id"]
            self.selection_adapter = self.scan_adapter
            self.selection_expires = (
                asyncio.get_running_loop().time() + self.scan_seconds + 120
            )
            self.state = "scanning"
            self.message = f"Scanning for {self.scan_seconds:g} seconds. Select your remote from the list."
            self.scan_task = asyncio.create_task(self._expire_scan())

    async def _expire_scan(self):
        await asyncio.sleep(self.scan_seconds)
        async with self.lock:
            with suppress(BluetoothError):
                await self._stop_scan()

    async def _stop_scan(self):
        if self.scan_task is not None and self.scan_task is not asyncio.current_task():
            self.scan_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.scan_task
        self.scan_task = None
        if self.scan_adapter:
            await self.status()
            adapter, self.scan_adapter = self.scan_adapter, None
            try:
                await self.backend.stop_scan(adapter)
            except (BluetoothError, OSError):
                # Disconnecting our own D-Bus client releases only its scan
                # session, leaving Home Assistant's discovery untouched.
                await self.backend.close()
                self.seen.clear()
                self.state = "error"
                self.message = "Scan cleanup failed; the Bluetooth connection was reset. Scan again to retry."
                raise BluetoothError(self.message) from None
            else:
                self.message = "Scan finished. Select your remote, or scan again."
            self.state = "ready"

    async def stop_scan(self):
        async with self.lock:
            await self._stop_scan()

    async def pair(self, identifier):
        async with self.lock:
            if self.closed:
                raise BluetoothError("Bluetooth pairing is stopped.")
            if self.pair_task is not None and not self.pair_task.done():
                raise BluetoothError("Another Bluetooth remote is pairing.")
            await self.status()
            if not isinstance(identifier, str) or not self._selectable(identifier):
                raise BluetoothError(
                    "Scan first and select a Bluetooth device from that list."
                )
            device = next(
                (item for item in self.devices if item["id"] == identifier), None
            )
            if device is None or device["paired"]:
                raise BluetoothError("Device is missing or already paired with the Pi.")
            if not any(
                item["id"] == self.selection_adapter and item["powered"]
                for item in self.adapters
            ):
                raise BluetoothError(
                    "The scanned Bluetooth adapter is no longer powered. Scan again."
                )
            await self._stop_scan()
            self.state, self.message = "pairing", "Pairing with the selected remote…"
            self.pair_task = asyncio.create_task(self._pair(identifier))

    async def _pair(self, identifier):
        try:
            self.message = await self.backend.pair(identifier)
            self.state = "paired"
        except Exception as error:  # noqa: BLE001 - isolate host/provider failures; redact details
            LOG.warning(
                "Bluetooth pairing failed: %s",
                str(error)
                if isinstance(error, BluetoothError)
                else type(error).__name__,
            )
            self.state = "error"
            self.message = (
                str(error)
                if isinstance(error, BluetoothError)
                else "Bluetooth pairing failed. Check pairing mode and retry."
            )

    async def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            for task in (self.scan_task, self.pair_task):
                if task is not None:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
            await self.stop_scan()
        finally:
            self.seen.clear()
            self.devices = []
            self.adapters = []
            await self.backend.close()
