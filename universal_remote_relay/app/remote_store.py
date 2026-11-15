"""Atomic storage for public certificates of trusted network remotes."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from OpenSSL import crypto


def certificate_id(certificate: crypto.X509) -> str:
    return hashlib.sha256(
        crypto.dump_certificate(crypto.FILETYPE_ASN1, certificate)
    ).hexdigest()


class RemoteStore:
    def __init__(self, path: Path, legacy_path: Path) -> None:
        self.path = path
        self.legacy_path = legacy_path
        self.records: dict[str, dict[str, str]] = {}

    def load(self) -> None:
        records = {}
        if self.path.exists():
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != 1:
                raise ValueError("Invalid saved-remotes format")
            items = payload.get("remotes")
            if not isinstance(items, list):
                raise ValueError("Invalid saved-remotes list")
            for item in items:
                if not isinstance(item, dict):
                    raise TypeError("Invalid saved remote")
                name, pem = item.get("name"), item.get("certificate")
                if not isinstance(name, str) or not isinstance(pem, str):
                    raise TypeError("Invalid saved remote certificate or name")
                cert = crypto.load_certificate(crypto.FILETYPE_PEM, pem.encode())
                identifier = certificate_id(cert)
                if item.get("id") != identifier:
                    raise ValueError("Saved remote identity does not match certificate")
                records[identifier] = {
                    "id": identifier,
                    "name": name,
                    "certificate": pem,
                }
        elif self.legacy_path.exists():
            pem = self.legacy_path.read_text(encoding="utf-8")
            cert = crypto.load_certificate(crypto.FILETYPE_PEM, pem.encode())
            identifier = certificate_id(cert)
            records[identifier] = {
                "id": identifier,
                "name": "Previously paired phone",
                "certificate": pem,
            }
            self.save(records)
        self.records = records

    def save(self, records: dict[str, dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump({"version": 1, "remotes": list(records.values())}, stream)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
        self.records = records

    def add(self, certificate: crypto.X509, name: str) -> str:
        identifier = certificate_id(certificate)
        records = dict(self.records)
        records[identifier] = {
            "id": identifier,
            "name": name.strip()[:100] or "Phone remote",
            "certificate": crypto.dump_certificate(
                crypto.FILETYPE_PEM, certificate
            ).decode(),
        }
        self.save(records)
        return identifier

    def remove(self, identifier: str) -> None:
        if identifier not in self.records:
            raise KeyError(identifier)
        records = dict(self.records)
        del records[identifier]
        self.save(records)

    def public_list(self) -> list[dict[str, str]]:
        return [
            {"id": item["id"], "name": item["name"]} for item in self.records.values()
        ]
