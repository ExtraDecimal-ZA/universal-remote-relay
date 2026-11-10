"""Persistent multi-remote trust, migration, and revocation regression tests."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from OpenSSL import crypto
from pairing_probe import _generate_identity
from remote_store import RemoteStore, certificate_id


class RemoteStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.path = self.root / "remotes.json"
        self.legacy = self.root / "paired_phone_cert.pem"
        self.store = RemoteStore(self.path, self.legacy)
        self.certs = []
        for index in range(2):
            cert = self.root / f"phone{index}.pem"
            _generate_identity(cert, self.root / f"phone{index}.key", f"Phone {index}")
            self.certs.append(
                crypto.load_certificate(crypto.FILETYPE_PEM, cert.read_bytes())
            )

    def tearDown(self):
        self.directory.cleanup()

    def test_two_remotes_survive_reload_without_replacing_each_other(self):
        ids = {self.store.add(cert, f"Phone {i}") for i, cert in enumerate(self.certs)}
        replacement = RemoteStore(self.path, self.legacy)
        replacement.load()
        self.assertEqual(set(replacement.records), ids)
        self.assertEqual(len(replacement.public_list()), 2)
        self.assertNotIn("certificate", replacement.public_list()[0])

    def test_repairing_same_remote_does_not_duplicate_it(self):
        self.store.add(self.certs[0], "Old name")
        self.store.add(self.certs[0], "New name")
        self.assertEqual(len(self.store.records), 1)
        self.assertEqual(self.store.public_list()[0]["name"], "New name")

    def test_legacy_phone_is_migrated_and_not_resurrected_after_removal(self):
        self.legacy.write_bytes(
            crypto.dump_certificate(crypto.FILETYPE_PEM, self.certs[0])
        )
        self.store.load()
        identifier = certificate_id(self.certs[0])
        self.assertIn(identifier, self.store.records)
        self.store.remove(identifier)
        replacement = RemoteStore(self.path, self.legacy)
        replacement.load()
        self.assertEqual(replacement.records, {})

    def test_removal_preserves_other_remote_after_restart(self):
        first = self.store.add(self.certs[0], "One")
        second = self.store.add(self.certs[1], "Two")
        self.store.remove(first)
        self.store.load()
        self.assertEqual(set(self.store.records), {second})

    def test_failed_write_preserves_previous_store_and_memory(self):
        first = self.store.add(self.certs[0], "One")
        before = self.path.read_bytes()
        with (
            patch("remote_store.os.fsync", side_effect=OSError("disk failure")),
            self.assertRaises(OSError),
        ):
            self.store.add(self.certs[1], "Two")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(set(self.store.records), {first})

    def test_corrupt_store_does_not_fall_back_to_revoked_legacy_trust(self):
        self.legacy.write_bytes(
            crypto.dump_certificate(crypto.FILETYPE_PEM, self.certs[0])
        )
        self.path.write_text("broken", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            self.store.load()
        self.assertEqual(self.store.records, {})
