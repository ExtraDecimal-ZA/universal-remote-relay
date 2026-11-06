# Universal Remote Relay v0.1.3

This stable recovery add-on is diagnostic-only. It logs a startup message and
then stays idle. It does not run the retained Python prototype, scan for Apple
TVs, emulate a Google TV receiver, accept phone connections, pair with Apple
TV, or send commands.

## Configuration

- **Log level** is the only runtime option in this stable diagnostic build.
  Third-party debug logs remain disabled so sensitive protocol details are not
  accidentally printed.

Start the add-on manually and open its **Log** tab. A successful diagnostic
start reports that safe diagnostic mode is active and remains idle. Do not
enter credentials in add-on options and do not port-forward this add-on.

Before installing on a Raspberry Pi 3B+, confirm Home Assistant reports the
host architecture as `aarch64`. Current Home Assistant releases no longer
support the older 32-bit `armv7` platform.

Apple TV discovery belongs to the separately installed experimental add-on.
The next development step is the controlled experimental v0.1.6 test described
in the repository README.
