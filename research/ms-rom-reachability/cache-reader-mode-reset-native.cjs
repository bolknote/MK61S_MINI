#!/usr/bin/env node
'use strict';
// Source-selected F/В↑ control for the alternative79 decoder route.
// The fresh stock reference gets public keys only; all observers are passive.
const assert = require('node:assert/strict');
const {prepare: oldPrepare, specs: oldSpecs} = require('./cache-reader-mode-origin-native.cjs');
const {trace, aligned} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const {rawMemoryRegister} = require('./check_ac_signature_keyboard.cjs');
const allIps = Array.from({length: 256}, (_, i) => i);
const word = (v, lane = 0) => Array.from({length: 12}, (_, i) =>
  v[3*i+lane].toString(16).toUpperCase()).join('');
const ready = e => e.r[22] === 7 &&
  Array.from({length: 8}, (_, i) => e.st[3*i+1]).every(n => n === 0);
const data = c => ({program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c), registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i))});
const spec = {name: 'up_after_reader', keys: ['F', 'В↑'], end: 3360, frames: 2};
const prepare = () => oldPrepare(oldSpecs[2]);
const finish = c => { c.pressSequence(spec.keys).runFrames(spec.frames); aligned(c); };

function capture({mirror = true, log = true} = {}) {
  const c = prepare(), before = data(c), initial = {command: 0, state: machineSnapshot(c)};
  const origin = [], decoder = [];
  let started = false;
  const result = trace(c, c => finish(c), {extraIps: allIps, fullState: true,
    otherChipsAt: e => {
      const save = () => ({command: e.command, ip: e.ip, state: machineSnapshot(c)});
      if (origin.length < 65) origin.push(save());
      if (e.ip === 0x79 && !decoder.length) started = true;
      if (started && decoder.length < 160) decoder.push(save());
      return false;
    }});
  const events = result.events, end = {command: spec.end, state: machineSnapshot(c)}, after = data(c);
  assert.equal(events.length, spec.end);
  assert.ok(events.every((e, i) => e.command === i));
  for (const entries of [origin, decoder])
    assert.ok(entries.every((e, i) => !i || e.command === entries[i-1].command+1));
  const firstLoss = events.findIndex(e => !ready(e)), final = end.state.ik1302;
  assert.equal(origin.length, 65); assert.equal(decoder.length, 160);
  assert.equal(decoder[0].command, 1123); assert.equal(decoder[0].ip, 0x79);
  assert.equal(firstLoss, 1142); assert.equal(events[firstLoss-1].ip, 0x92);
  const preserved = decoder.find(e => e.command === 1152);
  assert.equal(preserved.ip, 0x8D);
  assert.deepEqual([preserved.state.ik1302.r[2], preserved.state.ik1302.r[5]], [0, 0]);
  for (const i of [0, 3, 9, 12, 18, 21])
    assert.equal(preserved.state.ik1302.r[i], initial.state.ik1302.r[i], 'raw6 held at native zero-mode8D');
  assert.equal(decoder.find(e => e.ip === 0xEE).command, 1168);
  assert.deepEqual([final.r[2], final.r[5]], [0, 0]);
  assert.equal(final.r[36]+16*final.r[39], 0xE5);
  assert.equal(word(final.r), '000000000000'); assert.ok(!ready(final));
  const changed = (field, values, other) => values.flatMap((v, i) => v === other[i] ? [] :
    [{[field]: i, before: v, after: other[i]}]);
  const programChanges = changed('address', before.program, after.program);
  const registerChanges = changed('register', before.registers, after.registers);
  assert.deepEqual(after.ms, before.ms, 'all56 Ms bytes held');
  assert.deepEqual(programChanges, [], 'all105 program bytes held');
  assert.deepEqual(registerChanges, [], 'all15 ordinary words held');
  assert.deepEqual(result.primitives, []);
  assert.ok(!events.some(e => [0xCF, 0xC3, 0xD4].includes(e.ip)));
  if (mirror) {
    const plain = prepare(); data(plain);
    assert.deepEqual(machineSnapshot(plain), initial.state, 'fresh unobserved preparation');
    finish(plain); data(plain);
    assert.deepEqual(machineSnapshot(plain), end.state, 'fresh whole ALL5 suffix mirror');
  }
  const report = {...spec, first79: events.findIndex(e => e.ip === 0x79),
    zeroModeRawCacheAt8D: preserved.command, firstEEAfter79: 1168,
    decoder: decoder.slice(0, 36).map(e => e.ip), firstReadinessLoss: firstLoss,
    lossCause: firstLoss > 0 ? events[firstLoss-1].ip : null,
    endIp: final.r[36]+16*final.r[39], endMode: [final.r[2], final.r[5]],
    endA: word(final.r), endB: word(final.r, 1), endST1: word(final.st, 1), finalReady: ready(final),
    programChanges, registerChanges, all56MsBytesHeld: true,
    nativeKeyboardOnly: true, observerIndependent: mirror,
    ordinaryCSignFCreated: false, partialK2: false};
  if (log) console.log(JSON.stringify(report));
  return {report, initial, origin, decoder, end};
}
if (require.main === module) {
  if (process.argv.includes('--proof-input')) console.log(JSON.stringify(capture({log: false})));
  else capture();
}
module.exports = {spec, prepare, finish, capture};
