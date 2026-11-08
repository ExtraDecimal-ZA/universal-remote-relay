"""Regression checks for runtime dependency compatibility."""

import unittest

from pyatv.auth.hap_srp import SRPAuthHandler


class DependencyCompatibilityTest(unittest.TestCase):
    def test_pyatv_srp_pairing_api_is_compatible(self):
        """The installed SRP library must accept pyatv's pairing call shape."""
        handler = SRPAuthHandler()
        handler.initialize()
        handler.step1(1234)
