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
- `universal_remote_relay/Dockerfile`: minimal image, no pip installation
- `universal_remote_relay/run.sh`: diagnostic startup and idle process

## Verification status

Verified on 2026-11-06:

- Stable v0.1.3 and experimental v0.1.4 remain the last confirmed installations.
  The v0.1.6 update stalled at `Installing (0%)` while Home Assistant and the
  Supervisor remained reachable; it was not accepted as installed.
- Start on boot, Watchdog, and Auto update are disabled for the experimental
  add-on, and `enable_single_scan` remains `false`.
- GitHub Actions validates the project and builds the experimental ARM64 image.
  Starting with v0.1.7, it must also publish the image and prove an anonymous
  ARM64 download before the Pi installation is allowed.
- Six retained prototype tests and nine experimental safe-scan tests pass.

Still pending: complete the v0.1.7 prebuilt-image release gate, then install it
without a local Pi build, confirm the stable Apple TV identifier, perform a
controlled manual startup, and observe Raspberry Pi CPU/RAM and stability.
Google TV receiver discovery and pairing remain unimplemented and unverified.

## Pi installation policy

The Raspberry Pi is the final hardware acceptance test, not a container build
machine. A new experimental version must not be installed until its checks,
versioned ARM64 image publication, anonymous pull test, documentation, and
rollback instructions are complete. The add-on remains manual-start and
discovery remains opt-in for the first hardware run.

## License

MIT — see [LICENSE](LICENSE).
