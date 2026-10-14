#!/usr/bin/env node
'use strict';
// Native selector provenance: the complete reader uses4→C8 and later8;
// public K0 has S1=4 but R35=5:1F suppliesD, notC.14 clearsR26;
// laterDE suppliesF. Opcode subtype and the selector supplier are distinct.
// No IP/selector/type/counter/ROM is repaired, including in the mirror.
const assert = require('node:assert/strict');
const {prepare, jointSpec} = require('./cache-writer-flag-native.cjs');
const {reader} = require('./cache-cf-buffer-native.cjs');
const {trace, aligned} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const {rawMemoryRegister} = require('./check_ac_signature_keyboard.cjs');
const data = c => ({program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c), registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i))});
const finish = c => {c.pressSequence(['K', '0']).runFrames(2); aligned(c);};
const ip = a => a.r[36]+16*a.r[39];
function capture() {
  const c = prepare(jointSpec), before = data(c), readerInitial = {command: 0, state: machineSnapshot(c)};
  const readerOrigin = [], readerCore = [];
  const readTrace = trace(c, reader, {extraIps: Array.from({length: 256}, (_, i) => i), fullState: true,
    otherChipsAt: e => {
      const snapshot = () => ({command: e.command, ip: e.ip, state: machineSnapshot(c)});
      if (readerOrigin.length < 65) readerOrigin.push(snapshot());
      if (e.command >= 1290 && e.command <= 1709) readerCore.push(snapshot());
      return false;
    }});
  assert.equal(readTrace.events.length, 6720); assert.deepEqual(readTrace.primitives, [0xC8]);
  const dispatch = readTrace.events.filter(e => e.ip === 0x60);
  assert.deepEqual(dispatch.map(e => [e.command, e.r[38], e.r[32], e.r[23], e.nextIp]), [
    [1312, 4, 0, 1, 0x61], [1318, 4, 0, 1, 0x61], [1324, 4, 0, 1, 0xC8],
    [1429, 8, 12, 1, 0x61], [1534, 8, 12, 1, 0x61], [1639, 8, 12, 1, 8]]);
  assert.ok(dispatch.every(e => e.r[32] === 0 || e.r[38] === 8 || e.r[23] === 0));
  assert.ok(dispatch.every(e => e.nextIp !== 0x48));
  assert.deepEqual(data(c), before);
  const initial = {command: 0, state: machineSnapshot(c)}, readerEnd = {command: 6720, state: initial.state};
  assert.equal(ip(initial.state.ik1302), 0x35);
  assert.deepEqual([0, 3, 9, 12, 18, 21].map(j => initial.state.ik1302.r[j]), [3, 10, 4, 13, 5, 7]);
  const origin = [], core = [];
  const t = trace(c, finish, {extraIps: Array.from({length: 256}, (_, i) => i), fullState: true,
    otherChipsAt: e => {
      const snapshot = () => ({command: e.command, ip: e.ip, state: machineSnapshot(c)});
      if (origin.length < 65) origin.push(snapshot());
      if (e.command >= 1149 && e.command <= 1219) core.push(snapshot());
      return false;
    }});
  assert.equal(t.events.length, 3360);
  for (const group of [readerOrigin, readerCore, origin, core])
    assert.ok(group.every((e, i) => !i || e.command === group[i-1].command+1));
  assert.equal(readerOrigin.length, 65); assert.equal(readerCore.length, 420);
  assert.equal(origin.length, 65); assert.equal(core.length, 71);
  const selector = t.events[1158], imported = t.events[1159], clear = t.events[1160];
  assert.equal(selector.ip, 0x1F); assert.equal(selector.s1, 4); assert.equal(selector.r[35], 5);
  assert.equal(imported.ip, 0x14);
  assert.deepEqual([imported.r[38], imported.r[23]], [13, 0]);
  assert.equal(clear.ip, 0xD3); assert.equal(clear.r[26], 0);
  assert.equal(t.events[1199].ip, 0xDE); assert.equal(t.events[1200].r[38], 15);
  assert.ok(!t.events.some(e => [0x60, 0xBC, 0xBB, 0xC9, 0xF9, 0xD4].includes(e.ip)));
  assert.deepEqual(data(c), before);
  const end = {command: 3360, state: machineSnapshot(c)}; assert.equal(ip(end.state.ik1302), 0xE5);
  const plain = prepare(jointSpec); data(plain);
  assert.deepEqual(machineSnapshot(plain), readerInitial.state);
  reader(plain); data(plain); assert.deepEqual(machineSnapshot(plain), initial.state);
  finish(plain); data(plain); assert.deepEqual(machineSnapshot(plain), end.state);
  const report = {name: 'bc60_reader_and_native_D_selector', keys: ['K', '0'],
    nativeKeyboardOnly: true, observerIndependent: true,
    readerDispatch: dispatch.map(e => ({command: e.command, selector: e.r[38], type: e.r[32],
      counter: e.r[23], equality: e.r[25] === e.r[31], next: e.nextIp.toString(16)})),
    nativeSelectorCConstructor: false, nativeSelectorDConstructor: '1F/1158 with R35=5/S1=4', counterAtD: 0,
    R26ClearedBy14: true, lateSelectorFConstructor: 'DE/1199',
    all105Programme56Ms15OrdinaryHeld: true, native60to48: false, nativeBC: false, partialK2: false};
  return {report, before, readerInitial, readerOrigin, readerCore, readerEnd, initial, origin, core, end};
}
if (require.main === module) {
  const result = capture(); console.log(JSON.stringify(process.argv.includes('--proof-input') ? result : result.report));
}
module.exports = {capture};
