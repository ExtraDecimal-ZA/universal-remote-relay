"""Persistent single-target storage independent of Home Assistant options."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

TARGET_KEYS = (
    "target_platform",
    "target_name",
    "target_identifier",
    "target_address",
)
LEGACY_OPTION_KEYS = (*TARGET_KEYS, "enable_single_scan")
SUPPORTED_PLATFORMS = {"apple_tv", "android_tv"}


@dataclass(frozen=True, slots=True)
class SavedTarget:
    """One Web UI-selected target stored under protected add-on data."""

    platform: str
    name: str
    address: str
    identifier: str

    @classmethod
    def from_payload(cls, payload: object) -> SavedTarget:
        if not isinstance(payload, dict):
            raise TypeError("Selection must be an object")
        platform = payload.get("platform")
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError("platform must be apple_tv or android_tv")
        values: dict[str, str] = {}
        for key in ("name", "address", "identifier"):
            value = payload.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be a non-empty string")
            values[key] = value.strip()
        return cls(platform, values["name"], values["address"], values["identifier"])

    @classmethod
    def from_legacy_options(cls, options: dict[str, object]) -> SavedTarget:
        return cls.from_payload(
            {
                "platform": options.get("target_platform"),
                "name": options.get("target_name"),
                "address": options.get("target_address"),
                "identifier": options.get("target_identifier"),
            }
        )

    @classmethod
    def load(cls, path: Path) -> SavedTarget:
        if not path.exists():
            raise FileNotFoundError(path)
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))

    def save(self, path: Path) -> None:
        """Atomically replace the saved target without exposing credentials."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(asdict(self), stream, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def as_public_payload(self) -> dict[str, str]:
        return {
            "target_platform": self.platform,
            "target_name": self.name,
            "target_identifier": self.identifier,
            "target_address": self.address,
        }


def read_options(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Options must be an object")
    return value


def migrate_legacy_target(options_path: Path, target_path: Path) -> bool:
    """Copy a complete legacy target once, preserving existing target data."""
    if target_path.exists():
        return False
    options = read_options(options_path)
    try:
        target = SavedTarget.from_legacy_options(options)
    except (TypeError, ValueError):
        return False
    target.save(target_path)
    return True
