"""User-initiated host BlueZ pairing; Bluetooth button input is separate."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

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


class BlueZBackend:
    def __init__(self):
        self.bus = None
        self.owner = ""
        self.selected = None
        self.agent_registered = False
        self.bus_lock = asyncio.Lock()

    async def call(self, path, interface, member, signature="", body=None, timeout=8):
        async with self.bus_lock:
            if self.bus is None:
                try:
                    self.bus = await asyncio.wait_for(
                        MessageBus(bus_type=BusType.SYSTEM).connect(), 8
                    )
                except Exception as error:
                    self.bus = None
                    raise BluetoothError(
                        "Pi Bluetooth is unavailable. Check host Bluetooth and add-on D-Bus access."
                    ) from error
        try:
            reply = await asyncio.wait_for(
                self.bus.call(
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
            raise BluetoothError(
                "Bluetooth request timed out. Put the remote in pairing mode and retry."
            ) from error
        except Exception as error:
            raise BluetoothError(
                "Could not communicate with Pi Bluetooth. Restart the add-on and retry."
            ) from error
        if reply.message_type == MessageType.ERROR:
            raise BluetoothError(
                f"Bluetooth request failed ({reply.error_name}). Check pairing mode and host permissions."
            )
        return reply.body

    async def objects(self):
        return (
            await self.call(
                "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"
            )
        )[0]

    async def start_scan(self, adapter):
        await self.call(adapter, ADAPTER, "StartDiscovery")

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
            return Message.new_method_return(message)
        selected = bool(message.body and message.body[0] == self.selected)
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

    async def pair(self, path):
        # Register only our application agent, never replace the host default.
        if not self.agent_registered:
            await self.objects()
            reply = await asyncio.wait_for(
                self.bus.call(
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
            if reply.message_type == MessageType.ERROR:
                raise BluetoothError("The Pi Bluetooth service is unavailable.")
            self.owner = reply.body[0]
            self.bus.add_message_handler(self.agent_message)
            try:
                await self.call(
                    "/org/bluez",
                    "org.bluez.AgentManager1",
                    "RegisterAgent",
                    "os",
                    [AGENT_PATH, "NoInputNoOutput"],
                )
            except BaseException:
                self.bus.remove_message_handler(self.agent_message)
                raise
            self.agent_registered = True
        self.selected = path
        try:
            await self.call(path, DEVICE, "Pair", timeout=60)
            await self.call(
                path,
                "org.freedesktop.DBus.Properties",
                "Set",
                "ssv",
                [DEVICE, "Trusted", Variant("b", True)],
            )
            try:
                await self.call(path, DEVICE, "Connect", timeout=15)
            except BluetoothError:
                return "Paired with the Pi; connection is not ready. Bluetooth button forwarding is not enabled yet."
            return "Paired and connected to the Pi. Bluetooth button forwarding is not enabled yet."
        except BaseException:
            with suppress(BluetoothError):
                await self.call(path, DEVICE, "CancelPairing")
            raise
        finally:
            self.selected = None

    async def close(self):
        if self.bus is not None:
            if self.agent_registered:
                with suppress(BluetoothError):
                    await self.call(
                        "/org/bluez",
                        "org.bluez.AgentManager1",
                        "UnregisterAgent",
                        "o",
                        [AGENT_PATH],
                    )
                self.bus.remove_message_handler(self.agent_message)
            self.bus.disconnect()
            with suppress(Exception):
                await self.bus.wait_for_disconnect()
            self.bus = None
            self.agent_registered = False


def value(properties, key, default=None):
    item = properties.get(key, default)
    return item.value if isinstance(item, Variant) else item


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

    async def status(self):
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
                    "connected": value(interfaces[DEVICE], "Connected", False),
                }
                for path, interfaces in objects.items()
                if DEVICE in interfaces
            ]
            if self.scan_adapter:
                self.seen.update(item["id"] for item in self.devices)
            for device in self.devices:
                device["selectable"] = device["id"] in self.seen
            available = any(item["powered"] for item in self.adapters)
        except (BluetoothError, OSError) as error:
            available = False
            self.devices = []
            self.adapters = []
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
            self.state = "scanning"
            self.message = "Scanning for 30 seconds. Select your remote from the list."
            self.scan_task = asyncio.create_task(self._expire_scan())

    async def _expire_scan(self):
        await asyncio.sleep(self.scan_seconds)
        async with self.lock:
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
                self.message = "Bluetooth scan ended; host discovery cleanup could not be confirmed."
            else:
                self.message = "Scan finished. Select your remote, or scan again."
            self.state = "ready"

    async def stop_scan(self):
        async with self.lock:
            await self._stop_scan()

    async def pair(self, identifier):
        async with self.lock:
            if self.pair_task is not None and not self.pair_task.done():
                raise BluetoothError("Another Bluetooth remote is pairing.")
            await self.status()
            if not isinstance(identifier, str) or identifier not in self.seen:
                raise BluetoothError(
                    "Scan first and select a Bluetooth device from that list."
                )
            device = next(
                (item for item in self.devices if item["id"] == identifier), None
            )
            if device is None or device["paired"]:
                raise BluetoothError("Device is missing or already paired with the Pi.")
            await self._stop_scan()
            self.state, self.message = "pairing", "Pairing with the selected remote…"
            self.pair_task = asyncio.create_task(self._pair(identifier))

    async def _pair(self, identifier):
        try:
            self.message = await self.backend.pair(identifier)
            self.state = "paired"
        except Exception as error:  # noqa: BLE001 - isolate host/provider failures; redact details
            LOG.warning("Bluetooth pairing failed: %s", type(error).__name__)
            self.state = "error"
            self.message = (
                str(error)
                if isinstance(error, BluetoothError)
                else "Bluetooth pairing failed. Check pairing mode and retry."
            )

    async def close(self):
        for task in (self.scan_task, self.pair_task):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        await self.stop_scan()
        await self.backend.close()
