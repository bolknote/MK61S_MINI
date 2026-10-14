#!/usr/bin/env node
'use strict';
// ROM-directed CF/C3 controls. Only public physical keys/frames change the
// immutable reference. The positive ZERO case creates 1, NOT a signF.
const assert = require('node:assert/strict');
const {prepare} = require('./cache-control-f-transfer-native.cjs');
const {prepareReader} = require('./cache-da-sign-native.cjs');
const {prepare: prepareMarker} = require('./cache-da-keyboard.cjs');
const {prepareSelector} = require('./st34-origin-trace.cjs');
const {trace, aligned} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const {rawMemoryRegister, finishSignature700, registerKey} = require('./check_ac_signature_keyboard.cjs');

// The last cached byte has high tetra7. It is installed by physical keys,
// not loadProgram/writeCommand: K/С/П/5 is the real opcode75.
const fixture = {
  name: 'cf_seven', bytes: [1, 2, 3, 0xA3, 0xD4, 0x75, 7],
  keys: ['1', '2', '3', 'K', 'ПП', '3', 'K', 'П→X', '4', 'K', 'С/П', '5', '7'],
};
const specs = [
  // aligned() may add whole frames; these are full observed macro counts.
  {name: 'zero', digit: '0', suffix: ['ВП'], end: 3360, expectedC3: true},
  {name: 'seven', digit: '7', suffix: ['ВП'], end: 3360, expectedC3: false},
  {name: 'cache_seven', suffix: ['F', 'Сx', 'ВП'], end: 5040, expectedC3: false},
];
const word = (values, lane = 0) => Array.from({length: 12}, (_, i) =>
  values[3*i+lane].toString(16).toUpperCase()).join('');
const data = c => ({
  program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c),
  registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i)),
});

function setup(spec, {withoutReaderObserver = false} = {}) {
  if (spec.name === 'cache_seven') {
    if (!withoutReaderObserver)
      return prepareReader({fixture, selector: 9, carrier: '0'}).c;
    // Same physical preparation, but no reader or suffix tick hook at all.
    const c = prepare();
    c.inputNumber('0', {clear: true}).pressSequence(['X→П', registerKey(12)]); aligned(c);
    prepareMarker({fixture, calc: c});
    prepareSelector(c, {selector: 9}); finishSignature700(c); aligned(c);
    c.pressSequence(['П→X', registerKey(9)]).runFrames(8); aligned(c);
    return c;
  }
  const c = prepare();
  c.press(spec.digit).runFrames(2); aligned(c);
  return c;
}

function finish(c, spec) {
  c.pressSequence(spec.suffix).runFrames(2); aligned(c);
}

function capture(spec, {mirror = true, log = true} = {}) {
  const c = setup(spec), before = data(c), prefix = [];
  const initial = {command: 0, state: machineSnapshot(c)};
  if (spec.name === 'cache_seven') {
    assert.equal(initial.state.ik1302.r[21], 7);
    assert.deepEqual([0, 3, 9, 12, 18, 21].map(k => initial.state.ik1302.r[k]),
      [3, 10, 4, 13, 5, 7], 'real simultaneous program cache A3/D4/75');
  }
  const t = trace(c, c => finish(c, spec), {
    extraIps: Array.from({length: 256}, (_, i) => i), fullState: true,
    otherChipsAt: e => {
      if ((e.ip === 0x8C && !prefix.length) || (prefix.length && prefix.length < 65))
        prefix.push({command: e.command, ip: e.ip, state: machineSnapshot(c)});
      return false;
    },
  });
  assert.equal(t.events.length, spec.end, 'actual observed complete macro count');
  assert.ok(t.events.every((e, i) => e.command === i));
  const cf = t.events.filter(e => e.ip === 0xCF);
  const c3 = t.events.filter(e => e.ip === 0xC3);
  assert.equal(cf.length, 1); assert.equal(c3.length, Number(spec.expectedC3));
  assert.equal(prefix.length, 65);
  assert.ok(prefix.every((e, i) => !i || e.command === prefix[i-1].command+1));
  const first = prefix[0], inlet = cf[0];
  assert.equal(first.ip, 0x8C); assert.equal(first.state.ik1302.s1, 12);
  assert.equal(inlet.command-first.command, 15);
  assert.equal(inlet.s1, 0);
  for (let i = 0; i < 8; i++)
    assert.equal(inlet.r[1+3*i], first.state.ik1302.st[3*i]);
  assert.equal(inlet.r[34], first.state.ik1302.st[34]);
  const lowerB = Array.from({length: 8}, (_, i) => inlet.r[1+3*i]);
  assert.equal(lowerB.every(v => v === 0), spec.expectedC3);
  const next = t.events.find(e => e.command === inlet.command+1);
  assert.equal(next.ip, spec.expectedC3 ? 0xC3 : 0xC2);
  assert.equal(next.r[21], inlet.r[21]);
  if (spec.name === 'zero') {
    assert.equal(inlet.r[21], 0); assert.equal(next.r[22], 1);
    const afterC3 = t.events.find(e => e.command === next.command+1);
    assert.equal(afterC3.ip, 0xC2); assert.equal(afterC3.r[21], 1);
  } else if (spec.name === 'seven') {
    assert.equal(inlet.r[21], 7); assert.equal(inlet.r[22], 7);
  } else {
    assert.equal(inlet.r[21], 7);
    assert.deepEqual(lowerB, [0, 8, 8, 8, 8, 8, 8, 0]);
    assert.equal(inlet.r[34], 15);
  }
  assert.ok(!t.events.some(e => e.ip === 0xD4), 'no native ordinary-sign writer');
  const after = data(c), end = {command: spec.end, state: machineSnapshot(c)};
  assert.deepEqual(after, before, 'all105 program /56 Ms /15 ordinary words held');
  assert.equal(c.ik1302.r[36]+16*c.ik1302.r[39], 0x35);
  assert.equal(c.ik1302.r[21], spec.name === 'zero' ? 1 : spec.name === 'seven' ? 7 : 0);
  if (mirror) {
    const plain = setup(spec, {withoutReaderObserver: true}); data(plain);
    assert.deepEqual(machineSnapshot(plain), initial.state, 'fresh unobserved preparation');
    finish(plain, spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), end.state, 'fresh unobserved ALL5 mirror');
  }
  const report = {
    name: spec.name, keys: spec.digit ? [spec.digit, ...spec.suffix] : spec.suffix,
    nativeCF: true, nativeC3: spec.expectedC3, CF_A7: inlet.r[21], CF_lowerB: lowerB,
    CF_header: inlet.r[34], at8C_ST0: word(first.state.ik1302.st),
    display: c.displayText(), finalA: word(c.ik1302.r),
    all105Program56Ms15OrdinaryWordsHeld: true, observerIndependent: mirror,
    nativeCF_C3NewF: false, ordinaryCSignFCreated: false, partialK2: false,
  };
  if (log) console.log(JSON.stringify(report));
  return {report, initial, prefix, end};
}

if (require.main === module) {
  if (process.argv.includes('--proof-input'))
    console.log(JSON.stringify(specs.map(spec => capture(spec, {log: false}))));
  else {
    for (const spec of specs) capture(spec);
    console.log('PASS three real CF controls and three fresh ALL5 mirrors; '+
      '0/ВП entersC3 and makes1, notF; seven/cache7 enterC2, noD4/partialK2.');
  }
}
module.exports = {fixture, specs, setup, finish, capture};
