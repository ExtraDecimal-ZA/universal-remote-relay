# Universal Remote Relay (Experimental) v0.3.1

This experimental add-on provides a private, Home Assistant-authenticated
single-target selector. The stable diagnostic add-on remains separate.

## Select one target

1. Start the add-on.
2. Open the add-on's **Web UI**.
3. Choose **Apple TV** or **Android TV / Google TV**.
4. Wait for the bounded local-network scan.
5. Select exactly one device from the radio-button list.

The selection is saved immediately into the add-on options:

- `target_platform`: selected platform.
- `target_name`: display name observed during selection; informational only.
- `target_identifier`: preferred identifier used for matching. Apple TV
  stability is verified; the Android TV discovery identity remains provisional
  until pairing is implemented and tested.
- `target_address`: last observed address; informational fallback only.

Only one target can be saved. Selecting another device replaces the previous
selection while preserving unrelated options. These four values are visible on
the add-on's Configuration tab. Discovery runs only from the Web UI; there is
no startup scan or duplicate configuration toggle.

## Pair a phone remote for the capture test

1. Open the add-on Web UI and select **Start 10-minute pairing test**.
2. Open the Google TV remote on the Samsung S24 Ultra while it is connected to
   the same trusted local network.
3. Select **Universal Remote Relay Test**.
4. Enter the six-character code shown only in the add-on Web UI.
5. Press one D-pad button. The Web UI should show the captured command and
   confirm that nothing was forwarded to the Apple TV.
6. Select **Stop test**. The local advertisement and listeners also stop
   automatically after ten minutes.

The probe uses Android TV Remote v2 TCP ports 6467 and 6466 only while active.
It does not require router forwarding or an Internet-facing port. The relay's
private identity and the paired phone's public certificate are stored under
the add-on's protected `/data` directory and are never written to the log.

## Security and scope

- The selector uses Home Assistant Ingress authentication.
- It uses a Supervisor-assigned dynamic port and publishes no host port.
- The web server accepts only the Supervisor ingress proxy.
- The Supervisor token is used only inside the container and is never returned
  to the browser or written to the log.
- Discovery is local and bounded.
- Apple TV pairing and commands are not implemented yet.
- Phone pairing and local command capture are experimental and locally
  simulated; physical Samsung S24 Ultra pairing is not yet claimed.
- Apple TV forwarding is disabled during the phone pairing test.
- Complete Google TV receiver emulation is not claimed.

Keep **Start on boot**, **Watchdog**, and **Auto update** disabled until this
version passes the Raspberry Pi acceptance test.
