#!/usr/bin/env node
'use strict';
// Real, guarded mode/decoder controls after the buffer preparation.
// A transient7/zeroST0 INSIDE91 is not a callable CF entry. No state setters.
const assert = require('node:assert/strict');
const {specs: payloads, setup, reader} = require('./cache-cf-buffer-native.cjs');
const {trace, aligned} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const {rawMemoryRegister} = require('./check_ac_signature_keyboard.cjs');
const allIps = Array.from({length: 256}, (_, i) => i);
const word = (v, lane = 0) => Array.from({length: 12}, (_, i) =>
  v[3*i+lane].toString(16).toUpperCase()).join('');
const lowerZero = (v, lane = 0) => Array.from({length: 8}, (_, i) =>
  v[3*i+lane]).every(n => n === 0);
const ready = e => e.r[22] === 7 && lowerZero(e.st, 1);
const joint = e => e.r[21] === 7 && lowerZero(e.st);
const data = c => ({
  program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c),
  registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i)),
});
const specs = [
  {name: 'cancel_seven', payload: 1, keys: ['F', 'Сx'], end: 3360},
  {name: 'manual_sign', payload: 1, keys: ['K', '5'], end: 3360},
  {name: 'mode_cycle_seven', payload: 1, keys: ['F', 'ВП', 'F', '/-/'], end: 6720},
  {name: 'mode_cycle_six', payload: 0, keys: ['F', 'ВП', 'F', '/-/'], end: 6720},
];

function prepare(spec) {
  const c = setup(payloads[spec.payload]); reader(c);
  if (spec.name !== 'cancel_seven') finish(c, specs[0]);
  return c;
}
function finish(c, spec) {
  c.pressSequence(spec.keys).runFrames(2); aligned(c);
}

function capture(spec, {mirror = true, log = true} = {}) {
  const c = prepare(spec), before = data(c);
  const initial = {command: 0, state: machineSnapshot(c)};
  const origin = [], formatter = [], packet = [], decoder = [];
  let packetStarted = false, decoderStarted = false;
  const result = trace(c, c => finish(c, spec), {
    extraIps: allIps, fullState: true,
    otherChipsAt: e => {
      const save = () => ({command: e.command, ip: e.ip, state: machineSnapshot(c)});
      if (origin.length < 65) origin.push(save());
      if (spec.name.startsWith('mode_cycle')) {
        if ((e.command >= 1120 && e.ip === 0x62 && !formatter.length) ||
            (formatter.length && formatter.length < 65)) formatter.push(save());
        if (e.command >= 3360 && e.ip === 0xE1 && !packet.length) packetStarted = true;
        if (packetStarted && packet.length < 100) packet.push(save());
      }
      if (spec.name === 'manual_sign') {
        if (e.ip === 0xA3 && !decoder.length) decoderStarted = true;
        if (decoderStarted && decoder.length < 90) decoder.push(save());
      }
      return false;
    },
  });
  const events = result.events;
  assert.equal(events.length, spec.end);
  assert.ok(events.every((e, i) => e.command === i));
  assert.deepEqual(result.primitives, []);
  assert.ok(!events.some(e => [0xCF, 0xC3, 0xD4].includes(e.ip)));
  const end = {command: spec.end, state: machineSnapshot(c)};
  assert.deepEqual(data(c), before, 'all105 program /56 Ms /15 ordinary words held');
  for (const entries of [origin, formatter, packet, decoder])
    assert.ok(entries.every((e, i) => !i || e.command === entries[i-1].command+1));
  assert.equal(origin.length, 65);
  const source = initial.state.ik1302, final = end.state.ik1302;
  const firstLoss = events.findIndex(e => !ready(e));
  const firstJoint = events.findIndex(joint);
  const firstF = events.findIndex(e => e.r[21] === 15);
  const dispatches = events.filter(e => e.ip === 0xA3).map(e => ({
    command: e.command, vector: e.r[37]+16*e.r[40], head: e.sp[0],
    B7: e.r[22], zeroST1: lowerZero(e.st, 1), S1: e.s1,
    R32: e.r[32], R35: e.r[35],
  }));
  assert.ok(!dispatches.some(e => e.vector === 0x93));
  if (spec.name === 'cancel_seven') {
    assert.equal(firstLoss, -1); assert.equal(firstJoint, -1);
    for (const lane of [0, 1]) {
      assert.equal(word(final.r, lane), word(source.r, lane));
      assert.equal(word(final.st, lane), word(source.st, lane));
    }
    assert.equal(source.r[23], 1); assert.equal(final.r[23], 0);
    assert.equal(final.r[36]+16*final.r[39], 0x35);
    assert.equal(final.r[22], 7); assert.ok(lowerZero(final.st, 1));
    assert.ok(!events.some(e => e.ip === 0x93));
  } else if (spec.name === 'manual_sign') {
    assert.equal(firstLoss, 1262); assert.equal(events[firstLoss-1].ip, 0x91);
    assert.deepEqual(dispatches, [{command: 1197, vector: 0xD3, head: 0x9A,
      B7: 7, zeroST1: true, S1: 11, R32: 2, R35: 3}]);
    assert.equal(firstJoint, -1); assert.equal(decoder.length, 90);
  } else {
    assert.equal(formatter.length, 65); assert.equal(packet.length, 100);
    assert.equal(formatter[0].command, 1126);
    assert.equal(firstF, 1129);
    assert.equal(packet[0].command, 3439); assert.equal(packet[0].ip, 0xE1);
    assert.equal(firstJoint, spec.payload === 1 ? 3445 : 3446);
    const first = events[firstJoint];
    assert.ok(joint(first));
    assert.equal(events[3452].ip, 0xE2);
    assert.equal(events[3452].r[21], 1); assert.ok(lowerZero(events[3452].st));
    assert.equal(final.r[36]+16*final.r[39], 0xD6,
      'this mode-cycle suffix is NOT a return to the idle scanner');
  }
  if (mirror) {
    const plain = prepare(spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), initial.state, 'fresh unobserved preparation');
    finish(plain, spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), end.state, 'fresh whole suffix ALL5 mirror');
  }
  const report = {
    name: spec.name, keys: spec.keys, macros: spec.end,
    nativeKeyboardOnly: true, observerIndependent: mirror,
    initialB7: source.r[22], firstReadinessLoss: firstLoss,
    readinessLossCause: firstLoss > 0 ? events[firstLoss-1].ip : null,
    firstJointSevenZeroST0: firstJoint, firstWorkingA7F: firstF,
    dispatches, finalIp: final.r[36]+16*final.r[39],
    finalA: word(final.r), finalST0: word(final.st),
    all105Program56Ms15OrdinaryWordsHeld: true,
    nativeCF: false, nativeC3: false, nativeD4: false,
    ordinaryCSignFCreated: false, partialK2: false,
  };
  if (log) console.log(JSON.stringify(report));
  return {report, initial, origin, formatter, packet, decoder, end};
}

if (require.main === module) {
  if (process.argv.includes('--proof-input'))
    console.log(JSON.stringify(specs.map(spec => capture(spec, {log: false}))));
  else {
    for (const spec of specs) capture(spec);
    console.log('PASS native cancel/decoder/two mode cycles and four fresh whole ALL5 mirrors; '+
      'joint7/zeroST0 is transient inside forced packets, NOT nativeCF/C3 or partialK2.');
  }
}
module.exports = {specs, prepare, finish, capture};
