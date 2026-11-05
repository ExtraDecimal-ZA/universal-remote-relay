"""Command translation primitives for Universal Remote Relay."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

LOGGER = logging.getLogger(__name__)


class RemoteControl(Protocol):
    """Subset of the pyatv remote control interface used by v0.1."""

    async def up(self) -> None: ...
    async def down(self) -> None: ...
    async def left(self) -> None: ...
    async def right(self) -> None: ...
    async def select(self) -> None: ...
    async def menu(self) -> None: ...
    async def play_pause(self) -> None: ...


COMMAND_MAP = {
    "DPAD_UP": "up",
    "DPAD_DOWN": "down",
    "DPAD_LEFT": "left",
    "DPAD_RIGHT": "right",
    "DPAD_CENTER": "select",
    "ENTER": "select",
    "BACK": "menu",
    "PLAY_PAUSE": "play_pause",
}


async def dispatch_command(remote: RemoteControl, incoming_key: str) -> str:
    """Translate and dispatch one allow-listed command to pyatv."""

    normalized = incoming_key.strip().upper()
    action = COMMAND_MAP.get(normalized)
    if action is None:
        raise ValueError(f"Unsupported remote command: {normalized!r}")

    method: Callable[[], Awaitable[None]] = getattr(remote, action)
    LOGGER.info("Dispatching remote command key=%s action=%s", normalized, action)
    await method()
    return action
