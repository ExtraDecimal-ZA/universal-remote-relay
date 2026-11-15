// Exercise the real embedded Bluetooth UI functions with a small DOM/fetch double.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../app/selector.py'), 'utf8');
const start = source.indexOf('const btScan =');
const end = source.indexOf('function platformName', start);
assert(start >= 0 && end > start, 'Bluetooth UI functions must be present');

function harness(script = source.slice(start, end)) {
  const elements = new Map();
  const documentListeners = new Map();
  function element() {
    return {
      children: [], disabled: false, textContent: '', replacements: 0, listeners: new Map(),
      addEventListener(name, callback) { this.listeners.set(name, callback); },
      replaceChildren() { this.children = []; this.replacements++; },
      append(...children) { this.children.push(...children); },
      querySelectorAll() { return this.children.flatMap(row => row.children || []).filter(item => item.type === 'button'); }
    };
  }
  const responses = [];
  const timers = new Map();
  const delays = new Map();
  const requestLog = [];
  let requests = 0;
  let timerId = 0;
  const context = vm.createContext({
    document: {
      hidden: false,
      addEventListener(name, callback) { documentListeners.set(name, callback); },
      getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
      createElement: element,
    },
    async fetch(url, options = {}) {
      requests++;
      requestLog.push({url, method: options.method || 'GET'});
      const response = responses.shift();
      if (response instanceof Error) throw response;
      assert(response, 'Unexpected network request');
      if (typeof response === 'function') return await response();
      return response;
    },
    AbortSignal,
    setTimeout(callback, delay) { timers.set(++timerId, callback); delays.set(timerId, delay); return timerId; },
    clearTimeout(id) { timers.delete(id); delays.delete(id); },
  });
  vm.runInContext(script, context);
  return { context, responses, timers, delays, elements, requestLog, requests: () => requests,
    visibility(hidden) {
      context.document.hidden = hidden;
      documentListeners.get('visibilitychange')();
    },
    run: code => vm.runInContext(code, context) };
}

function pairingHarness() {
  const scriptStart = source.indexOf('<script>') + '<script>'.length;
  const scriptEnd = source.indexOf('loadConfig().catch(showError);', scriptStart);
  assert(scriptStart >= '<script>'.length && scriptEnd > scriptStart);
  return harness(source.slice(scriptStart, scriptEnd));
}

function phoneState(overrides = {}) {
  return {state: 'receiver_ready', message: 'Ready', paired: true, active: true,
    pairing_active: false, remote_connected: false, pairing_code: '', remotes: [], ...overrides};
}

function response(body, ok = true) { return { ok, async json() { return body; } }; }
function state(overrides = {}) {
  return { available: true, scanning: false, pairing: false, state: 'ready', message: 'Ready', devices: [], ...overrides };
}

(async () => {
  {
    const h = pairingHarness();
    h.run(`showPairing({state: 'pairing_error', message: 'Pairing confirmation failed. Reconnect and retry.',
      paired: true, active: true, pairing_active: false, pairing_code: '', remotes: []})`);
    assert.equal(h.elements.get('pair-status').className, 'error', 'Saved trust must not hide confirmation failure');
    assert(h.elements.get('pair-status').textContent.includes('confirmation failed'));
    assert.equal(h.elements.get('pair-start').disabled, false, 'The user must be able to reopen pairing');
    assert.equal(h.elements.get('pair-code').hidden, true);
  }
  {
    const h = pairingHarness();
    h.run(`showPairing(${JSON.stringify(phoneState())})`);
    assert.deepEqual([...h.delays.values()], [5000], 'Idle status refresh should run five times less often');
    h.run(`showPairing(${JSON.stringify(phoneState({pairing_active: true}))})`);
    assert.deepEqual([...h.delays.values()], [1000], 'Pairing should retain fast code/countdown updates');
    h.run(`showPairing(${JSON.stringify(phoneState({remote_connected: true}))})`);
    assert.deepEqual([...h.delays.values()], [1000], 'Connected phones should retain live command feedback');
  }
  {
    const h = pairingHarness();
    const snapshot = phoneState({remotes: [{id: 'saved-phone-1', name: 'Phone'}]});
    for (let poll = 0; poll < 60; poll++) h.run(`showPairing(${JSON.stringify(snapshot)})`);
    const list = h.elements.get('remotes');
    assert.equal(list.replacements, 1, 'Unchanged saved phones should render once, not on every poll');
    snapshot.remotes[0].name = 'Renamed phone';
    h.run(`showPairing(${JSON.stringify(snapshot)})`);
    assert.equal(list.replacements, 2, 'Changed phone names must still update');
  }
  {
    const h = pairingHarness();
    h.run(`showPairing(${JSON.stringify(phoneState({pairing_active: true}))})`);
    h.run(`showBluetooth(${JSON.stringify(state({scanning: true}))})`);
    assert.equal(h.timers.size, 2);
    h.visibility(true);
    assert.equal(h.timers.size, 0, 'Hidden pages must stop both polling timers');
    h.responses.push(response(phoneState()), response(state()));
    h.visibility(false);
    await h.run('Promise.all([pairingLoad, btLoad])');
    assert.equal(h.requests(), 2, 'Returning to the page should refresh each status once');
    assert(h.requestLog.every(request => request.method === 'GET'), 'Resuming must never start discovery or pairing');
    assert.deepEqual([...h.delays.values()], [5000]);
  }
  for (const [load, busy] of [['loadPairing', 'pairingLoad'], ['loadBluetooth', 'btLoad']]) {
    const h = pairingHarness();
    let release;
    h.responses.push(() => new Promise(resolve => { release = resolve; }));
    const first = h.run(`${load}()`);
    const second = h.run(`${load}()`);
    assert.equal(h.requests(), 1, 'Concurrent refreshes must share one status request');
    assert.equal(h.timers.size, 0, 'A slow request must not create another polling request');
    release(response(load === 'loadPairing' ? phoneState() : state()));
    await Promise.all([first, second]);
    assert.equal(h.run(busy), null);
  }
  {
    const h = pairingHarness();
    h.responses.push(new Error('network interrupted'));
    await h.run('loadPairing().catch(showPairingError)');
    assert.equal(h.elements.get('pair-status').className, 'error');
    assert.equal(h.requests(), 1, 'A failed status read must not immediately retry in a loop');
    assert.deepEqual([...h.delays.values()], [5000], 'A failed refresh must schedule a bounded retry');
  }
  {
    const h = pairingHarness();
    let release;
    h.responses.push(() => new Promise(resolve => { release = resolve; }));
    const initial = h.run('loadPairing()');
    h.visibility(true);
    release(response(phoneState({pairing_active: true})));
    await initial;
    assert.equal(h.timers.size, 0, 'An in-flight response must not restart polling after the page is hidden');
  }
  {
    const h = pairingHarness();
    let release;
    h.responses.push(() => new Promise(resolve => { release = resolve; }));
    const initial = h.run('loadPairing()');
    const update = h.run("pairingRequest('api/pairing/start')");
    assert.equal(h.requests(), 1, 'A status response must finish before a pairing change is sent');
    h.responses.push(response(phoneState({pairing_active: true})));
    release(response(phoneState()));
    await Promise.all([initial, update]);
    assert.equal(h.requests(), 2);
    assert.equal(h.elements.get('pair-start').disabled, true);
    assert.equal(h.elements.get('pair-stop').disabled, false);
    assert.deepEqual([...h.delays.values()], [1000]);
  }
  {
    const h = pairingHarness();
    let release;
    h.responses.push(() => new Promise(resolve => { release = resolve; }));
    const initial = h.run('loadBluetooth()');
    const update = h.run("bluetoothRequest('api/bluetooth/scan')");
    assert.equal(h.requests(), 1, 'Bluetooth changes must wait for older status reads');
    h.responses.push(response({}), response(state({scanning: true})));
    release(response(state()));
    await Promise.all([initial, update]);
    assert.equal(h.requests(), 3);
    assert.equal(h.elements.get('bt-scan').disabled, true);
    assert.equal(h.elements.get('bt-stop').disabled, false);
    assert.deepEqual([...h.delays.values()], [2500]);
  }
  {
    const h = pairingHarness();
    h.run(`showPairing(${JSON.stringify(phoneState({remotes: [{id: 'saved-phone-1', name: 'Phone'}]}))})`);
    const remove = h.elements.get('remotes').children[0].children[1];
    h.responses.push(response({error: 'Temporary save failure'}, false));
    await remove.listeners.get('click')();
    assert.equal(remove.disabled, false, 'A failed removal must restore the unchanged button');
    assert.equal(h.elements.get('pair-status').className, 'error');
  }
  for (const [bonded, expected] of [[true, 'Paired, saved, connected'], [false, 'Paired, temporary, connected'], [null, 'Paired, saved pairing unverified, connected']]) {
    const h = harness();
    h.responses.push(response(state({devices: [{id: 'remote', name: 'Xiaomi RC', address: 'test', paired: true, connected: true, bonded}]})));
    await h.run('loadBluetooth()');
    const label = h.elements.get('bt-devices').children[0].children[0].textContent;
    assert(label.includes(expected), `Saved pairing state must be accurate: ${expected}`);
  }
  {
    const h = harness();
    h.responses.push(response(state({ scanning: true })));
    await h.run('loadBluetooth()');
    h.run("showBluetoothError(new Error('network interrupted'))");
    assert.equal(h.elements.get('bt-scan').disabled, true);
    assert.equal(h.elements.get('bt-stop').disabled, false);
    assert.equal(h.timers.size, 1, 'Active scan polling must resume after a failed refresh');
  }
  {
    const h = harness();
    h.responses.push(response({ error: 'Pairing refused' }, false), response(state({
      devices: [{ id: 'remote', name: '<remote>', address: 'test', selectable: true, paired: false }]
    })));
    await assert.rejects(h.run("bluetoothRequest('api/bluetooth/pair', {id: 'remote'})"), /Pairing refused/);
    assert.equal(h.requests(), 2, 'Failed mutations must refresh authoritative host state');
    assert.equal(h.elements.get('bt-scan').disabled, false);
    const buttons = h.elements.get('bt-devices').querySelectorAll('button');
    assert.equal(buttons.length, 1);
    assert.equal(buttons[0].disabled, false, 'Retry controls must be restored');
  }
  {
    const h = harness();
    h.responses.push(response(state({ pairing: true })));
    await h.run('loadBluetooth()');
    h.run("showBluetoothError(new Error('temporary failure'))");
    assert.equal(h.elements.get('bt-scan').disabled, true, 'An error must not allow a second scan during pairing');
    assert.equal(h.elements.get('bt-stop').disabled, true);
    assert.equal(h.timers.size, 1);
  }
  assert(source.lastIndexOf('<h2>Add Bluetooth remote</h2>') > source.indexOf('<h2>Phone remote</h2>'));
  console.log('Phone and Bluetooth Web UI behavior checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
