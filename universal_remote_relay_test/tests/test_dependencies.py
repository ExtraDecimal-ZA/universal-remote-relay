"""Regression checks for runtime dependency compatibility."""

import unittest
from unittest.mock import AsyncMock, Mock

from pyatv.auth.hap_srp import SRPAuthHandler
from pyatv.protocols.companion import CompanionPower
from pyatv.protocols.companion.api import HidCommand


class DependencyCompatibilityTest(unittest.TestCase):
    def test_pyatv_srp_pairing_api_is_compatible(self):
        """The installed SRP library must accept pyatv's pairing call shape."""
        handler = SRPAuthHandler()
        handler.initialize()
        handler.step1(1234)


class CompanionPowerTest(unittest.IsolatedAsyncioTestCase):
    async def test_installed_provider_sends_wake_and_sleep(self):
        api = Mock()
        api.hid_command = AsyncMock()
        power = CompanionPower(api)

        await power.turn_off()
        await power.turn_on()

        self.assertEqual(
            api.hid_command.await_args_list[0].args, (False, HidCommand.Sleep)
        )
        self.assertEqual(
            api.hid_command.await_args_list[1].args, (False, HidCommand.Wake)
        )
