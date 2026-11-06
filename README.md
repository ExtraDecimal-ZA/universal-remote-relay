# Universal Remote Relay

Experimental Home Assistant add-on project targeting Raspberry Pi 3B+ (64-bit, aarch64).

## Current release: v0.1.3 — recovery diagnostic only

**This release is NOT a working Google TV or Apple TV remote relay.**
It deliberately starts an idle process, without Python, pyatv, network discovery,
remote-control actions, host networking, or listening ports.

The earlier v0.1.1 build coincided with Home Assistant becoming unresponsive on
the test Raspberry Pi. Causation has **not** been established. Do not reinstall
or run the earlier build for troubleshooting.

### What happens on startup

- Logs that diagnostic mode is active.
- Stays idle until stopped.
- Does not discover or connect to Apple TV.
- Does not advertise itself as a Google TV receiver.
- Does not install Python dependencies.

### Install and recovery precautions

1. Recover Home Assistant first; confirm it remains stable **without** this add-on.
2. Stop the previously installed add-on and disable its Start on boot setting.
3. Review Supervisor, Core, and host logs for the original crash before proceeding.
4. Make a Home Assistant backup.
5. Only then install/update to v0.1.3. Leave Start on boot disabled.
6. Start manually, read the logs, and monitor system responsiveness. Stop if it
   becomes unstable.

The repository can be added to the Home Assistant add-on store using:

`https://github.com/ExtraDecimal-ZA/universal-remote-relay`

**Do not assume the Pi is running v0.1.3 just because this repository was updated.**
The installed add-on must be updated separately.

### Architecture

The manifest currently targets only `aarch64`; a 32-bit Home Assistant OS
installation is not supported by this build.

### Code retained for later development

`app/main.py` contains earlier observation-only Apple TV discovery code using
`pyatv`, and `app/relay.py` contains a command mapping prototype. Neither
file is copied into or executed by the v0.1.3 diagnostic image. The old
`requirements.txt` is also unused by this build.

Google TV receiver discovery/pairing has **not** been implemented or verified.
Reintroduce Apple TV discovery only after isolated build tests, memory monitoring,
and stability checks on the target hardware. Google TV pairing requires separate
protocol feasibility testing.

## Current build files

- `repository.yaml`: add-on repository metadata
- `universal_remote_relay/config.yaml`: diagnostic-only add-on manifest
- `universal_remote_relay/build.yaml`: aarch64 base-image mapping
- `universal_remote_relay/Dockerfile`: minimal image, no pip installation
- `universal_remote_relay/run.sh`: diagnostic startup and idle process

## Verification status

Verified on 2026-11-06:

- Stable v0.1.3 and the last verified experimental installation (v0.1.4) were
  installed in Home Assistant and left stopped. Experimental v0.1.6 is a new
  candidate and must not be treated as installed until Home Assistant confirms it.
- Start on boot, Watchdog, and Auto update are disabled for the experimental
  add-on, and `enable_single_scan` remains `false`.
- GitHub Actions successfully validates the project and builds the experimental
  ARM64 container image.
- Six retained prototype tests and nine experimental safe-scan tests pass.

Still pending: install/update the experimental add-on to v0.1.6, confirm the
stable Apple TV identifier is configured, perform a controlled manual startup,
and observe Raspberry Pi CPU/RAM and stability. Google TV receiver discovery
and pairing remain unimplemented and unverified.

## License

MIT — see [LICENSE](LICENSE).
