# Changelog

## 0.4.15 - Unreleased

- Drop a pending Apple TV command if the saved target's identity or pairing
  changes while connecting or before a transport retry. A Power retry cannot
  move to another selected TV, even if that TV has since been paired.
- Keep display-name and address changes compatible with the same saved identity.
- Poll phone status every five seconds while the Web UI is idle, retaining
  one-second updates during pairing or an active phone connection. Pause phone
  and Bluetooth polling in hidden pages and refresh once when they return.
- Share in-flight status reads, wait for older reads before pairing changes,
  and reuse unchanged saved-phone rows instead of rebuilding them every second.
- Add four regressions for target changes, navigation and Power retries, and
  informational name/address updates during connection.
- Preserve phone trust, Bluetooth behavior, stable v0.4.6, hostnames and ports.

## 0.4.14 — 2026-11-15

- Distinguish saved phone trust from a successfully sent final pairing
  confirmation. A failed confirmation now reports a pairing error and retry
  instructions rather than a permanent-pairing success message.
- Keep valid saved trust and existing phone connections available while
  clearing the failed pairing code and closing the new-pairing window safely.
- Add a local TLS failure regression and a Web UI check that saved trust
  cannot hide the confirmation error or prevent reopening pairing.
- Keep stable v0.4.6, Bluetooth behavior, permissions and hostnames unchanged.

## 0.4.13 — 2026-11-15

- Add versioned CHANGELOG.md files inside both add-on folders so Home
  Assistant can display each channel's release notes in its update interface.
- Validate that the newest changelog version matches each add-on's manifest.
- Keep the existing hostname and add-on IDs unchanged, preserving in-place
  updates and existing pairing data. No remote-control or pairing behavior changes.

## 0.4.12 — 2026-11-15

- Release this app's Bluetooth client after failed or cancelled pairing-agent
  registration, including an accepted registration whose reply was lost.
  A later attempt can register cleanly without a stale AlreadyExists error.
- Schedule successful phone-pairing window cleanup only after the final
  confirmation has been written and the TLS session has finished, so cleanup
  cannot close the phone socket before that acknowledgement is delivered.
- Add regression coverage for registration timeout/cancellation recovery and
  the phone acknowledgement race using a real local TLS handshake.
- Preserve stable v0.4.6, existing credentials, and private management access.

## 0.4.11 — 2026-11-15

- Restore the Bluetooth agent and owner on the current bus after a setup
  reconnect, with one bounded retry. Bind an active pairing to its original
  connection and fail promptly if that connection changes.
- Check BlueZ Bonded separately from Paired. Display saved, temporary, or
  unverified pairing accurately, and stop logging temporary pairing as a
  confirmed saved bond.
- Do not resend Play/Pause after an uncertain response: the Apple TV may have
  already applied the toggle. Tell the user to check playback before retrying.
- Add seven Python regression tests and Web UI checks for the three audit
  findings. Stable remains unchanged at v0.4.6.

## 0.4.10 — 2026-11-15

- Name the Bluetooth operation and time limit in timeout messages instead of
  returning the same pairing-mode suggestion for every request.
- After a Pair timeout, read the selected device's paired/connected state.
  Keep a confirmed pairing and complete trust/connection setup; cancel an
  unfinished request only when no pairing is confirmed.
- Log the safe timeout context and pairing-agent step without device addresses,
  PINs, passkeys, or raw provider messages. Preserve unknown state as unknown.
- Clarify that remembered devices in the list may be asleep. Record XMRM-006
  as the physical test model; compatibility and button input remain unverified.
- Stable remains pinned to the unchanged original v0.4.6 runtime.

## Stable channel promotion — 2026-11-15

- Promote the original v0.4.6 runtime to the stable `universal_remote_relay`
  add-on, replacing the v0.1.3 diagnostic-only entry. Keep experimental v0.4.9
  and its installed data separate.
- Reuse the published v0.4.6 ARM64 image; restore its unchanged source, launcher,
  dependency pins, and regression suite from commit
  `4582d427501f4ad36f8daf3dd7eff842dd25e0d1` for review and reproducibility.
- Require a manual upgrade from the diagnostic entry; stable enables the full
  LAN relay but does not request Bluetooth D-Bus access.
- Verify the original image digest, ARM64 startup, source match, and private
  ingress before publishing the channel change. Document separate pairing data
  and the requirement to run only one relay at a time.

## 0.4.9 — 2026-11-15

- Identify which Bluetooth operation was rejected and report InProgress as a
  busy operation rather than suggesting a permissions problem.
- Do not cancel another pairing or connection attempt when BlueZ rejects our
  Pair request. Cancel only an unanswered request initiated by this app.
- Release this app's discovery client after an unanswered scan; recover a busy
  discovery session with one bounded retry without resetting host Bluetooth.
- Add regression coverage for busy/rejected pairing, timeout/cancellation,
  bounded scan recovery, and preserving completed bonds after later failures.
- Physical Xiaomi pairing remains unverified; Bluetooth button forwarding is
  still not enabled.

## 0.4.8 — 2026-11-14

- Release failed/cancelled Bluetooth connections and always disconnect during
  shutdown, even if unregistering the pairing agent is interrupted.
- Recover from a dead host-bus connection and re-register the application
  agent when BlueZ restarts, without replacing the host default agent.
- Restrict pairing selections to the scanned adapter and expire them two
  minutes after discovery; reject pairing after adapter power loss.
- Reset this app's Bluetooth connection if stopping discovery fails, and
  prevent status requests from reopening Bluetooth during shutdown.
- Restore authoritative Web UI controls after request errors, keep controls
  locked during active pairing, and resume polling after temporary failures.
- Add lifecycle regression tests and executable browser-control tests to both
  GitHub workflows. Bluetooth input forwarding remains a separate hardware gate.

## 0.4.7 — 2026-11-14

- Add a bottom-of-page Bluetooth remote section with a manual 30-second scan,
  device list, and Pair with Pi action using the host BlueZ service.
- Add narrow host D-Bus access, without device mappings or full hardware access.
- Register an application-scoped no-PIN pairing agent that authorizes only the
  selected remote and never replaces the host's default agent.
- Persist Bluetooth bonds through the Pi's Bluetooth service; keep existing
  phone and Apple TV pairing files unchanged.
- Report missing adapters, host access failures, pairing failures, and paired
  versus connected state without blocking the existing relay.
- Explicitly label Bluetooth button forwarding as not enabled. Real Xiaomi
  pairing and input capture remain hardware acceptance tests.

## 0.4.6 — 2026-11-11

- Save multiple Google TV phone remotes independently and migrate the previous
  single-phone certificate without changing the relay identity.
- List paired phone remotes in the private Web UI and remove individual remotes,
  revoking their live connections while retaining all other pairings.
- Preserve an authoritative empty list so a removed legacy phone cannot return
  after restart. Save changes atomically before updating in-memory trust.
- Report connected phone counts correctly when one of several phones disconnects.
- Test two certificate/PIN pairings and reconnect after runtime replacement,
  legacy migration, selective revocation, write failure, and Web UI removal.
- Document the separate Xiaomi Bluetooth input proof of concept. Bluetooth
  remote pairing is not implemented or claimed by this release.

Physical two-phone and Xiaomi Bluetooth testing remain pending.

## 0.4.5 — 2026-11-10

- Rename the displayed add-on and container title to Universal Remote Relay.
- Retain the add-on slug, image location, configuration, and pairing data paths
  so existing installations update in place. Runtime behavior is unchanged.
- Keep experimental maturity metadata until physical acceptance is complete.

## 0.4.4 (Experimental) — 2026-11-10

- Add POWER and TV_POWER forwarding through pyatv's power interface, selecting
  sleep or wake from the reported Apple TV state. Unknown state is reported
  without guessing; retries repeat the same explicit operation.
- Discard a previous target's cached connection before controlling another
  selected Apple TV.
- Serialize Web UI target saves, reject invalid platform types cleanly, and
  return a recoverable JSON error for damaged saved-target data.
- Preserve incomplete legacy options for recovery when migration cannot finish.
- Test power sleep/wake, unknown state, pairing enforcement, transport retry,
  target changes, phone power release events, and the installed Companion
  provider's actual Wake/Sleep command mapping.

Physical S24 Ultra power-button and Apple TV sleep/wake testing remains pending.

## 0.4.3 (Experimental) — 2026-11-08

- Translate the Samsung phone's `START_LONG`/`END_LONG` navigation events into
  one Apple TV command on button release, while retaining `SHORT` support.
- Keep power, volume, microphone, text, app-link, and unknown inputs blocked.
- Move the Web UI-selected target from redundant Configuration fields into
  protected add-on data, with one-time migration of the existing selection.
- Remove the user-facing `Test` receiver name without regenerating the relay
  identity or discarding the paired phone certificate.
- Preserve the existing Apple TV credentials and phone trust files across the
  update.

Apple TV pairing, Back forwarding, phone sleep reconnect, and restart
persistence are physically verified on v0.4.2. The expanded navigation mapping
remains the v0.4.3 hardware acceptance test.

## 0.4.2 (Experimental) — 2026-11-08

- Pin `srptools` to the pyatv-compatible 1.0.1 release so Companion PIN
  pairing can complete instead of failing before the PIN reaches the Apple TV.
- Replace the removed pyatv base-exception reference with guarded provider
  boundaries, preserving a useful pairing error instead of returning HTTP 500.
- Show a clear HTTP fallback in the Web UI if an unexpected response is ever
  not JSON.
- Verify the real pyatv SRP call shape during tests.
- Verify phone trust and Apple TV credential state survive replacement of the
  add-on runtime while the protected `/data` directory is preserved, matching
  Home Assistant add-on update behavior.

Real Apple TV pairing and command forwarding remain physical acceptance tests.

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
