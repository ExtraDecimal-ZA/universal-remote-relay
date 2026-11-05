import unittest

from app.relay import dispatch_command


def run_immediate(coroutine):
    """Complete a coroutine whose test double performs no blocking awaits."""

    with unittest.TestCase().assertRaises(StopIteration) as completed:
        coroutine.send(None)
    return completed.exception.value


class FakeRemote:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        async def command():
            self.calls.append(name)

        return command


class DispatchCommandTests(unittest.TestCase):
    def test_maps_navigation_command(self):
        remote = FakeRemote()

        action = run_immediate(dispatch_command(remote, "dpad_up"))

        self.assertEqual("up", action)
        self.assertEqual(["up"], remote.calls)

    def test_maps_back_to_menu(self):
        remote = FakeRemote()

        action = run_immediate(dispatch_command(remote, "BACK"))

        self.assertEqual("menu", action)
        self.assertEqual(["menu"], remote.calls)

    def test_rejects_unknown_commands(self):
        remote = FakeRemote()

        with self.assertRaisesRegex(ValueError, "Unsupported remote command"):
            run_immediate(dispatch_command(remote, "POWER"))

        self.assertEqual([], remote.calls)


if __name__ == "__main__":
    unittest.main()
