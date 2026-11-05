# Universal Remote Relay

Universal Remote Relay is an experimental, local-only Home Assistant OS add-on
for relaying remote-control commands between ecosystems. Version 0.1 targets a
Raspberry Pi 3B+, the Google TV remote in the Google TV app on a Samsung S24
Ultra, and an Apple TV controlled through
[`pyatv`](https://pyatv.dev/).

> [!IMPORTANT]
> Google TV receiver discovery and pairing are **not implemented or verified**.
> The first milestone is a hands-on protocol feasibility test. This repository
> does not claim that a phone can currently discover or pair with the add-on.

This is an independent project. It has no dependency on HomeBridge AI
Connector, ChatGPT, a cloud service, or a subscription.

## What v0.1 contains

- A minimal Home Assistant add-on repository and container scaffold.
- Raspberry Pi 3B+ 64-bit (`raspberrypi3-64` / `aarch64`) build target.
- Local Apple TV discovery with `pyatv` and configurable scan intervals.
- A small, unit-tested mapping from remote keys to Apple TV actions.
- Structured stdout logging for the Home Assistant add-on log screen.
- No published ports, ingress page, embedded credentials, or remote access.
- A focused Google TV discovery/pairing proof-of-concept plan.

The running service is deliberately observation-only. It discovers Apple TVs
and waits; it does not start a Google TV listener or send Apple TV commands.

## Repository layout

```text
repository.yaml
universal_remote_relay/
  config.yaml
  build.yaml
  Dockerfile
  run.sh
  requirements.txt
  app/
    main.py
    relay.py
  tests/
```

## Add-on configuration

```yaml
log_level: info
apple_tv_identifier: ""
scan_interval: 300
```

- `log_level`: `debug`, `info`, `warning`, or `error`.
- `apple_tv_identifier`: optional stable identifier reported by `pyatv`.
  Leave blank to list all Apple TVs found on the local network.
- `scan_interval`: seconds between scans, from 30 to 3600.

Options are read from `/data/options.json`, which Home Assistant manages. Do
not put pairing credentials in this repository or in add-on options. A later
pairing milestone will use persistent add-on storage under `/data` and ensure
credential values are never logged.

The add-on uses host networking because Zeroconf/mDNS discovery must operate on
the same LAN as the Apple TV. It declares no public container ports and should
not be port-forwarded at the router.

Home Assistant's current supported Pi 3B+ path is the 64-bit
`raspberrypi3-64` image. This scaffold intentionally does not advertise
obsolete 32-bit `armv7` support.

## Install for the first device test

1. In Home Assistant, open **Settings → System → Repairs → ⋮ → System
   information** and confirm the architecture is `aarch64`.
2. Open **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add:

   ```text
   https://github.com/ExtraDecimal-ZA/universal-remote-relay
   ```

3. Install **Universal Remote Relay** but leave `apple_tv_identifier` blank.
4. Start the add-on and open its **Log** tab.
5. Stop if the log does not say `observation-only`, or if it contains anything
   resembling credentials. Otherwise record the intended Apple TV's stable
   identifier for Gate 1.

The Raspberry Pi, Apple TV, and phone must use the same non-guest LAN for the
later discovery test. Do not create router port-forwarding rules for this
add-on.

## Local checks

From `universal_remote_relay`:

```sh
python -m unittest discover -s tests -v
python -m compileall app
```

The final runtime image must be built on Home Assistant's builder or another
multi-architecture Docker builder. A successful desktop unit test is not a
substitute for installing on the Raspberry Pi.

## Proof-of-concept plan

### Gate 1 — Baseline the LAN and Apple TV

1. Install the add-on on the Raspberry Pi 3B+ and start it.
2. Confirm the log reports the intended architecture and `observation-only`
   status.
3. Confirm `pyatv` finds the intended Apple TV on the same LAN.
4. Copy its stable identifier into the add-on option and restart.

Success: the selected Apple TV is consistently rediscovered without secrets in
the logs.

### Gate 2 — Observe the Samsung S24 Ultra search

1. Keep the phone and Raspberry Pi on the same non-guest Wi-Fi/VLAN and disable
   client isolation for the test.
2. Start a packet capture local to the add-on host.
3. On the S24 Ultra, open Google TV remote, choose search/pair, and record the
   multicast DNS, service names, addresses, ports, and TLS/pairing sequence.
4. Compare the observation with an actual Google TV device if one is available.

Success: identify the exact discovery advertisement and initial connection
expected by the phone. A scan that shows nothing is also a useful result and
must be recorded.

### Gate 3 — Minimal receiver experiment

Only after Gate 2, implement the smallest LAN-only advertisement and pairing
state machine supported by the evidence. Bind only to the local interface,
generate device-specific keys at first start, persist them under `/data`, and
log metadata rather than key material.

Success: the S24 Ultra discovers the relay and completes pairing twice after a
clean restart. Until this occurs on the real devices, receiver compatibility is
unverified.

### Gate 4 — Relay one command through `pyatv`

Pair the add-on with the Apple TV using `pyatv` persistent storage, then relay
one harmless command (`up`) before enabling the remaining mappings.

Planned mappings:

| Incoming key | `pyatv` remote action |
| --- | --- |
| `DPAD_UP` | `up` |
| `DPAD_DOWN` | `down` |
| `DPAD_LEFT` | `left` |
| `DPAD_RIGHT` | `right` |
| `DPAD_CENTER` / `ENTER` | `select` |
| `BACK` | `menu` |
| `PLAY_PAUSE` | `play_pause` |

Success: each accepted phone command produces exactly one intended Apple TV
action, reconnects cleanly, and redacts credentials from logs.

## Security boundaries

- LAN-only; never configure router port forwarding for this add-on.
- No ingress or HTTP control endpoint in v0.1.
- No secrets in source, add-on options, exceptions, or routine logs.
- Pairing must require physical confirmation on the relevant device.
- Unknown incoming commands are rejected rather than guessed.

## License

MIT — see [LICENSE](LICENSE).
