#!/usr/bin/env node
'use strict';
// ROM-directed data preparation for ONE restore93, not its native entry.
// A changed decimal payload supplies B7=7 alongside cache7 and zero ST1.
// Only public keys/frames change the immutable reference. No address repair.
const assert = require('node:assert/strict');
const {prepare} = require('./cache-control-f-transfer-native.cjs');
const {prepare: prepareMarker} = require('./cache-da-keyboard.cjs');
const {prepareSelector} = require('./st34-origin-trace.cjs');
const {finishSignature700, registerKey, rawMemoryRegister} = require('./check_ac_signature_keyboard.cjs');
const {trace, aligned} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const {fixture} = require('./cache-cf-constructor-native.cjs');
const specs = [
  {name: 'original_six', values: '8.7654321E-91', B7: 6},
  {name: 'prepared_seven', values: '8.7754321E-91', B7: 7},
];
const word = (v, lane = 0) => Array.from({length: 12}, (_, i) =>
  v[3*i+lane].toString(16).toUpperCase()).join('');
const data = c => ({
  program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c),
  registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i)),
});
function setup(spec) {
  const c = prepare();
  c.inputNumber('0', {clear: true}).pressSequence(['X→П', registerKey(12)]); aligned(c);
  prepareMarker({fixture, calc: c, values: spec.values});
  prepareSelector(c, {selector: 9}); finishSignature700(c); aligned(c);
  assert.equal(rawMemoryRegister(c, 8), '9990FFFFFFF0');
  assert.equal(rawMemoryRegister(c, 12), '000000000000');
  return c;
}
function reader(c) {
  c.pressSequence(['П→X', registerKey(9)]).runFrames(8); aligned(c);
}
function capture(spec, {mirror = true, log = true} = {}) {
  const c = setup(spec), before = data(c);
  const initial = {command: 0, state: machineSnapshot(c)};
  const origin = []; let window = null, prefix = null;
  const t = trace(c, reader, {
    extraIps: Array.from({length: 256}, (_, i) => i), fullState: true,
    otherChipsAt: e => {
      const snapshot = () => ({command: e.command, ip: e.ip, state: machineSnapshot(c)});
      if (origin.length < 65) origin.push(snapshot());
      if (prefix === null) {
        if (e.ip === 0xAC) window = [];
        if (window) window.push(snapshot());
        if (e.ip === 0xC8) { assert.ok(window); prefix = window; }
      } else if (prefix.at(-1).command < prefix.find(v => v.ip === 0xC8).command+64) {
        prefix.push(snapshot());
      }
      return false;
    },
  });
  assert.equal(t.events.length, 6720);
  assert.ok(t.events.every((e, i) => e.command === i));
  assert.deepEqual(t.primitives, [0xC8]);
  for (const entries of [origin, prefix])
    assert.ok(entries.every((e, i) => !i || e.command === entries[i-1].command+1));
  assert.equal(origin.length, 65);
  assert.equal(prefix[0].ip, 0xAC);
  assert.equal(prefix.at(-1).command-prefix.find(v => v.ip === 0xC8).command, 64);
  const restoreHeads = t.events.flatMap((e, i) => e.ip === 0x93 ? [{
    command: e.command, previous: t.events[i-1].ip, head: e.sp[0],
    B7: e.r[22], ST1Lower8AllZero:
      Array.from({length: 8}, (_, j) => e.st[3*j+1]).every(v => v === 0),
  }] : []);
  assert.deepEqual(restoreHeads.map(e => [e.command, e.previous, e.head, e.B7,
    e.ST1Lower8AllZero]), [[1218, 0x92, 0x93, 0, false],
    [1223, 0x9A, 0xE4, 1, false], [1246, 0xA9, 0xE5, 1, false]]);
  assert.ok(!t.events.some(e => e.r[21] === 7 &&
    Array.from({length: 8}, (_, j) => e.st[3*j]).every(v => v === 0)),
    'this complete native reader never reaches joint A7=7/zeroST0');
  const a = c.ik1302;
  assert.equal(a.r[36]+16*a.r[39], 0x35);
  assert.equal(a.r[21], 7);
  assert.equal(a.r[22], spec.B7);
  assert.equal(a.r[37]+16*a.r[40], 0x21);
  assert.equal(a.s1, 0); assert.equal(a.r[26], 0);
  assert.deepEqual(Array.from({length: 8}, (_, i) => a.stack[3*i+1]), Array(8).fill(0));
  assert.deepEqual([0, 3, 9, 12, 18, 21].map(k => a.r[k]), [3, 10, 4, 13, 5, 7]);
  assert.deepEqual(a.stack.slice(36, 39).map((lo, i) => lo+16*a.stack[39+i]),
    [0x70, 0xD8, 0xEC], 'the native return head is70, NOT a repaired35/8C/CF');
  assert.deepEqual(data(c), before, 'all105 program /56 Ms /15 ordinary words held by reader');
  const end = {command: 6720, state: machineSnapshot(c)};
  const stable = machineSnapshot(c);
  c.runFrames(3); aligned(c);
  assert.deepEqual(machineSnapshot(c), stable, 'native phase-aligned idle state is stable');
  if (mirror) {
    const plain = setup(spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), initial.state, 'fresh unobserved preparation');
    reader(plain); data(plain);
    assert.deepEqual(machineSnapshot(plain), end.state, 'fresh unobserved entire-reader ALL5 mirror');
  }
  const report = {
    name: spec.name, values: spec.values, nativeDataOnly: true,
    A: word(a.r), B: word(a.r, 1), ST0: word(a.stack), ST1: word(a.stack, 1),
    A7: a.r[21], B7: a.r[22], ST1Lower8AllZero: true,
    single93DataReady: spec.B7 === 7, native93Entry: false,
    restoreHeads, jointA7SevenZeroST0DuringReader: false,
    returnTags: [0x70, 0xD8, 0xEC], all105Program56Ms15OrdinaryWordsHeld: true,
    nativeControl: {vector: 0x21, S1: 0, R26: 0},
    observerIndependent: mirror, ordinaryCSignFCreated: false, partialK2: false,
  };
  if (log) console.log(JSON.stringify(report));
  return {report, initial, origin, prefix, end};
}
if (require.main === module) {
  if (process.argv.includes('--proof-input'))
    console.log(JSON.stringify(specs.map(spec => capture(spec, {log: false}))));
  else {
    for (const spec of specs) capture(spec);
    console.log('PASS two native reader preparations and fresh whole ALL5 mirrors; '+
      'B7=7/zeroST1 is DATA readiness, not native93 entry or partialK2.');
  }
}
module.exports = {specs, setup, reader, capture};
