#!/usr/bin/env node
'use strict';
// Three source-selected controls of the UNCANCELLED native C8 reader.
// The reference receives public keys only. All snapshots/hooks are passive;
// no dispatch, return tag, RAM, ROM or chip-state assignment is used.
const assert = require('node:assert/strict');
const {setup, reader} = require('./cache-cf-buffer-native.cjs');
const {trace, aligned} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {rawMemoryRegister} = require('./check_ac_signature_keyboard.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const raw = [0, 3, 9, 12, 18, 21];
const ip = a => a.r[36]+16*a.r[39];
const data = c => ({program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c), registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i))});
const specs = [
  {name: 'call_prefix', keys: ['K', 'ПП'], end: 3360},
  {name: 'call_operand8', keys: ['K', 'ПП', '8'], end: 5040},
  {name: 'return_key', keys: ['В/О'], end: 3360},
];

function prepare() {
  const c = setup({values: '7.7754327E-91'}); reader(c);
  // Deliberately NO F/Сx: test the original pending-input flag R23=1.
  return c;
}
function finish(c, spec) { c.pressSequence(spec.keys).runFrames(2); aligned(c); }
function changes(before, after) {
  return Object.fromEntries(Object.keys(before).map(field => [field,
    Object.entries(before[field]).flatMap(([key, value]) =>
      JSON.stringify(value) === JSON.stringify(after[field][key]) ? [] :
        [{index: Array.isArray(before[field]) ? Number(key) : key,
          before: value, after: after[field][key]}]) ]));
}

function capture(spec, {mirror = true, log = true} = {}) {
  const c = prepare(), before = data(c), initial = {command: 0, state: machineSnapshot(c)};
  const payload = raw.map(j => initial.state.ik1302.r[j]);
  assert.deepEqual(payload, [3, 10, 4, 13, 5, 7]);
  assert.equal(initial.state.ik1302.r[23], 1);
  assert.equal(ip(initial.state.ik1302), 0x35);
  const origin = [], operandPrefix = [], replacement = [], pointer = [];
  let collecting = false, replacing = false;
  const result = trace(c, c => finish(c, spec), {
    extraIps: Array.from({length: 256}, (_, i) => i), fullState: true,
    otherChipsAt: e => {
      const save = () => ({command: e.command, ip: e.ip, slot: e.slot,
        state: machineSnapshot(c)});
      if (origin.length < 65) origin.push(save());
      if (spec.keys.length > 1 && e.command >= 1120 && operandPrefix.length < 65)
        operandPrefix.push(save());
      if (!replacement.length && e.ip === 0xEE) replacing = true;
      if (replacing && replacement.length < 65) replacement.push(save());
      if (!pointer.length && e.ip === 0xD6) collecting = true;
      if (collecting && pointer.length < 160) pointer.push(save());
      return false;
    },
  });
  const events = result.events, after = data(c), end = {command: spec.end, state: machineSnapshot(c)};
  assert.equal(events.length, spec.end);
  assert.ok(events.every((e, i) => e.command === i));
  assert.equal(origin.length, 65);
  for (const group of [origin, operandPrefix, replacement, pointer])
    assert.ok(group.every((e, i) => !i || e.command === group[i-1].command+1));
  assert.equal(operandPrefix.length, spec.keys.length > 1 ? 65 : 0);
  assert.deepEqual(result.primitives, []);
  assert.deepEqual(after, before, 'all105 programme bytes/56 Ms bytes/15 ordinary words held');
  const firstLoss = events.findIndex(e => !raw.every((j, i) => e.r[j] === payload[i]));
  const ee = events.find(e => e.ip === 0xEE), d6 = events.find(e => e.ip === 0xD6);
  const call = events.find(e => e.ip === 0x73), delta = changes(before, after);
  if (spec.name === 'call_prefix') {
    assert.equal(replacement.length, 0);
    assert.equal(firstLoss, -1); assert.equal(ee, undefined); assert.equal(d6, undefined);
    assert.equal(call, undefined); assert.equal(ip(end.state.ik1302), 0x35);
    assert.ok(!events.some(e => [0x40, 0x93, 0x16, 0x3F, 0x49, 0x91,
      0x98, 0xE1, 0xE4, 0xEC, 0xC9, 0xD4].includes(e.ip)));
    assert.deepEqual(after, before, '105 programme bytes/56 Ms bytes/15 ordinary words held');
    const a = initial.state.ik1302, b = end.state.ik1302;
    assert.deepEqual(a.r.flatMap((v, j) => v === b.r[j] ? [] : [j]), [35]);
    assert.deepEqual([a.r[35], b.r[35]], [5, 10]);
    assert.deepEqual(a.st.flatMap((v, j) => v === b.st[j] ? [] : [j]), [37, 38, 40, 41]);
    assert.equal(b.r[23], 1);
  } else {
    assert.equal(replacement.length, 65);
    assert.ok(ee && firstLoss === ee.command+1);
    assert.deepEqual(raw.map(j => ee.r[j]), payload);
    assert.ok(!events.slice(0, ee.command).some(e => [0x40, 0x93, 0x16, 0x3F,
      0x49, 0x91, 0x98, 0xE1, 0xE4, 0xEC, 0xC9, 0xD4].includes(e.ip)),
      'no universal full A-to-ST/A-to-B copy or export word before the first EE');
    if (spec.name === 'call_operand8') {
      assert.equal(ee.command, 2279); assert.equal(firstLoss, 2280);
      assert.ok(d6 && d6.command === 2306 && call && call.command === 2340);
      assert.equal(pointer.length, 160);
      assert.deepEqual(raw.map(j => call.r[j]), [15, 15, 15, 15, 0, 9]);
      assert.equal(call.r[23], 0);
      assert.equal(events[call.command+1].ip, 0x6F);
      assert.ok(!events.some(e => e.ip === 0xC9));
    } else {
      assert.equal(ee.command, 44); assert.equal(firstLoss, 45);
      assert.equal(d6, undefined); assert.equal(call, undefined);
      assert.equal(ip(end.state.ik1302), 0x35);
    }
  }
  if (mirror) {
    const plain = prepare(); data(plain);
    assert.deepEqual(machineSnapshot(plain), initial.state, 'fresh unobserved preparation');
    finish(plain, spec);
    assert.deepEqual(data(plain), after, 'fresh unobserved data mirror');
    assert.deepEqual(machineSnapshot(plain), end.state, 'fresh unobserved whole ALL5 suffix');
  }
  const report = {...spec, values: '7.7754327E-91', nativeKeyboardOnly: true,
    observerIndependent: mirror, initialInputFlag: 1, firstEE: ee?.command ?? -1,
    firstCacheReplacement: firstLoss, firstD6: d6?.command ?? -1,
    first73: call?.command ?? -1, at73PC: call?.pc ?? null,
    at73Raw6: call ? raw.map(j => call.r[j]) : null,
    endIp: ip(end.state.ik1302), endPC: end.state.ik1302.r[31]+16*end.state.ik1302.r[34],
    endInputFlag: end.state.ik1302.r[23], dataChanges: delta,
    newSTReserve: false, nativeCacheExport: false, partialK2: false};
  if (log) console.log(JSON.stringify(report));
  return {report, initial, origin, operandPrefix, replacement, pointer, end};
}
if (require.main === module) {
  if (process.argv.includes('--proof-input'))
    console.log(JSON.stringify(specs.map(spec => capture(spec, {log: false}))));
  else specs.forEach(spec => capture(spec));
}
module.exports = {specs, prepare, finish, capture};
