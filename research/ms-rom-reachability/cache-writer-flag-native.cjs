#!/usr/bin/env node
'use strict';
// Source-directed C0/C1 intervention, public keys ONLY. Numeric ST1[7]
// really changes; no pending flag, byte, PC, return or ROM is repaired.
// The first D3 chooses D5 in all four controls. This is not partialK2.
const assert = require('node:assert/strict');
const {prepare: cold} = require('./cache-control-f-transfer-native.cjs');
const {prepare: marker} = require('./cache-da-keyboard.cjs');
const {prepareSelector} = require('./st34-origin-trace.cjs');
const {finishSignature700, registerKey, rawMemoryRegister} = require('./check_ac_signature_keyboard.cjs');
const {fixture} = require('./cache-cf-constructor-native.cjs');
const {reader} = require('./cache-cf-buffer-native.cjs');
const {trace, aligned} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const data = c => ({program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c), registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i))});
const code = e => e.r[30]+16*e.r[33];
const ip = a => a.r[36]+16*a.r[39];
const specs = [0, 1].flatMap(C => [
  {name: 'nop_C'+C, C, kind: 'nop', keys: ['K', '0'], end: 3360, start: 1119, last: 1249},
  {name: 'call_C'+C, C, kind: 'call', keys: ['K', 'ПП', '8'], end: 5040, start: 2239, last: 2415},
]);
const jointSpec = {name: 'nop_joint', C: 1, value: '1.0000005', rawC: '000010000005',
  ST10: 5, lateJoint: true, kind: 'nop', keys: ['K', '0'], end: 3360, start: 1119, last: 1249};

function prepare(spec) {
  const c = cold();
  c.inputNumber(spec.value ?? String(spec.C), {clear: true}).pressSequence(['X→П', registerKey(12)]); aligned(c);
  marker({fixture, calc: c, values: '7.7754327E-91'});
  prepareSelector(c, {selector: 9}); finishSignature700(c); aligned(c);
  assert.equal(rawMemoryRegister(c, 12), spec.rawC ?? (spec.C ? '000010000000' : '000000000000'));
  return c;
}
function finish(c, spec) { c.pressSequence(spec.keys).runFrames(2); aligned(c); }

function capture(spec, {mirror = true, log = true} = {}) {
  const c = prepare(spec), before = data(c), readerInitial = {command: 0, state: machineSnapshot(c)};
  const readerOrigin = [], readerCore = [];
  const rd = trace(c, reader, {
    extraIps: Array.from({length: 256}, (_, i) => i), fullState: true,
    otherChipsAt: e => {
      const save = () => ({command: e.command, ip: e.ip, slot: e.slot, state: machineSnapshot(c)});
      if (readerOrigin.length < 65) readerOrigin.push(save());
      if (e.command >= 1325 && e.command <= 1699) readerCore.push(save());
      return false;
    },
  });
  assert.equal(rd.events.length, 6720); assert.deepEqual(rd.primitives, [0xC8]);
  assert.equal(rd.events.find(e => e.ip === 0xC8).slot, 'W', 'actual Ms reader, not ordinary working X');
  assert.deepEqual(data(c), before, 'whole reader preserves105/56/15');
  const initial = {command: 0, state: machineSnapshot(c)}, readerEnd = {command: 6720, state: initial.state};
  assert.equal(ip(initial.state.ik1302), 0x35);
  assert.deepEqual([0, 3, 9, 12, 18, 21].map(j => initial.state.ik1302.r[j]), [3, 10, 4, 13, 5, 7]);
  assert.equal(initial.state.ik1302.r[23], 1);
  assert.equal(initial.state.ik1302.st[22], spec.C, 'ordinary C really supplies numeric ST1[7]');
  assert.equal(initial.state.ik1302.st[1], spec.ST10 ?? 0, 'independent numeric ST1[0] is source-selected too');
  const origin = [], core = [];
  const t = trace(c, c => finish(c, spec), {
    extraIps: Array.from({length: 256}, (_, i) => i), fullState: true,
    otherChipsAt: e => {
      const save = () => ({command: e.command, ip: e.ip, slot: e.slot, state: machineSnapshot(c)});
      if (origin.length < 65) origin.push(save());
      if (e.command >= spec.start && e.command <= spec.last) core.push(save());
      return false;
    },
  });
  assert.equal(t.events.length, spec.end);
  assert.ok(t.events.every((e, i) => e.command === i));
  for (const group of [readerOrigin, readerCore, origin, core])
    assert.ok(group.every((e, i) => !i || e.command === group[i-1].command+1));
  assert.equal(readerOrigin.length, 65); assert.equal(readerCore.length, 375);
  assert.equal(origin.length, 65); assert.equal(core.length, spec.last-spec.start+1);
  assert.deepEqual(t.primitives, []);
  assert.ok(!t.events.some(e => [0xC9, 0xF9, 0xBB, 0xBC].includes(e.ip)),
    'the COMPLETE suffix contains no C9/F9 programme writer or BB/BC M2 writer');
  const numericWrites = t.events.filter(e => e.ip === 0xD4).map(e => ({command: e.command, slot: e.slot}));
  assert.deepEqual(numericWrites, spec.kind === 'call' ? [{command: 2336, slot: 'marker'}] : []);
  const gate = t.events.find(e => e.ip === 0xD3), ee = t.events.find(e => e.ip === 0xEE);
  const restore = t.events.find(e => e.ip === 0x91);
  assert.ok(gate && ee && restore); assert.ok(restore.command > gate.command);
  assert.deepEqual([gate.r[2], gate.r[23], gate.r[26], gate.st[22]], [5, 0, 0, spec.C]);
  assert.equal(t.events[gate.command+1].ip, 0xD5);
  assert.equal(t.events[gate.command+2].r[30]+16*t.events[gate.command+2].r[33], 0xFF);
  assert.equal(ee.slot, 'X', 'first numeric source is working X, NOT MsW');
  const imported = ee.m[31]+16*ee.m[34];
  assert.equal(code(t.events[ee.command+1]), imported, 'EE input byte has exact numeric M2 provenance');
  const late = t.events.find(e => e.command > restore.command && e.r[23] === spec.C);
  assert.ok(late);
  if (spec.C) { assert.equal(late.command, restore.command+2); assert.equal(late.ip, 0x93); }
  if (spec.kind === 'nop') {
    assert.equal(gate.command, 1160); assert.equal(restore.command, 1186);
    assert.equal(ee.command, 1154); assert.equal(imported, 0x60); assert.equal(code(gate), 0x60);
    const branch = t.events[1158], clear = t.events[1159];
    assert.equal(branch.ip, 0x1F); assert.equal(branch.s1, 4); assert.equal(clear.ip, 0x14);
    assert.equal(clear.pc, 0x90); assert.equal(gate.pc, clear.pc);
    const zero = t.events.find(e => e.ip === 0x54);
    assert.ok(zero && zero.command === 1127);
    assert.equal(t.events[zero.command+1].r[23], 0);
    assert.ok(!t.events.slice(zero.command+1, gate.command+1).some(e => e.ip === 0x91));
  } else {
    assert.equal(gate.command, 2345); assert.equal(restore.command, 2371);
    assert.equal(ee.command, 2279);
    const coupling = t.events.find(e => e.ip === 0x74);
    assert.ok(coupling && coupling.command === 2343);
    assert.equal(coupling.pc, 0x89); assert.equal(code(coupling), 0xF0);
    assert.equal(t.events[coupling.command+1].pc, 0xF0);
    assert.equal(gate.pc, 0xF0); assert.equal(code(gate), 0xF0);
  }
  let lateWriterFields = null;
  if (spec.lateJoint) {
    const joint = t.events[1198], coupled = t.events[1199], replaced = t.events[1200];
    assert.equal(joint.ip, 0xE4);
    assert.deepEqual([joint.r[2], joint.r[23], joint.r[26]], [5, 1, 0],
      'all three writer fields are prepared natively after the COMPLETE original91');
    assert.equal(joint.pc, 0xF9); assert.equal(code(joint), 0x60);
    assert.equal(coupled.ip, 0xDE); assert.equal(coupled.pc, 0x60);
    assert.equal(replaced.ip, 0xD6); assert.equal(code(replaced), 0xF0);
    assert.equal(replaced.r[23], 7);
    lateWriterFields = {command: 1198, ip: 0xE4, mode: 5, R23: 1, R26: 0,
      byte: 0x60, PC: 0xF9, next: 0xDE, coupledPC: 0x60, replacedByte: 0xF0,
      sourceIsWorkingX: true, originalReturnIsNotBE: true};
  }
  const after = data(c), end = {command: spec.end, state: machineSnapshot(c)};
  assert.deepEqual(after, before, 'all105 programme bytes/56 Ms bytes/15 ordinary words held');
  assert.equal(ip(end.state.ik1302), 0xE5);
  if (mirror) {
    const plain = prepare(spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), readerInitial.state, 'fresh unobserved preparation');
    reader(plain); data(plain);
    assert.deepEqual(machineSnapshot(plain), initial.state, 'fresh unobserved COMPLETE reader');
    finish(plain, spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), end.state, 'fresh unobserved COMPLETE suffix');
  }
  const report = {...spec, nativeKeyboardOnly: true, observerIndependent: mirror,
    initialST1Seven: spec.C, initialInputFlag: 1,
    firstD3: gate.command, gateMode: 5, gateR26: 0, gateR23: 0,
    gateByte: code(gate), gatePC: gate.pc, firstEE: ee.command, firstEESlot: ee.slot,
    firstEEImportedByte: imported, first91: restore.command,
    firstLateMatchingFlag: late.command, numericM1Writes: numericWrites, lateWriterFields,
    destinationCoupledToByte: spec.kind === 'call',
    all105Programme56Ms15OrdinaryHeld: true, nativeFlagRepair: false,
    nativeJointWriterFieldsPrepared: Boolean(spec.lateJoint),
    persistentMsCopy: false, partialK2: false};
  if (log) console.log(JSON.stringify(report));
  return {report, readerInitial, readerOrigin, readerCore, readerEnd, initial, origin, core, end};
}
if (require.main === module) {
  const selected = process.argv.includes('--joint') ? [jointSpec] : specs;
  if (process.argv.includes('--proof-input'))
    console.log(JSON.stringify(selected.map(spec => capture(spec, {log: false}))));
  else selected.forEach(spec => capture(spec));
}
module.exports = {specs, jointSpec, prepare, finish, capture};
