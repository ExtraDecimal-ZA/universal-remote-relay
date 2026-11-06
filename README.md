# Universal Remote Relay

Experimental Home Assistant add-on project for Raspberry Pi 3B+ running
64-bit `aarch64` Home Assistant OS.

## Experimental release: v0.2.1

v0.2.1 provides a private, Home Assistant-authenticated selector for saving exactly
one target device:

1. Open the add-on Web UI.
2. Choose Apple TV or Android TV / Google TV.
3. The add-on performs one bounded local discovery scan.
4. Select one device from the single-choice list.
5. Its platform, display name, preferred identifier, and current address are saved
   immediately into the add-on options.

The identifier is the preferred match. Apple TV identifier stability has been
verified. The Android TV discovery identity remains provisional until pairing
is implemented and tested. Display names and addresses are informational
because either can change.

The selector uses Home Assistant Ingress with a Supervisor-assigned dynamic
port. It does not publish a host port, require a separate login, or return the
Supervisor token to the browser.

## Current capability boundary

- Apple TV discovery through `pyatv`: implemented and physically verified.
- Android TV Remote v2 discovery: implemented for the next physical test.
- Apple TV pairing and command dispatch: not implemented.
- Android TV pairing and command dispatch: not implemented.
- Google TV receiver emulation and Samsung phone pairing: not implemented or
  claimed.

The independent stable add-on remains a recovery diagnostic at v0.1.3. The
v0.2.1 selector stays experimental until its install, selection, restart,
resource-use, and rollback checks pass on the Pi.

## Repository installation

Add this repository to the Home Assistant Add-on Store:

`https://github.com/ExtraDecimal-ZA/universal-remote-relay`

Install **Universal Remote Relay (Experimental)** only after both GitHub
workflows pass and the versioned ARM64 image is anonymously downloadable.

Keep Start on boot, Watchdog, Auto update, and automatic startup scanning off
during the acceptance test.

## Release gate

The Raspberry Pi is the final acceptance test, not a build machine. Every
experimental version must pass:

- unit, YAML, compilation, and launcher checks;
- a prebuilt `linux/arm64` image build;
- a real startup and readiness check of that completed ARM64 image;
- an anonymous registry-download check;
- configuration and documentation consistency checks;
- basic secret and private-network-data checks.

## License

MIT — see [LICENSE](LICENSE).
