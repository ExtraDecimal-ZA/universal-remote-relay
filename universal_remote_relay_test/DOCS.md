# Universal Remote Relay (Experimental) v0.2.2

This experimental add-on provides a private, Home Assistant-authenticated
single-target selector. The stable diagnostic add-on remains separate.

## Select one target

1. Start the add-on with **Scan once on startup** disabled.
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
selection while preserving unrelated options.

## Validate the saved target

Enable **Scan once on startup**, restart the add-on, and inspect its log. A
successful scan reports one matching device. Disable the option afterward to
return to safe idle mode.

## Security and scope

- The selector uses Home Assistant Ingress authentication.
- It uses a Supervisor-assigned dynamic port and publishes no host port.
- The web server accepts only the Supervisor ingress proxy.
- The Supervisor token is used only inside the container and is never returned
  to the browser or written to the log.
- Discovery is local and bounded.
- Apple TV pairing and commands are not implemented yet.
- Android TV is discovery-only. Pairing and commands are not implemented yet.
- Google TV receiver emulation and phone pairing are not implemented or
  claimed.

Keep **Start on boot**, **Watchdog**, and **Auto update** disabled until this
version passes the Raspberry Pi acceptance test.
