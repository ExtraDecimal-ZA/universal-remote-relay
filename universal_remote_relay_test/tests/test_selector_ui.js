// Exercise the real embedded Bluetooth UI functions with a small DOM/fetch double.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../app/selector.py'), 'utf8');
const start = source.indexOf('const btScan =');
const end = source.indexOf('function platformName', start);
assert(start >= 0 && end > start, 'Bluetooth UI functions must be present');

function harness() {
  const elements = new Map();
  function element() {
    return {
      children: [], disabled: false, textContent: '',
      addEventListener() {},
      replaceChildren() { this.children = []; },
      append(...children) { this.children.push(...children); },
      querySelectorAll() { return this.children.flatMap(row => row.children || []).filter(item => item.type === 'button'); }
    };
  }
  const responses = [];
  const timers = new Map();
  let requests = 0;
  let timerId = 0;
  const context = vm.createContext({
    document: {
      getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
      createElement: element,
    },
    async fetch() {
      requests++;
      const response = responses.shift();
      if (response instanceof Error) throw response;
      assert(response, 'Unexpected network request');
      return response;
    },
    setTimeout(callback) { timers.set(++timerId, callback); return timerId; },
    clearTimeout(id) { timers.delete(id); },
  });
  vm.runInContext(source.slice(start, end), context);
  return { context, responses, timers, elements, requests: () => requests,
    run: code => vm.runInContext(code, context) };
}

function response(body, ok = true) { return { ok, async json() { return body; } }; }
function state(overrides = {}) {
  return { available: true, scanning: false, pairing: false, state: 'ready', message: 'Ready', devices: [], ...overrides };
}

(async () => {
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
  console.log('Bluetooth Web UI behavior checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
