# Universal Remote Relay (Experimental) v0.1.5

This is a **separate test add-on**. The stable `Universal Remote Relay` v0.1.3 add-on remains installed independently.

## Before starting

- Make a Home Assistant backup and verify it is listed under Backups.
- Keep stable v0.1.3 installed and its Start on boot setting off.
- Keep this experimental add-on's Start on boot, Watchdog, and Auto update switches off.
- Initially leave `enable_single_scan: false` in Configuration.
- Start the experimental add-on manually; inspect logs and host CPU/RAM before enabling a scan.
- Do not run both add-ons simultaneously during the first test; stop v0.1.3 before starting the experimental instance, but do not uninstall it.

## What it does

- With `enable_single_scan: false`, runs an idle Python process without importing pyatv or scanning.
- With `enable_single_scan: true`, performs a single bounded Apple TV discovery attempt on startup, then idles.
- `target_name` optionally limits reported results to an exact device name. For
  the current test, set it to `Living Room`.
- The scan logs the matching device's primary and available non-secret
  identifiers. Copy the primary identifier into `target_identifier` for later
  scans; clear `target_name` after the identifier has been verified.
- When `target_identifier` is set, pyatv filters discovery to that stable device
  identifier instead of relying on a potentially changing name or IP address.
- Does not pair, send remote commands, advertise a Google TV receiver, or listen for remote commands.
- Uses host networking for mDNS discovery; it has not yet been runtime-tested on the Raspberry Pi 3B+.

## Stop/rollback

Stop the experimental add-on and restart stable v0.1.3 manually. If the system becomes unresponsive, recover Home Assistant first; do not enable automatic startup of the experimental add-on.
