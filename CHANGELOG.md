# Changelog

## 0.4.1 (Experimental) — 2026-11-08

- Immediately terminate any in-progress new-phone pairing session when its
  Web UI pairing window is closed or expires, without interrupting a trusted
  phone's normal receiver connection.
- Bind saved Apple TV credentials to the selected device's stable identifier;
  a renamed Apple TV remains valid, while selecting a different device now
  requires its own pairing.
- Show command forwarding errors as errors in the Web UI even when the phone
  itself remains paired.
- Add regression coverage for each repaired lifecycle and status path.

Samsung phone sleep/reconnect and real Apple TV command forwarding remain
physical acceptance tests; this release does not claim either result yet.

## 0.4.0 (Experimental) — 2026-11-07

- Kept the trusted phone receiver advertised for the full add-on lifetime so a
  paired Samsung phone can reconnect after sleep or suspension.
- Limited TCP 6467 to a ten-minute new-phone pairing window while keeping TCP
  6466 available for trusted reconnects.
- Added private Web UI pairing with the selected Apple TV using `pyatv`
  Companion credentials stored under the protected add-on `/data` directory.
- Added allow-listed forwarding for navigation, menu, home, play, pause, and
  play/pause commands using the saved stable Apple TV identifier.
- Kept text input, app links, unknown buttons, and long-press commands blocked.
- Added simulated persistent-pairing, target-identity, Apple TV pairing, and
  command-forwarding tests. Physical reconnect and forwarding remain pending.

## 0.3.1 (Experimental) — 2026-11-07

- Made the private Web UI the only target discovery path.
- Removed the `enable_single_scan` configuration toggle and the complete
  startup validation scanner.
- Kept the saved platform, display name, preferred identifier, and last address
  on the Configuration tab after Web UI selection.
- Added migration cleanup so the next Web UI save removes the obsolete scan
  option from existing add-on settings.

## 0.3.0 (Experimental) — 2026-11-07

- Added a manually started, ten-minute Google TV phone-remote pairing probe.
- Added local-only Android TV Remote v2 advertisement and TLS listeners on
  ports 6467 and 6466 only while the probe is active.
- Added a Home Assistant Ingress pairing-code display, status polling, explicit
  stop control, and automatic expiry.
- Persisted the relay identity and paired phone's public certificate in the
  protected add-on data directory without logging protocol secrets.
- Added command capture with text and app-link contents withheld; Apple TV
  forwarding remains disabled.
- Added a full simulated certificate, pairing-code, trusted reconnect, and
  D-pad command round trip. Physical Samsung S24 Ultra pairing remains the next
  acceptance test and full receiver emulation is not claimed.

## 0.2.2 (Experimental) — 2026-11-06

- Made an empty target match nothing, preventing an unconfigured validation
  scan from reporting unrelated devices as successful matches.
- Restored selector controls and displayed an error when saving a target fails.
- Marked the add-on as experimental in Home Assistant metadata.
- Prevented the image workflow from overwriting an existing version tag.

## 0.2.1 (Experimental) — 2026-11-06

- Fixed the startup crash caused by calling a Bashio ingress helper that is not
  present in the pinned Home Assistant base image.
- Read the Supervisor-assigned dynamic ingress port from the authenticated
  `/addons/self/info` API instead, without logging the token or opening a host
  port.
- Added regression tests for Supervisor port lookup and invalid responses.
- Changed the release workflow to start the completed ARM64 container and
  require its selector-readiness message before publishing it.

## 0.2.0 (Experimental) — 2026-11-06

- Added a private Home Assistant Ingress selector with no published host port.
- Added a platform pre-selection for Apple TV or Android TV / Google TV.
- Added a single-choice discovered-target list; selecting one device
  immediately saves its platform, name, stable identifier, and current address
  into the add-on options.
- Added Android TV Remote v2 discovery without claiming pairing or control.
- Kept automatic discovery disabled by default and retained bounded validation
  scans on startup.
- Added friendly Home Assistant option labels and expanded unit and release
  validation for the selector.

## 0.1.7 (Experimental) — 2026-11-06

- Changed Home Assistant installation from a local Pi build to a prebuilt,
  versioned ARM64 image hosted on GitHub Container Registry.
- Added an anonymous image-download and ARM64-manifest release gate so an image
  is not offered to the Pi until Home Assistant can actually retrieve it.
- Derived the published image tag from `config.yaml` to prevent version drift.
- Added GitHub build caching and concurrency control for faster clean releases.
- Removed obsolete `build.yaml` files now that Dockerfiles define their base
  images directly.
- Recorded that the v0.1.6 update stalled at 0% without claiming it installed.

## 0.1.6 (Experimental) — 2026-11-06

- Made stable identifiers override device names, so later name changes do not
  prevent the intended Apple TV from being reported.
- Made scan timeouts, exceptions, and no-match outcomes exit unsuccessfully
  instead of appearing as a healthy idle process.
- Added current Home Assistant Docker defaults and pinned base-image releases;
  retained `build.yaml` only for compatibility with older installations.
- Expanded validation to cover both add-ons and pull-request ARM64 builds.
- Removed private device names and addresses from current documentation.

## 0.1.5 (Experimental) — 2026-11-06

- Added logging for primary and available non-secret pyatv identifiers.
- Added optional exact-name and stable-identifier discovery filters.
- Kept single-scan discovery explicitly disabled by default.
- Confirmed the intended Apple TV during a local test; its name and address are
  not persistent selectors.

## 0.1.4 (Experimental) — 2026-11-06

- Added a separate `Universal Remote Relay (Experimental)` add-on so the stable
  diagnostic installation remains untouched.
- Added an explicit `enable_single_scan` opt-in that defaults to `false`.
- When opted in, performs one bounded Apple TV discovery scan and then idles;
  it does not pair, send commands, emulate Google TV, or listen for commands.
- Added three unit tests and a dedicated ARM64 container-build workflow.
- Verified the experimental ARM64 image builds successfully in GitHub Actions.
- Installed the experimental add-on in Home Assistant but left it stopped with
  Start on boot, Watchdog, Auto update, and `enable_single_scan` disabled.

## 0.1.3 — 2026-11-05

- Replaced the earlier runtime with a minimal recovery diagnostic image.
- Removed Python dependency installation, host networking, discovery, pairing,
  command transmission, and listening ports from the running image.
- Changed startup to manual and kept the container safely idle after logging
  its diagnostic-only status.
- Preserved the earlier prototype source without copying or executing it.

## 0.1.2 — 2026-11-05

- Switched the add-on to manual boot and disabled discovery by default after
  Home Assistant became unresponsive during the earlier test period.
- The timing did not establish that the add-on caused the Home Assistant issue.
- Added an idle diagnostic mode to reduce risk while recovery was investigated.

## 0.1.1 — 2026-11-05

- Added automated YAML, dependency, unit-test, compile, and launcher checks.
- Added a focused Home Assistant installation and Gate 1 preflight checklist.
- Clarified that current Pi 3B+ installations require 64-bit `aarch64`.

## 0.1.0 — 2026-11-05

- Added a minimal Home Assistant OS add-on scaffold for Raspberry Pi 3B+ 64-bit.
- Added observation-only Apple TV discovery with `pyatv`.
- Added safe configuration, logging, and allow-listed command translation.
- Documented the unverified Google TV discovery/pairing proof of concept.
