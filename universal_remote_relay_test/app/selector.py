"""Home Assistant Ingress UI for selecting exactly one discovered target."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from aiohttp import ClientSession, ClientTimeout, web
from discovery import discover_devices, normalize_platform
from pairing_probe import PairingProbeError

LOG = logging.getLogger("universal_remote_relay")
OPTIONS = Path("/data/options.json")
SUPERVISOR_REMOTE = "172.30.32.2"
ALLOWED_REMOTE_KEY = web.AppKey("allowed_remote", str | None)
OPTIONS_PATH_KEY = web.AppKey("options_path", Path)
DISCOVER_FUNC_KEY = web.AppKey("discover_func", object)
SAVE_FUNC_KEY = web.AppKey("save_func", object)
DISCOVERED_KEY = web.AppKey("discovered", dict)
PAIRING_PROBE_KEY = web.AppKey("pairing_probe", object)

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Universal Remote Relay</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
    body { margin: 0; padding: 24px; background: #101e24; color: #e8f1f5; }
    main { max-width: 720px; margin: auto; }
    section { background: #172a33; border: 1px solid #294653; border-radius: 12px; padding: 18px; margin-bottom: 16px; }
    h1, h2 { margin-top: 0; }
    label { display: block; margin: 10px 0 6px; font-weight: 650; }
    select { width: 100%; padding: 10px; border-radius: 8px; }
    button { padding: 10px 14px; margin: 6px 8px 6px 0; border: 0; border-radius: 8px; cursor: pointer; }
    button:disabled { cursor: wait; opacity: .65; }
    .target { display: flex; gap: 12px; padding: 12px; margin-top: 10px; border: 1px solid #3b5966; border-radius: 9px; cursor: pointer; }
    .target:has(input:checked) { border-color: #03a9f4; background: #173b4d; }
    .muted { color: #aac0ca; }
    .ok { color: #72d572; }
    .error { color: #ff8a80; }
    .code { font: 700 2rem ui-monospace, monospace; letter-spacing: .18em; margin: 12px 0; }
    code { word-break: break-all; }
  </style>
</head>
<body><main>
  <h1>Universal Remote Relay</h1>
  <section>
    <h2>Saved target</h2>
    <div id="saved" class="muted">Loading configuration…</div>
  </section>
  <section>
    <h2>Pre-select one target</h2>
    <p class="muted">Choose a platform. The relay scans once and shows a single-choice target list. Selecting one target saves it immediately.</p>
    <label for="platform">Device type</label>
    <select id="platform">
      <option value="">Choose Apple TV or Android TV…</option>
      <option value="apple_tv">Apple TV</option>
      <option value="android_tv">Android TV / Google TV</option>
    </select>
    <div id="status" class="muted"></div>
    <div id="targets"></div>
  </section>
  <section>
    <h2>Phone remote pairing test</h2>
    <p class="muted">Temporarily advertises <strong>Universal Remote Relay Test</strong> on your local network. Pairing and command capture stop automatically after ten minutes. Captured commands are not forwarded to the Apple TV.</p>
    <button id="pair-start" type="button">Start 10-minute pairing test</button>
    <button id="pair-stop" type="button" disabled>Stop test</button>
    <div id="pair-status" class="muted">Pairing test is stopped.</div>
    <div id="pair-code" class="code" hidden></div>
    <div id="pair-detail" class="muted"></div>
  </section>
  <p class="muted">Google TV receiver pairing remains experimental until this physical phone test passes. Apple TV forwarding is disabled.</p>
</main>
<script>
const platform = document.getElementById('platform');
const status = document.getElementById('status');
const targets = document.getElementById('targets');
const saved = document.getElementById('saved');
const pairStart = document.getElementById('pair-start');
const pairStop = document.getElementById('pair-stop');
const pairStatus = document.getElementById('pair-status');
const pairCode = document.getElementById('pair-code');
const pairDetail = document.getElementById('pair-detail');
let pairingPoll = null;

function platformName(value) {
  if (value === 'apple_tv') return 'Apple TV';
  if (value === 'android_tv') return 'Android TV / Google TV';
  return 'Unknown platform';
}

function showSaved(config) {
  if (!config.target_identifier) {
    saved.textContent = 'No target has been selected.';
    return;
  }
  saved.replaceChildren();
  const title = document.createElement('strong');
  title.textContent = config.target_name || 'Saved device';
  const detail = document.createElement('div');
  detail.className = 'muted';
  detail.textContent = `${platformName(config.target_platform)} · ${config.target_address || 'address unknown'} · ${config.target_identifier}`;
  saved.append(title, detail);
}

async function loadConfig() {
  const response = await fetch('api/config');
  if (!response.ok) throw new Error('Could not read the saved target.');
  showSaved(await response.json());
}

function renderTargets(devices) {
  targets.replaceChildren();
  if (!devices.length) {
    status.textContent = 'No compatible devices were found.';
    return;
  }
  status.textContent = `Found ${devices.length} device(s). Select exactly one target:`;
  for (const device of devices) {
    const label = document.createElement('label');
    label.className = 'target';
    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'target';
    radio.value = device.identifier;
    radio.addEventListener('change', () => saveTarget(device, radio).catch(showError));
    const text = document.createElement('span');
    const name = document.createElement('strong');
    name.textContent = device.name;
    const detail = document.createElement('div');
    detail.className = 'muted';
    detail.textContent = `${device.address} · ${device.identifier}`;
    text.append(name, detail);
    label.append(radio, text);
    targets.append(label);
  }
}

async function scan() {
  targets.replaceChildren();
  if (!platform.value) {
    status.textContent = '';
    return;
  }
  status.className = 'muted';
  status.textContent = `Scanning for ${platformName(platform.value)} devices…`;
  const response = await fetch('api/discover', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({platform: platform.value})
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'Discovery failed.');
  renderTargets(body.devices);
}

async function saveTarget(device, radio) {
  for (const item of targets.querySelectorAll('input')) item.disabled = true;
  status.className = 'muted';
  status.textContent = `Saving ${device.name}…`;
  try {
    const response = await fetch('api/select', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(device)
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || 'Could not save the selected target.');
    showSaved(body.options);
    status.className = 'ok';
    status.textContent = 'Target saved. The Configuration tab now contains this device information.';
  } catch (error) {
    radio.checked = false;
    for (const item of targets.querySelectorAll('input')) item.disabled = false;
    throw error;
  }
}

platform.addEventListener('change', () => scan().catch(showError));
function showError(error) { status.className = 'error'; status.textContent = error.message; }

function showPairing(pairing) {
  pairStart.disabled = pairing.active;
  pairStop.disabled = !pairing.active;
  pairStatus.className = pairing.state === 'error' ? 'error' : pairing.paired ? 'ok' : 'muted';
  pairStatus.textContent = pairing.message;
  pairCode.hidden = !pairing.pairing_code;
  pairCode.textContent = pairing.pairing_code || '';
  const details = [];
  if (pairing.client_name) details.push(`Phone: ${pairing.client_name}`);
  if (pairing.last_command) details.push(`Last command: ${pairing.last_command}`);
  if (pairing.active) details.push(`${pairing.seconds_remaining}s remaining`);
  pairDetail.textContent = details.join(' · ');
  if (pairing.active && !pairingPoll) pairingPoll = setInterval(loadPairing, 1000);
  if (!pairing.active && pairingPoll) { clearInterval(pairingPoll); pairingPoll = null; }
}

async function pairingRequest(path) {
  pairStart.disabled = true;
  pairStop.disabled = true;
  const response = await fetch(path, {method: 'POST'});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'Pairing test request failed.');
  showPairing(body);
}

async function loadPairing() {
  const response = await fetch('api/pairing/status');
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'Could not read pairing status.');
  showPairing(body);
}

pairStart.addEventListener('click', () => pairingRequest('api/pairing/start').catch(showPairingError));
pairStop.addEventListener('click', () => pairingRequest('api/pairing/stop').catch(showPairingError));
function showPairingError(error) {
  pairStatus.className = 'error';
  pairStatus.textContent = error.message;
  loadPairing().catch(() => { pairStart.disabled = false; pairStop.disabled = true; });
}
loadConfig().catch(showError);
loadPairing().catch(showPairingError);
</script></body></html>"""


@dataclass(frozen=True, slots=True)
class Selection:
    platform: str
    name: str
    address: str
    identifier: str

    @classmethod
    def from_payload(cls, payload: object) -> Selection:
        if not isinstance(payload, dict):
            raise TypeError("Selection must be an object")
        platform = normalize_platform(payload.get("platform"))
        values: dict[str, str] = {}
        for key in ("name", "address", "identifier"):
            value = payload.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be a non-empty string")
            values[key] = value.strip()
        return cls(platform, values["name"], values["address"], values["identifier"])


def read_options(path: Path = OPTIONS) -> dict[str, object]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Options must be an object")
    return value


def options_with_selection(
    options: dict[str, object], selection: Selection
) -> dict[str, object]:
    updated = dict(options)
    updated.pop("enable_single_scan", None)
    updated.update(
        target_platform=selection.platform,
        target_name=selection.name,
        target_identifier=selection.identifier,
        target_address=selection.address,
    )
    return updated


def public_target_options(options: dict[str, object]) -> dict[str, str]:
    return {
        "target_platform": str(options.get("target_platform", "apple_tv")),
        "target_name": str(options.get("target_name", "")),
        "target_identifier": str(options.get("target_identifier", "")),
        "target_address": str(options.get("target_address", "")),
    }


async def save_supervisor_options(options: dict[str, object]) -> None:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise RuntimeError("Supervisor token is unavailable")
    url = os.environ.get("SUPERVISOR_URL", "http://supervisor") + "/addons/self/options"
    timeout = ClientTimeout(total=15)
    async with (
        ClientSession(timeout=timeout) as session,
        session.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json={"options": options},
        ) as response,
    ):
        if response.status >= 300:
            raise RuntimeError(
                f"Supervisor rejected the configuration ({response.status})"
            )


@web.middleware
async def supervisor_only(request: web.Request, handler):
    allowed_remote = request.app[ALLOWED_REMOTE_KEY]
    if allowed_remote is not None and request.remote != allowed_remote:
        raise web.HTTPForbidden(text="Ingress access only")
    return await handler(request)


async def handle_index(request: web.Request) -> web.Response:
    del request
    return web.Response(text=INDEX_HTML, content_type="text/html")


async def handle_config(request: web.Request) -> web.Response:
    return web.json_response(
        public_target_options(read_options(request.app[OPTIONS_PATH_KEY]))
    )


async def handle_discover(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        platform = normalize_platform(
            payload.get("platform") if isinstance(payload, dict) else None
        )
        devices = await request.app[DISCOVER_FUNC_KEY](platform, timeout=10)
        request.app[DISCOVERED_KEY][platform] = devices
        return web.json_response({"devices": [device.as_dict() for device in devices]})
    except (ValueError, TimeoutError) as error:
        return web.json_response({"error": str(error)}, status=400)
    except Exception:
        LOG.exception("Selector discovery failed")
        return web.json_response(
            {"error": "Discovery failed; check the add-on log."}, status=500
        )


async def handle_select(request: web.Request) -> web.Response:
    try:
        selection = Selection.from_payload(await request.json())
        candidates = request.app[DISCOVERED_KEY].get(selection.platform, [])
        if not any(
            device.name == selection.name
            and device.address == selection.address
            and device.identifier == selection.identifier
            for device in candidates
        ):
            raise ValueError("Select a device from the current discovery list")
        options = options_with_selection(
            read_options(request.app[OPTIONS_PATH_KEY]), selection
        )
        await request.app[SAVE_FUNC_KEY](options)
        LOG.info(
            "Saved one target: platform=%s name=%r address=%s identifier=%r",
            selection.platform,
            selection.name,
            selection.address,
            selection.identifier,
        )
        return web.json_response({"options": public_target_options(options)})
    except (TypeError, ValueError) as error:
        return web.json_response({"error": str(error)}, status=400)
    except Exception:
        LOG.exception("Could not save selected target")
        return web.json_response(
            {"error": "Could not save the target; check the add-on log."}, status=502
        )


def _pairing_probe(request: web.Request):
    probe = request.app[PAIRING_PROBE_KEY]
    if probe is None:
        raise web.HTTPServiceUnavailable(text="Pairing test is unavailable")
    return probe


async def handle_pairing_status(request: web.Request) -> web.Response:
    return web.json_response(_pairing_probe(request).status())


async def handle_pairing_start(request: web.Request) -> web.Response:
    probe = _pairing_probe(request)
    try:
        await probe.start()
        return web.json_response(probe.status())
    except (OSError, PairingProbeError, ValueError) as error:
        LOG.warning("Could not start pairing test: %s", error)
        return web.json_response({"error": str(error)}, status=409)


async def handle_pairing_stop(request: web.Request) -> web.Response:
    probe = _pairing_probe(request)
    await probe.stop()
    return web.json_response(probe.status())


def create_app(
    *,
    options_path: Path = OPTIONS,
    allowed_remote: str | None = SUPERVISOR_REMOTE,
    discover_func=discover_devices,
    save_func=save_supervisor_options,
    pairing_probe=None,
) -> web.Application:
    app = web.Application(middlewares=[supervisor_only])
    app[ALLOWED_REMOTE_KEY] = allowed_remote
    app[OPTIONS_PATH_KEY] = options_path
    app[DISCOVER_FUNC_KEY] = discover_func
    app[SAVE_FUNC_KEY] = save_func
    app[DISCOVERED_KEY] = {}
    app[PAIRING_PROBE_KEY] = pairing_probe
    app.add_routes(
        [
            web.get("/", handle_index),
            web.get("/api/config", handle_config),
            web.post("/api/discover", handle_discover),
            web.post("/api/select", handle_select),
            web.get("/api/pairing/status", handle_pairing_status),
            web.post("/api/pairing/start", handle_pairing_start),
            web.post("/api/pairing/stop", handle_pairing_stop),
        ]
    )
    return app
