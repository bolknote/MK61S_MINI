#!/usr/bin/env node
'use strict';
// Read-only source-selected controls at the ORIGINAL1D resolver. Nothing
// in the reference is repaired; any later hypothesis is a detached model.
const assert = require('node:assert/strict');
const {prepare, jointSpec} = require('./cache-writer-flag-native.cjs');
const {reader} = require('./cache-cf-buffer-native.cjs');
const {trace} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const {rawMemoryRegister} = require('./check_ac_signature_keyboard.cjs');
const {layout, slots, locations} = require('./cache-d4-native-topology.cjs');
const specs = [{name: 'bc77_resolver_C0', C: 0}, {...jointSpec, name: 'bc77_resolver_joint'}];
const data = c => ({program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c), registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i))});
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
function capture(spec) {
  const c = prepare(spec), before = data(c);
  const readerInitial = {command: 0, state: machineSnapshot(c)}, readerOrigin = [], readerCore = [];
  const t = trace(c, reader, {extraIps: Array.from({length: 256}, (_, i) => i), fullState: true,
    otherChipsAt: e => {
      const save = () => ({command: e.command, ip: e.ip, slot: e.slot, state: machineSnapshot(c)});
      if (readerOrigin.length < 65) readerOrigin.push(save());
      if (e.command >= 1259 && e.command <= 1709) readerCore.push(save());
      return false;
    }, ringAt: e => e.command === 1264});
  assert.equal(t.events.length, 6720); assert.deepEqual(t.primitives, [0xC8]);
  assert.equal(t.events.find(e => e.ip === 0xC8).slot, 'W');
  const gate = readerCore.find(e => e.command === 1264), event = t.events[1264];
  assert.equal(event.ip, 0x1D); assert.equal(event.slot, 'V'); assert.equal(event.nextIp, 0x2E);
  assert.deepEqual([0, 26, 29, 32, 35, 38].map(j => event.r[j]), [3, 0, 8, 2, 5, 13]);
  assert.deepEqual([event.r[25], event.r[31]], [0, 9]);
  assert.deepEqual(Array.from({length: 12}, (_, i) => event.r[3*i]),
    [3, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 6]);
  assert.ok(event.command < t.events.find(e => e.ip === 0xC8).command,
    'stored600 at1D precedes the actual Ms/programme reader, not its cached output');
  assert.deepEqual([event.st[1], event.st[22], event.st[25]], spec.C ? [5, 1, 0] : [0, 0, 0]);
  assert.equal(event.st[30]+16*event.st[33], 0x99);
  assert.ok(!t.events.some(e => [0x25, 0x26, 0x28, 0x7E, 0x77, 0xBC, 0xBB, 0xD4, 0xF9].includes(e.ip)));
  for (const group of [readerOrigin, readerCore])
    assert.ok(group.every((e, i) => !i || e.command === group[i-1].command+1));
  assert.equal(readerOrigin.length, 65); assert.equal(readerCore.length, 451);
  assert.deepEqual(data(c), before);
  const readerEnd = {command: 6720, state: machineSnapshot(c)};
  const plain = prepare(spec); data(plain);
  assert.deepEqual(machineSnapshot(plain), readerInitial.state);
  reader(plain); data(plain); assert.deepEqual(machineSnapshot(plain), readerEnd.state);
  const report = {name: spec.name, numericJoint: Boolean(spec.C),
    nativeKeyboardOnly: true, observerIndependent: true, original1D: 1264, next: '2E',
    nativeA0: 3, nativeType: 2, nativeKind: 5, nativeR26: 0,
    nativeB8EqualsB10: false, nativeAIsStored600: true, nativeAIsProgrammeCache: false,
    native25: false, native77: false, nativeBC: false,
    all105Programme56Ms15OrdinaryHeld: true, partialK2: false};
  return {report, before, topology: topology(c), readerInitial, readerOrigin, readerCore,
    readerEnd, gate, gateRing: event.ring};
}
if (require.main === module) {
  const controls = specs.map(capture);
  console.log(JSON.stringify(process.argv.includes('--proof-input') ? controls : controls.map(c => c.report)));
}
module.exports = {specs, capture};
