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

The next development step is the physical S24 Ultra discovery capture described
in the repository README.
