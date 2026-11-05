# Universal Remote Relay 0.1

This experimental add-on currently scans for Apple TVs and logs what it finds.
It does not yet emulate a Google TV receiver, accept phone connections, pair
with Apple TV, or send commands.

## Configuration

- **Log level** controls add-on messages. Third-party debug logs remain disabled
  so sensitive protocol details are not accidentally printed.
- **Apple TV identifier** restricts discovery to one known device. Leave it
  blank for the first scan.
- **Scan interval** controls how often discovery runs.

Start the add-on and open its **Log** tab. A successful baseline reports at
least one Apple TV name, address, and stable identifier. Do not enter
credentials in add-on options and do not port-forward this add-on.

Before installing on a Raspberry Pi 3B+, confirm Home Assistant reports the
host architecture as `aarch64`. Current Home Assistant releases no longer
support the older 32-bit `armv7` platform.

For the first run, leave **Apple TV identifier** blank. After the intended
Apple TV appears in the log, copy only its stable identifier into the option
and restart the add-on. Gate 1 passes when that same device is rediscovered
consistently and the log remains free of credentials.

The next development step is the physical S24 Ultra discovery capture described
in the repository README.
