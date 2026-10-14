#!/usr/bin/env node
'use strict';
// Source-selected seed0/seed5 controls and two proposed mode repairs.
// The reference receives ONLY ordinary public keys/frames. No ROM edits,
// state setters, address overrides or observer-dependent preparations.
const assert = require('node:assert/strict');
const {prepare: cold} = require('./cache-control-f-transfer-native.cjs');
const {prepare: marker} = require('./cache-da-keyboard.cjs');
const {fixture} = require('./cache-cf-constructor-native.cjs');
const {specs: payloads, setup: oldSetup, reader} = require('./cache-cf-buffer-native.cjs');
const {installArithmetic, finishSignature700, registerKey, rawMemoryRegister} =
  require('./check_ac_signature_keyboard.cjs');
const {trace, aligned} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const allIps = Array.from({length: 256}, (_, i) => i);
const word = (v, lane = 0) => Array.from({length: 12}, (_, i) =>
  v[3*i+lane].toString(16).toUpperCase()).join('');
const ready = e => e.r[22] === 7 &&
  Array.from({length: 8}, (_, i) => e.st[3*i+1]).every(n => n === 0);
const joint = e => e.r[21] === 7 &&
  Array.from({length: 8}, (_, i) => e.st[3*i]).every(n => n === 0);
const data = c => ({program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c), registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i))});
const specs = [
  {name: 'seed_five', seed: 5, keys: ['П→X', '9'], end: 6720, frames: 8},
  {name: 'seed_zero', seed: 0, keys: ['П→X', '9'], end: 6720, frames: 8},
  {name: 'step_after_five', keys: ['ШГ→'], end: 3360, frames: 2},
  {name: 'nop_after_five', keys: ['K', '0'], end: 5040, frames: 4},
];

function setupSeed(seed) {
  assert.ok(seed === 0 || seed === 5, 'two source-selected controls, not a digit search');
  const c = cold();
  c.inputNumber('0', {clear: true}).pressSequence(['X→П', registerKey(12)]); aligned(c);
  marker({fixture, calc: c, values: payloads[1].values});
  installArithmetic(c, {input: '1E75', multiplier: '1.0000003', store: 9});
  c.pressSequence(['В/О', 'С/П']).runFrames(12); aligned(c);
  assert.equal(rawMemoryRegister(c, 9), '600010000003');
  c.inputNumber('1', {clear: true}).pressSequence(['X→П', '2']);
  installArithmetic(c, {input: '1E87', multiplier: `1.000000${seed}E4`});
  finishSignature700(c); aligned(c);
  assert.equal(rawMemoryRegister(c, 9), '600010000003');
  assert.equal(rawMemoryRegister(c, 8), '9990FFFFFFF0');
  assert.equal(rawMemoryRegister(c, 12), '000000000000');
  return c;
}
function prepare(spec) {
  if (spec.seed !== undefined) return setupSeed(spec.seed);
  const c = oldSetup(payloads[1]); reader(c);
  c.pressSequence(['F', 'Сx']).runFrames(2); aligned(c);
  return c;
}
function finish(c, spec) {
  c.pressSequence(spec.keys).runFrames(spec.frames); aligned(c);
}

function capture(spec, {mirror = true, log = true} = {}) {
  const c = prepare(spec), before = data(c);
  const initial = {command: 0, state: machineSnapshot(c)};
  if (spec.name === 'seed_five') {
    const baseline = oldSetup(payloads[1]); data(baseline);
    assert.deepEqual(machineSnapshot(baseline), initial.state,
      'seed5 preparation is exactly the existing guarded preparation');
  }
  const origin = [], source = [], control = [];
  let sourceStarted = false, controlStarted = false;
  const t = trace(c, c => finish(c, spec), {
    extraIps: allIps, fullState: true,
    otherChipsAt: e => {
      const save = () => ({command: e.command, ip: e.ip, state: machineSnapshot(c)});
      if (origin.length < (spec.name === 'step_after_five' ? 100 : 65)) origin.push(save());
      if (spec.seed !== undefined) {
        if (e.ip === 0xAC && !source.length) sourceStarted = true;
        if (sourceStarted && source.length < 160) source.push(save());
      }
      if (spec.name === 'nop_after_five') {
        if (e.command >= 1120 && e.ip === 0x54 && !control.length) controlStarted = true;
        if (controlStarted && control.length < 100) control.push(save());
      }
      return false;
    },
  });
  assert.equal(t.events.length, spec.end);
  assert.ok(t.events.every((e, i) => e.command === i));
  for (const entries of [origin, source, control])
    assert.ok(entries.every((e, i) => !i || e.command === entries[i-1].command+1));
  const end = {command: spec.end, state: machineSnapshot(c)}, after = data(c);
  const events = t.events, final = end.state.ik1302;
  const gates = events.flatMap((e, i) => e.ip === 0x07 ? [{command: e.command,
    R2: e.r[2], R5: e.r[5], next: events[i+1].ip}] : []);
  const pairChanges = events.slice(0, -1).flatMap((e, i) => {
    const n = events[i+1];
    return e.r[2] === n.r[2] && e.r[5] === n.r[5] ? [] : [{command: e.command,
      ip: e.ip, before: [e.r[2], e.r[5]], after: [n.r[2], n.r[5]]}];
  });
  const firstC8 = events.findIndex(e => e.ip === 0xC8);
  const firstIdleAfterC8 = firstC8 < 0 ? -1 :
    events.findIndex((e, i) => i > firstC8 && e.ip === 0x35);
  const firstLoss = events.findIndex(e => !ready(e));
  const programChanges = before.program.flatMap((v, i) => v === after.program[i] ? [] :
    [{address: i, before: v, after: after.program[i]}]);
  const registerChanges = before.registers.flatMap((v, i) => v === after.registers[i] ? [] :
    [{register: i, before: v, after: after.registers[i]}]);
  assert.deepEqual(after.ms, before.ms, 'all56 Ms bytes held in these controls');
  assert.deepEqual(programChanges, [], 'all105 program bytes held in these controls');
  assert.deepEqual(registerChanges, [], 'all15 ordinary words held in these controls');
  assert.ok(!events.some(e => [0xCF, 0xC3, 0xD4].includes(e.ip)));
  if (spec.seed !== undefined) {
    assert.equal(source.length, 160); assert.equal(source[0].command, 1204);
    assert.equal(source[0].state.ik1302.r[1], spec.seed, 'actual AC.B0 source is the seed digit');
    assert.equal(source[0].state.ik1302.r[4], 0, 'actual AC.B1 supplies zero to saved mode');
    assert.deepEqual(gates[0], {command: 1302, R2: spec.seed, R5: 0,
      next: spec.seed === 5 ? 0x6D : 0x09});
    assert.equal(source.find(e => e.command === 1251).state.ik1302.r[2], spec.seed);
    if (spec.seed === 5) {
      assert.deepEqual(t.primitives, [0xC8]); assert.equal(firstC8, 1325);
      assert.equal(final.r[36]+16*final.r[39], 0x35);
      assert.deepEqual([final.r[2], final.r[5]], [0, 5]);
      assert.ok(ready({r: final.r, st: final.st}));
      assert.equal(word(final.r), '3AF4DF57F09F');
    } else {
      assert.deepEqual(t.primitives, []);
      assert.equal(final.r[36]+16*final.r[39], 0xE5);
      assert.deepEqual([final.r[2], final.r[5]], [0, 0]);
      assert.ok(!ready({r: final.r, st: final.st}));
    }
  } else if (spec.name === 'step_after_five') {
    assert.equal(firstLoss, 20); assert.equal(events[firstLoss-1].ip, 0x62);
    assert.equal(gates[0].R2, 5); assert.equal(gates[0].next, 0x6D);
    assert.deepEqual(t.primitives, []);
  } else {
    assert.equal(control.length, 100); assert.equal(control[0].command, 1127);
    assert.deepEqual([control[0].state.ik1302.r[2], control[0].state.ik1302.r[5]], [5, 0]);
    assert.equal(firstLoss, 1187); assert.equal(events[firstLoss-1].ip, 0x91);
    assert.deepEqual([final.r[2], final.r[5]], [0, 0]);
    assert.ok(!ready({r: final.r, st: final.st}));
    assert.deepEqual(t.primitives, []);
  }
  if (mirror) {
    const plain = prepare(spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), initial.state, 'fresh unobserved preparation');
    finish(plain, spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), end.state, 'fresh unobserved whole ALL5 suffix');
  }
  const report = {name: spec.name, seed: spec.seed, keys: spec.keys, macros: spec.end,
    firstReadinessLoss: firstLoss, firstJoint: events.findIndex(joint), gates,
    firstC8, firstIdleAfterC8, pairChanges,
    endMode: [final.r[2], final.r[5]], endIp: final.r[36]+16*final.r[39],
    endA: word(final.r), endB: word(final.r, 1), endST1: word(final.st, 1),
    finalReady: ready({r: final.r, st: final.st}), programChanges, registerChanges,
    all56MsBytesHeld: true, nativeKeyboardOnly: true, observerIndependent: mirror,
    ordinaryCSignFCreated: false, partialK2: false};
  if (log) console.log(JSON.stringify(report));
  return {report, initial, origin, source, control, end,
    tail: firstC8 < 0 ? [] : events.slice(firstC8, firstIdleAfterC8+1).map(e => e.ip)};
}
if (require.main === module) {
  if (process.argv.includes('--proof-input'))
    console.log(JSON.stringify(specs.map(s => capture(s, {log: false}))));
  else {
    for (const s of specs) capture(s);
    console.log('PASS four source-selected native controls / fresh whole ALL5 mirrors; '+
      'mode0 disables this reader; ШГ→ and K0 do not give a ready restore93 entry.');
  }
}
module.exports = {specs, setupSeed, prepare, finish, capture};
