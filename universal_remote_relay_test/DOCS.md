# Universal Remote Relay (Experimental) v0.4.4

This experimental add-on provides a private, Home Assistant-authenticated
single-target selector. The stable diagnostic add-on remains separate.

## Select one target

1. Start the add-on.
2. Open the add-on's **Web UI**.
3. Choose **Apple TV** or **Android TV / Google TV**.
4. Wait for the bounded local-network scan.
5. Select exactly one device from the radio-button list.

The selection is saved immediately in protected add-on data:

- `target_platform`: selected platform.
- `target_name`: display name observed during selection; informational only.
- `target_identifier`: preferred identifier used for matching. Apple TV
  stability is verified; the Android TV discovery identity remains provisional
  until pairing is implemented and tested.
- `target_address`: last observed address; informational fallback only.

Only one target can be saved. Selecting another device replaces the previous
selection. The Configuration tab now contains only the log level; target
selection and display are handled by the Web UI. An existing v0.4.2 target is
migrated automatically before the retired Configuration fields are removed.
Discovery runs only from the Web UI; there is no startup scan or duplicate
configuration toggle.

## Pair the relay with the Apple TV

1. Save the Apple TV target through the Web UI.
2. Select **Pair with selected Apple TV**.
3. Enter the four-digit PIN shown on the television.
4. Confirm the Web UI reports that Apple TV credentials were saved.

The credentials are stored under protected add-on data and loaded again after
restarts and add-on image updates. They are never placed in the Home Assistant
configuration fields or written to the log. Re-pairing is required only if the
selected physical Apple TV changes or Apple invalidates its credentials.

## Pair or reconnect the phone remote

1. Select **Open 10-minute pairing window** if the phone is not already paired.
2. Open the Google TV remote on the Samsung S24 Ultra while it is connected to
   the same trusted local network.
3. Select **Universal Remote Relay**.
4. Enter the six-character code shown only in the add-on Web UI.
5. Press one D-pad button and confirm the selected Apple TV responds.
6. Let the phone sleep, wake it, and reopen the remote. It should reconnect
   without requesting another code.

The receiver advertisement and TCP 6466 remain active while the add-on runs so
the trusted phone can reconnect. TCP 6467 is opened only during the ten-minute
new-phone pairing window. No router forwarding or Internet-facing port is
required. The relay identity and paired phone's public certificate remain in
the protected `/data` directory, survive add-on image updates, and are never
written to the log.

## Security and scope

- The selector uses Home Assistant Ingress authentication.
- It uses a Supervisor-assigned dynamic port and publishes no host port.
- The web server accepts only the Supervisor ingress proxy.
- The Supervisor token is used only inside the container and is never returned
  to the browser or written to the log.
- Discovery is local and bounded.
- The Samsung S24 Ultra has physically completed initial pairing and reconnect
  after sleep.
- Apple TV Companion pairing and Back forwarding are physically verified.
- D-pad, Select, Home, and Power forwarding require the v0.4.4 physical
  acceptance test.
- Power sleeps an awake Apple TV and wakes a sleeping Apple TV using its
  reported power state. If that state is unknown, an error is shown so you can
  retry after the status updates. TV power depends on HDMI-CEC. A transport
  retry repeats the same sleep/wake operation rather than toggling again.
- Volume, microphone, text input, app links, and unknown buttons are
  blocked.
- Complete Google TV receiver emulation is not claimed.

Keep **Start on boot**, **Watchdog**, and **Auto update** disabled until this
version passes the Raspberry Pi acceptance test.
