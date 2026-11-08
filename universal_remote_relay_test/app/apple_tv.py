"""Persistent Apple TV pairing and allow-listed command forwarding."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import pyatv
from pyatv.const import Protocol
from pyatv.storage.file_storage import FileStorage

LOG = logging.getLogger("universal_remote_relay")
OPTIONS = Path("/data/options.json")
DATA_DIR = Path("/data/apple_tv")

COMMAND_MAP = {
    "DPAD_UP": "up",
    "DPAD_DOWN": "down",
    "DPAD_LEFT": "left",
    "DPAD_RIGHT": "right",
    "DPAD_CENTER": "select",
    "ENTER": "select",
    "BACK": "menu",
    "MENU": "menu",
    "HOME": "home",
    "MEDIA_PLAY_PAUSE": "play_pause",
    "MEDIA_PLAY": "play",
    "MEDIA_PAUSE": "pause",
}


class AppleTVRelayError(RuntimeError):
    """Raised when Apple TV pairing or command forwarding cannot continue."""


@dataclass(frozen=True, slots=True)
class AppleTVTarget:
    """One saved Apple TV identity selected through the private Web UI."""

    name: str
    identifier: str
    address: str

    @classmethod
    def from_options(cls, path: Path) -> AppleTVTarget:
        if not path.exists():
            raise AppleTVRelayError("Select an Apple TV in the Web UI first.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("target_platform") != "apple_tv"
        ):
            raise AppleTVRelayError("The saved target is not an Apple TV.")
        identifier = payload.get("target_identifier")
        if not isinstance(identifier, str) or not identifier.strip():
            raise AppleTVRelayError("The saved Apple TV identifier is missing.")
        name = payload.get("target_name")
        address = payload.get("target_address")
        return cls(
            name=name.strip() if isinstance(name, str) and name.strip() else "Apple TV",
            identifier=identifier.strip(),
            address=address.strip() if isinstance(address, str) else "",
        )


@dataclass(frozen=True, slots=True)
class AppleTVState:
    state: str = "not_paired"
    message: str = "Pair this relay with the selected Apple TV before forwarding."
    target_name: str = ""
    paired: bool = False
    connected: bool = False
    last_action: str = ""


class AppleTVController:
    """Own pyatv storage, pairing lifecycle, and serialized remote commands."""

    def __init__(
        self,
        *,
        options_path: Path = OPTIONS,
        data_dir: Path = DATA_DIR,
        scan_func=None,
        pair_func=None,
        connect_func=None,
        storage_factory=FileStorage,
    ) -> None:
        self.options_path = options_path
        self.data_dir = data_dir
        self.storage_path = data_dir / "pyatv.json"
        self.paired_target_path = data_dir / "paired_target.json"
        self.scan_func = scan_func or pyatv.scan
        self.pair_func = pair_func or pyatv.pair
        self.connect_func = connect_func or pyatv.connect
        self.storage_factory = storage_factory
        self._storage = None
        self._pairing = None
        self._pairing_target: AppleTVTarget | None = None
        self._connection = None
        self._state = AppleTVState()
        self._pairing_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Load persistent credentials once without scanning the network."""
        if self._storage is not None:
            return
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._storage = self.storage_factory(
            str(self.storage_path), asyncio.get_running_loop()
        )
        await self._storage.load()
        target = None
        try:
            target = AppleTVTarget.from_options(self.options_path)
        except (AppleTVRelayError, json.JSONDecodeError, OSError):
            pass
        credentials_saved = bool(
            target
            and self.storage_path.exists()
            and self._load_paired_target_identifier() == target.identifier
        )
        if credentials_saved and target is not None:
            self._state = replace(
                self._state,
                state="paired",
                message="Apple TV credentials loaded. Ready to connect on command.",
                target_name=target.name,
                paired=True,
            )
        elif target is not None:
            self._state = replace(self._state, target_name=target.name)

    def status(self) -> dict[str, object]:
        state = self._state
        try:
            target = AppleTVTarget.from_options(self.options_path)
            target_is_paired = self._is_paired_target(target)
            if state.paired and not target_is_paired:
                state = replace(
                    state,
                    state="not_paired",
                    message="Pair the selected Apple TV before forwarding commands.",
                    paired=False,
                    connected=False,
                )
            state = replace(state, target_name=target.name)
        except (AppleTVRelayError, json.JSONDecodeError, OSError):
            pass
        return asdict(state)

    async def start_pairing(self) -> None:
        """Ask the selected Apple TV to display a Companion pairing PIN."""
        await self.initialize()
        async with self._pairing_lock:
            if self._pairing is not None:
                raise AppleTVRelayError("Apple TV pairing is already in progress.")
            await self._disconnect()
            target, config = await self._scan_target()
            service = config.get_service(Protocol.Companion)
            if service is None:
                raise AppleTVRelayError(
                    "The selected Apple TV does not advertise Companion pairing."
                )
            pairing = None
            try:
                pairing = await self.pair_func(
                    config,
                    Protocol.Companion,
                    asyncio.get_running_loop(),
                    storage=self._storage,
                    name="Universal Remote Relay",
                )
                await pairing.begin()
                if not pairing.device_provides_pin:
                    raise AppleTVRelayError(
                        "The Apple TV did not provide the expected on-screen PIN flow."
                    )
            except AppleTVRelayError:
                if pairing is not None:
                    await pairing.close()
                raise
            except Exception as error:
                if pairing is not None:
                    await pairing.close()
                raise AppleTVRelayError(
                    "Apple TV pairing could not start; check the selected target."
                ) from error
            self._pairing = pairing
            self._pairing_target = target
            self._state = replace(
                self._state,
                state="waiting_for_pin",
                message="Enter the four-digit PIN shown on the Apple TV.",
                target_name=target.name,
                connected=False,
            )
            LOG.info("Apple TV pairing started for the saved target")

    async def finish_pairing(self, pin: object) -> None:
        """Finish Companion pairing and persist credentials under /data."""
        if not isinstance(pin, str) or len(pin) != 4 or not pin.isdigit():
            raise ValueError("Apple TV PIN must contain exactly four digits.")
        async with self._pairing_lock:
            pairing = self._pairing
            if pairing is None:
                raise AppleTVRelayError("Start Apple TV pairing first.")
            pairing_target = self._pairing_target
            if pairing_target is None:
                raise AppleTVRelayError("The Apple TV pairing target was lost.")
            try:
                pairing.pin(int(pin))
                await pairing.finish()
                if not pairing.has_paired:
                    raise AppleTVRelayError("Apple TV rejected the pairing request.")
                await self._storage.save()
                if self.storage_path.exists():
                    os.chmod(self.storage_path, 0o600)
                self._save_paired_target_identifier(pairing_target.identifier)
                self._state = replace(
                    self._state,
                    state="paired",
                    message="Apple TV paired. Phone commands can now be forwarded.",
                    paired=True,
                    connected=False,
                )
                LOG.info("Apple TV credentials saved in the protected add-on data")
            except AppleTVRelayError:
                self._state = replace(
                    self._state,
                    state="error",
                    message="Apple TV rejected the pairing request.",
                )
                raise
            except Exception as error:
                self._state = replace(
                    self._state,
                    state="error",
                    message="Apple TV pairing failed; verify the PIN and try again.",
                )
                raise AppleTVRelayError(
                    "Apple TV pairing failed; verify the PIN and try again."
                ) from error
            finally:
                await pairing.close()
                self._pairing = None
                self._pairing_target = None

    async def cancel_pairing(self) -> None:
        async with self._pairing_lock:
            if self._pairing is not None:
                await self._pairing.close()
                self._pairing = None
            self._pairing_target = None
            self._state = replace(
                self._state,
                state="paired" if self._state.paired else "not_paired",
                message=(
                    "Apple TV pairing cancelled; saved credentials were preserved."
                    if self._state.paired
                    else "Apple TV pairing cancelled."
                ),
            )

    async def send_key(self, key: str) -> str:
        """Forward one allow-listed Android remote key to the selected Apple TV."""
        action = COMMAND_MAP.get(key.strip().upper())
        if action is None:
            raise AppleTVRelayError(f"Unsupported remote button: {key.strip().upper()}")
        await self.initialize()
        try:
            target = AppleTVTarget.from_options(self.options_path)
        except (json.JSONDecodeError, OSError) as error:
            raise AppleTVRelayError("The saved Apple TV target is invalid.") from error
        if not self._is_paired_target(target):
            raise AppleTVRelayError(
                "Pair the selected Apple TV in the Web UI before sending commands."
            )
        async with self._command_lock:
            for attempt in range(2):
                try:
                    connection = await self._ensure_connected()
                    method = getattr(connection.remote_control, action)
                    await method()
                    self._state = replace(
                        self._state,
                        state="command_sent",
                        message=f"Sent {action} to the Apple TV.",
                        connected=True,
                        last_action=action,
                    )
                    return action
                except AppleTVRelayError:
                    raise
                except Exception as error:
                    await self._disconnect()
                    if attempt:
                        self._state = replace(
                            self._state,
                            state="error",
                            message="Apple TV command failed; check pairing and network.",
                            connected=False,
                        )
                        raise AppleTVRelayError(
                            "Could not send the command; check Apple TV pairing."
                        ) from error
            raise AssertionError("unreachable")

    async def close(self) -> None:
        await self.cancel_pairing()
        await self._disconnect()

    async def _scan_target(self):
        target = AppleTVTarget.from_options(self.options_path)
        base_options = {
            "identifier": target.identifier,
            "storage": self._storage,
        }
        configs = []
        if target.address:
            try:
                configs = await self.scan_func(
                    asyncio.get_running_loop(),
                    **base_options,
                    hosts=[target.address],
                    timeout=5,
                )
            # pyatv 0.18 exposes no common base exception for provider failures;
            # an address-specific failure must still fall back to stable identity.
            except Exception:  # noqa: BLE001
                configs = []
        if configs:
            return target, configs[0]
        try:
            configs = await self.scan_func(
                asyncio.get_running_loop(), **base_options, timeout=10
            )
        except Exception as error:
            raise AppleTVRelayError(
                "The selected Apple TV could not be reached on the local network."
            ) from error
        if not configs:
            raise AppleTVRelayError(
                "The selected Apple TV was not found at its saved identity."
            )
        return target, configs[0]

    async def _ensure_connected(self):
        if self._connection is not None:
            return self._connection
        target, config = await self._scan_target()
        try:
            self._connection = await self.connect_func(
                config,
                asyncio.get_running_loop(),
                storage=self._storage,
            )
        except Exception as error:
            raise AppleTVRelayError(
                "Apple TV connection failed; pair it in the Web UI first."
            ) from error
        self._state = replace(
            self._state,
            state="connected",
            message="Connected to the selected Apple TV.",
            target_name=target.name,
            paired=True,
            connected=True,
        )
        return self._connection

    async def _disconnect(self) -> None:
        if self._connection is None:
            return
        pending = self._connection.close()
        self._connection = None
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._state = replace(self._state, connected=False)

    def _is_paired_target(self, target: AppleTVTarget) -> bool:
        return bool(
            self.storage_path.exists()
            and self._load_paired_target_identifier() == target.identifier
        )

    def _load_paired_target_identifier(self) -> str | None:
        try:
            payload = json.loads(self.paired_target_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        identifier = payload.get("identifier") if isinstance(payload, dict) else None
        return identifier if isinstance(identifier, str) and identifier else None

    def _save_paired_target_identifier(self, identifier: str) -> None:
        """Atomically bind saved credentials to one stable Apple TV identity."""
        temporary_path = self.paired_target_path.with_suffix(".json.tmp")
        try:
            with temporary_path.open("w", encoding="utf-8") as marker:
                json.dump({"identifier": identifier}, marker)
                marker.write("\n")
                marker.flush()
                os.fsync(marker.fileno())
            os.chmod(temporary_path, 0o600)
            temporary_path.replace(self.paired_target_path)
        finally:
            temporary_path.unlink(missing_ok=True)
