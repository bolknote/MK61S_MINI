#!/usr/bin/env node
'use strict';
// Four source-selected controls, not a key/digit search. Fresh protected
// stock instances receive public keys ONLY; snapshots are passive. All
// positive conditional ROM bridges stay outside this native reference.
const assert = require('node:assert/strict');
const {setup: readerSetup, reader} = require('./cache-cf-buffer-native.cjs');
const {trace, aligned} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {rawMemoryRegister} = require('./check_ac_signature_keyboard.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const raw = [0, 3, 9, 12, 18, 21];
const word = (values, lane = 0) => Array.from({length: 12}, (_, i) =>
  values[3*i+lane].toString(16).toUpperCase()).join('');
const ready = e => e.r[22] === 7 && Array.from({length: 8}, (_, i) =>
  e.st[3*i+1]).every(v => v === 0);
const data = c => ({program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c), registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i))});
const specs = [
  {name: 'step_counter2', values: '8.7754321E-91', keys: ['ШГ→'],
    startIp: 0x62, start: 19, end: 3360, counter: 2, B0: 1},
  {name: 'step_counter8', values: '8.7754327E-91', keys: ['ШГ→'],
    startIp: 0x62, start: 19, end: 3360, counter: 8, B0: 7},
  {name: 'step_counter8_ready', values: '7.7754327E-91', keys: ['ШГ→'],
    startIp: 0x62, start: 19, end: 3360, counter: 8, B0: 7, holdsAfter62: true},
  {name: 'operand3', values: '8.7754321E-91', keys: ['K', '3'],
    startIp: 0x54, start: 1127, end: 3360},
];

function prepare(spec) {
  const c = readerSetup({values: spec.values}); reader(c);
  c.pressSequence(['F', 'Сx']).runFrames(2); aligned(c);
  return c;
}
function finish(c, spec) { c.pressSequence(spec.keys).runFrames(2); aligned(c); }

function capture(spec, {mirror = true, log = true} = {}) {
  const c = prepare(spec), before = data(c), initial = {command: 0, state: machineSnapshot(c)};
  const source = initial.state.ik1302, payload = raw.map(j => source.r[j]);
  assert.deepEqual(payload, [3, 10, 4, 13, 5, 7]); assert.ok(ready(source));
  if (spec.B0 !== undefined) assert.equal(source.r[1], spec.B0);
  const origin = [], decoder = []; let started = false;
  const result = trace(c, c => finish(c, spec), {
    extraIps: Array.from({length: 256}, (_, i) => i), fullState: true,
    otherChipsAt: e => {
      const save = () => ({command: e.command, ip: e.ip, state: machineSnapshot(c)});
      if (origin.length < 65) origin.push(save());
      if (!decoder.length && e.ip === spec.startIp) started = true;
      if (started && decoder.length < 160) decoder.push(save());
      return false;
    },
  });
  const events = result.events, after = data(c), end = {command: spec.end, state: machineSnapshot(c)};
  assert.equal(events.length, spec.end); assert.ok(events.every((e, i) => e.command === i));
  assert.equal(origin.length, 65); assert.equal(decoder.length, 160);
  assert.equal(decoder[0].command, spec.start);
  for (const group of [origin, decoder])
    assert.ok(group.every((e, i) => !i || e.command === group[i-1].command+1));
  assert.deepEqual(after, before, 'ALL105 programme bytes/56 Ms bytes/15 ordinary words held');
  assert.deepEqual(result.primitives, []);
  assert.ok(!events.some(e => [0x28, 0xBC, 0xCF, 0xC3, 0xD4].includes(e.ip)));
  if (spec.counter !== undefined) {
    const inlet = decoder[0].state.ik1302;
    assert.equal(inlet.r[26], spec.counter); assert.equal(inlet.r[1], spec.B0);
    assert.deepEqual(raw.map(j => inlet.r[j]), payload); assert.ok(ready(inlet));
    assert.deepEqual([inlet.r[29], inlet.r[32], inlet.r[35]], [0, 0, 9]);
    assert.deepEqual([inlet.r[2], inlet.r[5]], [5, 0]);
    assert.equal(events.findIndex(e => !ready(e)), spec.holdsAfter62 ? 61 : 20);
    assert.equal(events[19].ip, 0x62);
    assert.equal(events[20].r[22], spec.holdsAfter62 ? 7 : 8,
      '62 shifts incomingB8 into B7');
    assert.equal(ready(events[20]), !!spec.holdsAfter62);
    assert.deepEqual(raw.map(j => events[20].r[j]), payload);
    assert.equal(events[20].r[26], spec.counter);
    assert.equal(events[20].ip, 0x6E, 'real caller forces return6E, NOT1D/28');
    assert.equal(events.findIndex(e => !raw.every((j, i) => e.r[j] === payload[i])), 21);
    assert.equal(end.state.ik1302.r[36]+16*end.state.ik1302.r[39], 0x35);
  } else {
    const inlet = decoder[0].state.ik1302;
    assert.deepEqual([inlet.r[29], inlet.r[32]], [3, 0]);
    assert.deepEqual(raw.map(j => inlet.r[j]), payload);
    assert.ok(ready(inlet));
    assert.deepEqual(decoder.slice(0, 12).map(e => e.ip),
      [0x54, 0x56, 0x65, 0x7B, 0xB7, 0x45, 0x8B, 0x48, 0x4A, 0x4C, 0x4E, 0x97]);
    assert.equal(end.state.ik1302.r[36]+16*end.state.ik1302.r[39], 0xE5);
  }
  if (mirror) {
    const plain = prepare(spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), initial.state, 'fresh completely unobserved preparation');
    finish(plain, spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), end.state, 'fresh unobserved whole ALL5 suffix');
  }
  const report = {...spec, nativeKeyboardOnly: true, observerIndependent: mirror,
    initialB: word(source.r, 1), endIp: end.state.ik1302.r[36]+16*end.state.ik1302.r[39],
    endMode: [end.state.ik1302.r[2], end.state.ik1302.r[5]],
    firstReadinessLoss: events.findIndex(e => !ready(e)),
    intactCacheAtCounter: spec.counter === undefined ? null : true,
    counterReadyAndCacheAfter62: spec.counter === undefined ? null : !!spec.holdsAfter62,
    all105Program56Ms15OrdinaryWordsHeld: true,
    native28: false, nativeBC: false, ordinaryCSignF: false, partialK2: false};
  if (log) console.log(JSON.stringify(report));
  return {report, initial, origin, decoder, end};
}
if (require.main === module) {
  if (process.argv.includes('--proof-input'))
    console.log(JSON.stringify(specs.map(spec => capture(spec, {log: false}))));
  else specs.forEach(spec => capture(spec));
}
module.exports = {specs, prepare, finish, capture};
