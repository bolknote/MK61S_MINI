#!/usr/bin/env node
'use strict';
// Source-selected ordinary X→П0 control after the Ms reader. All mutations
// are public keys in a fresh protected stock reference. D4 really writes
// ordinary P0, so this test MUST NOT claim that all15 registers are held.
const assert = require('node:assert/strict');
const {prepare, jointSpec} = require('./cache-writer-flag-native.cjs');
const {reader} = require('./cache-cf-buffer-native.cjs');
const {trace, aligned} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const {rawMemoryRegister} = require('./check_ac_signature_keyboard.cjs');
const specs = [{name: 'store_C0', C: 0}, {name: 'store_joint', C: jointSpec.C,
  value: jointSpec.value, rawC: jointSpec.rawC, ST10: jointSpec.ST10}]
  .map(spec => ({...spec, keys: ['X→П', '0'], end: 3360, start: 1119, last: 1259}));
const data = c => ({program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c), registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i))});
const code = e => e.r[30]+16*e.r[33];
const ip = a => a.r[36]+16*a.r[39];
function finish(c, spec) { c.pressSequence(spec.keys).runFrames(2); aligned(c); }

function capture(spec, {mirror = true, log = true} = {}) {
  const c = prepare(spec), before = data(c);
  const readerInitial = {command: 0, state: machineSnapshot(c)}, readerOrigin = [], readerCore = [];
  const rd = trace(c, reader, {extraIps: Array.from({length: 256}, (_, i) => i), fullState: true,
    otherChipsAt: e => {
      const save = () => ({command: e.command, ip: e.ip, slot: e.slot, state: machineSnapshot(c)});
      if (readerOrigin.length < 65) readerOrigin.push(save());
      if (e.command >= 1325 && e.command <= 1699) readerCore.push(save());
      return false;
    }});
  assert.equal(rd.events.length, 6720); assert.deepEqual(rd.primitives, [0xC8]);
  assert.equal(rd.events.find(e => e.ip === 0xC8).slot, 'W');
  assert.deepEqual(data(c), before, 'complete reader preserves105/56/15');
  const initial = {command: 0, state: machineSnapshot(c)}, readerEnd = {command: 6720, state: initial.state};
  assert.equal(ip(initial.state.ik1302), 0x35);
  assert.equal(initial.state.ik1302.r[23], 1);
  assert.deepEqual([initial.state.ik1302.st[1], initial.state.ik1302.st[22], initial.state.ik1302.st[25]],
    spec.name === 'store_joint' ? [5, 1, 0] : [0, 0, 0]);
  const origin = [], core = [];
  const t = trace(c, c => finish(c, spec), {
    extraIps: Array.from({length: 256}, (_, i) => i), fullState: true,
    otherChipsAt: e => {
      const save = () => ({command: e.command, ip: e.ip, slot: e.slot, state: machineSnapshot(c)});
      if (origin.length < 65) origin.push(save());
      if (e.command >= spec.start && e.command <= spec.last) core.push(save());
      return false;
    }});
  assert.equal(t.events.length, spec.end);
  assert.ok(t.events.every((e, i) => e.command === i));
  for (const group of [readerOrigin, readerCore, origin, core])
    assert.ok(group.every((e, i) => !i || e.command === group[i-1].command+1));
  assert.equal(readerOrigin.length, 65); assert.equal(readerCore.length, 375);
  assert.equal(origin.length, 65); assert.equal(core.length, spec.last-spec.start+1);
  assert.deepEqual(t.primitives, []);
  assert.ok(!t.events.some(e => [0x47, 0x49, 0x82, 0xBD, 0xBE, 0x63, 0xC9, 0xF9, 0xBB, 0xBC].includes(e.ip)),
    'complete ordinary store suffix does not supply either original BE writer caller');
  const writes = t.events.filter(e => e.ip === 0xD4).map(e => ({command: e.command, slot: e.slot}));
  assert.deepEqual(writes, [{command: 1173, slot: 'U'}], 'actual numeric M1 write, NOT Ms M2');
  const gate = t.events[1177], restore = t.events[1201], late = t.events[1213];
  assert.equal(gate.ip, 0xD3); assert.equal(gate.pc, 0x90); assert.equal(code(gate), 0x36);
  assert.deepEqual([gate.r[2], gate.r[23], gate.r[26]], [5, 0, 0]);
  assert.equal(t.events[1178].ip, 0xD5);
  assert.equal(restore.ip, 0x91); assert.equal(late.ip, 0xE4);
  assert.deepEqual([late.r[2], late.r[23], late.r[26]], spec.name === 'store_joint' ? [5, 1, 0] : [0, 0, 0]);
  assert.equal(code(late), 0x60); assert.equal(late.pc, 0xF9);
  assert.equal(t.events[1214].ip, 0xDE); assert.equal(t.events[1214].pc, 0x60);
  assert.equal(t.events[1215].ip, 0xD6); assert.equal(code(t.events[1215]), 0xF0);
  const after = data(c), end = {command: spec.end, state: machineSnapshot(c)};
  assert.deepEqual(after.program, before.program, 'all105 programme bytes held');
  assert.deepEqual(after.ms, before.ms, 'all56 Ms bytes held');
  assert.equal(before.registers[0], '004010000005'); assert.equal(after.registers[0], '600010000003');
  assert.deepEqual(after.registers.slice(1), before.registers.slice(1), 'other14 ordinary words held');
  assert.equal(ip(end.state.ik1302), 0xE5);
  if (mirror) {
    const plain = prepare(spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), readerInitial.state, 'fresh completely unobserved preparation');
    reader(plain); data(plain);
    assert.deepEqual(machineSnapshot(plain), initial.state, 'fresh unobserved complete reader');
    finish(plain, spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), end.state, 'fresh unobserved complete suffix');
  }
  const report = {...spec, nativeKeyboardOnly: true, observerIndependent: mirror,
    all105Programme56MsHeld: true, other14OrdinaryHeld: true,
    changedP0: {before: before.registers[0], after: after.registers[0]}, numericM1Writes: writes,
    firstD3: 1177, first91: 1201, lateReturn: 1213, lateReturnIP: 0xE4,
    lateJointWriterFields: spec.name === 'store_joint', originalBEWriterCaller: false,
    persistentMsCopy: false, partialK2: false};
  if (log) console.log(JSON.stringify(report));
  return {report, readerInitial, readerOrigin, readerCore, readerEnd, initial, origin, core, end};
}
if (require.main === module) {
  if (process.argv.includes('--proof-input')) console.log(JSON.stringify(specs.map(spec => capture(spec, {log: false}))));
  else specs.forEach(spec => capture(spec));
}
module.exports = {specs, prepare, finish, capture};
