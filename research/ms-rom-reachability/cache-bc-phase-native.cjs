#!/usr/bin/env node
'use strict';
// The exact ring tags distinguish working words from Ms. No added wait:
// native54 has type0; the later TYPE3 hypothesis never changes this reference.
const assert = require('node:assert/strict');
const {prepare, jointSpec} = require('./cache-writer-flag-native.cjs');
const {reader} = require('./cache-cf-buffer-native.cjs');
const {trace, aligned} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const {rawMemoryRegister} = require('./check_ac_signature_keyboard.cjs');
const {layout, slots, locations} = require('./cache-d4-native-topology.cjs');
const specs = [{name: 'bc_phase_C0', C: 0}, {name: 'bc_phase_joint', C: jointSpec.C,
  value: jointSpec.value, rawC: jointSpec.rawC, ST10: jointSpec.ST10}]
  .map(spec => ({...spec, keys: ['K', '6'], waitMacros: 0, end: 3360, start: 1119, last: 1299}));
// Source-selected9 offsets the exact type0 cleanup operand decrement by3.
// It constructs type3/operand6 at48, NOT a type3 inlet at54.
const typeSpec = {...specs[1], name: 'bc_type_K9_joint', keys: ['K', '9'], last: 1379};
const data = c => ({program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c), registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i))});
const ip = a => a.r[36]+16*a.r[39];
const raw = [0, 3, 9, 12, 18, 21];
function finish(c, spec) { c.pressSequence(spec.keys).runFrames(2); aligned(c); }
function topology(c) {
  const locate = (chip, index) => {
    const p = locations.findIndex(([id, end]) => id === chip && index >= end-41 && index <= end);
    assert.ok(p >= 0); return {slot: slots[p], n: index-(locations[p][1]-41)};
  };
  return {registerPages: layout().registerPages, programMap: Array.from({length: 105}, (_, i) => {
    const [chip, n] = c.commandAddress(i, 1);
    return {hi: locate(chip, n), lo: locate(chip, n-3)};
  })};
}

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
  assert.deepEqual(data(c), before);
  const initial = {command: 0, state: machineSnapshot(c)}, readerEnd = {command: 6720, state: initial.state};
  const origin = [], core = [];
  const t = trace(c, c => finish(c, spec), {extraIps: Array.from({length: 256}, (_, i) => i), fullState: true,
    otherChipsAt: e => {
      const save = () => ({command: e.command, ip: e.ip, slot: e.slot, state: machineSnapshot(c)});
      if (origin.length < 65) origin.push(save());
      if (e.command >= spec.start && e.command <= spec.last) core.push(save());
      return false;
    }});
  assert.equal(t.events.length, spec.end); assert.ok(t.events.every((e, i) => e.command === i));
  for (const group of [readerOrigin, readerCore, origin, core])
    assert.ok(group.every((e, i) => !i || e.command === group[i-1].command+1));
  assert.equal(readerOrigin.length, 65); assert.equal(readerCore.length, 375);
  assert.equal(origin.length, 65); assert.equal(core.length, spec.last-spec.start+1);
  const gate = core.find(e => e.command === 1127), e = t.events[1127];
  const typeControl = spec.keys[1] === '9', operand = typeControl ? 9 : 6;
  assert.equal(e.ip, 0x54); assert.equal(e.slot, 'T');
  assert.deepEqual([e.r[29], e.r[32], e.r[2], e.r[5]], [operand, 0, 5, 0]);
  assert.deepEqual([e.st[1], e.st[22], e.st[25]], spec.C ? [5, 1, 0] : [0, 0, 0]);
  assert.equal(e.st[30]+16*e.st[33], 0x99); assert.equal(e.pc, 0x90);
  assert.deepEqual(raw.map(j => e.r[j]), raw.map(j => initial.state.ik1302.r[j]));
  assert.deepEqual(t.events.slice(1127, 1139).map(e => e.ip),
    [0x54, 0x56, 0x65, 0x7B, 0xB7, 0x45, 0x8B, 0x48, 0x4A, 0x4C, 0x4E, 0x97]);
  assert.deepEqual(t.primitives, []);
  assert.ok(!t.events.some(e => [0xBC, 0xBB, 0xC9, 0xF9, 0xD4,
    ...(typeControl ? [] : [0xBE])].includes(e.ip)));
  if (typeControl) {
    const typed = t.events[1134], be = t.events[1350];
    assert.equal(typed.ip, 0x48); assert.equal(typed.slot, 'P9');
    assert.deepEqual([typed.r[32], typed.r[29], typed.r[23]], [3, 6, 0]);
    assert.deepEqual([typed.st[1], typed.st[22], typed.st[25]], [5, 1, 0]);
    assert.deepEqual(t.events.slice(1134, 1138).map(v => v.ip), [0x48, 0x4A, 0x4C, 0x4E]);
    assert.equal(be.ip, 0xBE);
    assert.deepEqual([be.r[2], be.r[23], be.r[26]], [5, 0, 0]);
    assert.ok(t.events.filter(v => v.ip === 0x54).every(v => v.r[32] === 0));
  }
  const after = data(c), end = {command: spec.end, state: machineSnapshot(c)};
  assert.deepEqual(after, before, 'all105/56/15 held by COMPLETE unmodified native control');
  assert.equal(ip(end.state.ik1302), typeControl ? 0x35 : 0xE5);
  if (mirror) {
    const plain = prepare(spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), readerInitial.state);
    reader(plain); data(plain); assert.deepEqual(machineSnapshot(plain), initial.state);
    finish(plain, spec); data(plain); assert.deepEqual(machineSnapshot(plain), end.state);
  }
  const report = {...spec, nativeKeyboardOnly: true, observerIndependent: mirror,
    first54: 1127, first54Slot: 'T', operand, nativeType: 0,
    type3Operand6At48: typeControl, nativeType3At54: false,
    numericJoint: Boolean(spec.C), nativeByte: 0x90, numericTarget: 0x99,
    all105Programme56Ms15OrdinaryHeld: true, nativeBC: false, nativeWriter: false, partialK2: false};
  if (log) console.log(JSON.stringify(report));
  return {report, before, after, topology: topology(c), readerInitial, readerOrigin, readerCore,
    readerEnd, initial, origin, core, gate, end};
}
if (require.main === module) {
  if (process.argv.includes('--type-proof-input')) console.log(JSON.stringify(capture(typeSpec, {log: false})));
  else if (process.argv.includes('--proof-input')) console.log(JSON.stringify(specs.map(spec => capture(spec, {log: false}))));
  else specs.forEach(spec => capture(spec));
}
module.exports = {specs, typeSpec, prepare, finish, capture};
