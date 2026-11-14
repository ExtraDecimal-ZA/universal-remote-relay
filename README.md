# Universal Remote Relay

Experimental Home Assistant add-on project for Raspberry Pi 3B+ running
64-bit `aarch64` Home Assistant OS.

## Current release: v0.4.8

v0.4.8 uses the private, Home Assistant-authenticated Web UI as the only device
discovery path and saves exactly
one target device:

1. Open the add-on Web UI.
2. Choose Apple TV or Android TV / Google TV.
3. The add-on performs one bounded local discovery scan.
4. Select one device from the single-choice list.
5. Its platform, display name, preferred identifier, and current address are
   saved immediately in protected add-on data.

There is no startup scan toggle or second validation scan. A device scan runs
only when a platform is chosen in the Web UI.

The identifier is the preferred match. Apple TV identifier stability has been
verified. The Android TV discovery identity remains provisional until pairing
is implemented and tested. Display names and addresses are informational
because either can change.

The selector uses Home Assistant Ingress with a Supervisor-assigned dynamic
port. It does not publish a host port, require a separate login, or return the
Supervisor token to the browser.

Multiple Google TV phone remotes can be paired and remembered independently.
Open a new pairing window for each phone. The Web UI lists saved phone remotes
and can remove one without affecting the others. The existing v0.4.5 pairing
is migrated automatically. All phones control the same selected Apple TV;
commands are serialized. Physical two-phone acceptance testing remains pending.

At the bottom of the Web UI, **Add Bluetooth remote** provides a manual scan
and **Pair with Pi** action. The Pi's BlueZ service stores the Bluetooth bond.
The app requests host D-Bus access; it never starts its own Bluetooth daemon or
changes the host's default pairing agent. Only no-PIN remotes are supported by
this initial pairing flow. Real Xiaomi pairing still needs hardware testing.
Bluetooth button forwarding is not enabled yet. See the
[Bluetooth test plan](BLUETOOTH_REMOTES.md) for the remaining hardware checks.

The trusted phone receiver remains advertised while the add-on is running,
so a paired phone can reconnect after sleeping. TCP 6467 is opened only during
a ten-minute new-phone pairing window; TCP 6466 remains available for a trusted
phone's command connection. The phone certificate and relay identity persist
under protected add-on data.

The Web UI also pairs the relay once with the selected Apple TV using the
on-screen four-digit Companion PIN. `pyatv` credentials persist under `/data`
across restarts and add-on image updates.
Allow-listed navigation and playback commands are forwarded using the selected
Apple TV's stable identifier; its display name may change without breaking the
selection.

## Current capability boundary

- Apple TV discovery through `pyatv`: implemented and physically verified.
- Android TV Remote v2 discovery: implemented.
- Initial Samsung S24 Ultra phone pairing: physically verified.
- Persistent phone reconnect after sleep: physically verified.
- Apple TV Companion pairing and Back command forwarding: physically verified.
- D-pad, Select, and Home release-event forwarding: implemented and simulated;
  physical verification is still required.
- Power: implemented and tested with simulated devices; physical sleep/wake
  verification is required. It toggles known Apple TV power state through
  pyatv; an unknown state produces an actionable error instead of guessing.
- Complete Google TV receiver emulation: not claimed.

The independent stable add-on remains a recovery diagnostic at v0.1.3. The
v0.4.8 stays experimental until Bluetooth pairing, multiple-phone operation, power, the expanded navigation mapping,
forwarding, resource-use, and rollback checks pass on the Pi, Samsung phone,
and Apple TV.

## Repository installation

Add this repository to the Home Assistant Add-on Store:

`https://github.com/ExtraDecimal-ZA/universal-remote-relay`

Install **Universal Remote Relay** only after both GitHub
workflows pass and the versioned ARM64 image is anonymously downloadable.

Keep Start on boot, Watchdog, and Auto update off during the acceptance test.

## Persistent relay acceptance test

1. Install and start **Universal Remote Relay v0.4.8**.
2. Open the private Web UI.
3. Confirm the saved Apple TV target, select **Pair with selected Apple TV**,
   and enter the four-digit PIN shown on the television.
4. Select **Open 10-minute pairing window** only if the Samsung phone is not
   already paired.
5. On the Samsung S24 Ultra, open the Google TV remote and select
   **Universal Remote Relay**.
6. Enter the six-character code if the phone requests new pairing.
7. Test D-pad Up/Down/Left/Right, Select, Home, and Back once each and confirm
   every button produces exactly one Apple TV action.
8. Let the phone sleep, wake it, reopen the remote, and confirm it reconnects
   without another pairing code.
9. While the Apple TV is awake, tap Power once to sleep it, wait for sleep,
   then tap Power again to wake it. Confirm the Web UI records `turn_off` and
   `turn_on`. Television power also depends on your HDMI-CEC setup.

The devices must be on the same trusted local network. TCP 6466 stays local to
the LAN for trusted phone reconnects. TCP 6467 exists only during the bounded
new-phone pairing window. No router forwarding or Internet exposure is
required.

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
