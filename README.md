# Universal Remote Relay

Experimental Home Assistant add-on project for Raspberry Pi 3B+ running
64-bit `aarch64` Home Assistant OS.

## Experimental release: v0.3.0

v0.3.0 retains the private, Home Assistant-authenticated selector for saving exactly
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

It also adds a manually started, ten-minute phone-remote pairing probe. While
the probe is active, the add-on advertises **Universal Remote Relay Test** on
the local network and listens on the Android TV Remote v2 pairing and control
ports. A six-character pairing code is shown only inside the authenticated Web
UI. After pairing, the probe can capture a navigation command for validation,
but it does not forward that command to the Apple TV. The advertisement and
listeners stop automatically or when **Stop test** is selected.

## Current capability boundary

- Apple TV discovery through `pyatv`: implemented and physically verified.
- Android TV Remote v2 discovery: implemented.
- Phone pairing and command capture: implemented and locally simulated; the
  Samsung S24 Ultra physical test is still required.
- Apple TV pairing and command dispatch: not implemented.
- Apple TV command forwarding: deliberately disabled during the pairing test.
- Complete Google TV receiver emulation: not claimed.

The independent stable add-on remains a recovery diagnostic at v0.1.3. The
v0.3.0 pairing probe stays experimental until discovery, pairing, reconnect,
command capture, expiry, resource-use, and rollback checks pass on the Pi and
Samsung phone.

## Repository installation

Add this repository to the Home Assistant Add-on Store:

`https://github.com/ExtraDecimal-ZA/universal-remote-relay`

Install **Universal Remote Relay (Experimental)** only after both GitHub
workflows pass and the versioned ARM64 image is anonymously downloadable.

Keep Start on boot, Watchdog, Auto update, and automatic startup scanning off
during the acceptance test.

## First phone pairing test

1. Install and start **Universal Remote Relay (Experimental) v0.3.0**.
2. Keep **Scan once on startup** disabled and open the private Web UI.
3. Select **Start 10-minute pairing test**.
4. On the Samsung S24 Ultra, open the Google TV remote and select
   **Universal Remote Relay Test**.
5. Enter the six-character code shown in the add-on Web UI.
6. Press one D-pad button and confirm that the Web UI reports the command as
   captured without forwarding it.
7. Select **Stop test**. The local advertisement and listeners should close.

The phone must be on the same trusted local network. The probe uses local TCP
ports 6467 for pairing and 6466 for the command session only while the test is
active. No router forwarding or Internet exposure is required.

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
