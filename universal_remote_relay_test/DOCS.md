# Universal Remote Relay (Experimental) v0.4.1

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

## Pair the relay with the Apple TV

1. Save the Apple TV target through the Web UI.
2. Select **Pair with selected Apple TV**.
3. Enter the four-digit PIN shown on the television.
4. Confirm the Web UI reports that Apple TV credentials were saved.

The credentials are stored under protected add-on data and loaded again after
restart. They are never placed in the Home Assistant configuration fields or
written to the log.

## Pair or reconnect the phone remote

1. Select **Open 10-minute pairing window** if the phone is not already paired.
2. Open the Google TV remote on the Samsung S24 Ultra while it is connected to
   the same trusted local network.
3. Select **Universal Remote Relay Test**.
4. Enter the six-character code shown only in the add-on Web UI.
5. Press one D-pad button and confirm the selected Apple TV responds.
6. Let the phone sleep, wake it, and reopen the remote. It should reconnect
   without requesting another code.

The receiver advertisement and TCP 6466 remain active while the add-on runs so
the trusted phone can reconnect. TCP 6467 is opened only during the ten-minute
new-phone pairing window. No router forwarding or Internet-facing port is
required. The relay identity and paired phone's public certificate remain in
the protected `/data` directory and are never written to the log.

## Security and scope

- The selector uses Home Assistant Ingress authentication.
- It uses a Supervisor-assigned dynamic port and publishes no host port.
- The web server accepts only the Supervisor ingress proxy.
- The Supervisor token is used only inside the container and is never returned
  to the browser or written to the log.
- Discovery is local and bounded.
- The Samsung S24 Ultra has physically completed initial pairing; persistent
  reconnect after sleep remains to be verified on hardware.
- Apple TV Companion pairing and allow-listed command forwarding are
  implemented and simulated but still require the physical Apple TV test.
- Text input, app links, unknown buttons, and long-press commands are blocked.
- Complete Google TV receiver emulation is not claimed.

Keep **Start on boot**, **Watchdog**, and **Auto update** disabled until this
version passes the Raspberry Pi acceptance test.
