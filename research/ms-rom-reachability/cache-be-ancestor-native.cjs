#!/usr/bin/env node
'use strict';
// A fixed source-selected digit control reaches ORIGINAL49/full91/BE.
// This is a real keyboard entry at BE, NOT a writer: R23 is0 there.
// The numeric M2/X write is reported, not confused with an Ms export.
const assert = require('node:assert/strict');
const {prepare, jointSpec} = require('./cache-writer-flag-native.cjs');
const {reader} = require('./cache-cf-buffer-native.cjs');
const {trace, aligned} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const {rawMemoryRegister} = require('./check_ac_signature_keyboard.cjs');
const specs = [{name: 'be_digit_C0', C: 0}, {name: 'be_digit_joint', C: jointSpec.C,
  value: jointSpec.value, rawC: jointSpec.rawC, ST10: jointSpec.ST10}]
  .map(spec => ({...spec, keys: ['F', 'Сx', '1'], end: 5040, start: 2255, last: 2379}));
const raw = [0, 3, 9, 12, 18, 21];
const data = c => ({program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c), registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i))});
const ip = a => a.r[36]+16*a.r[39];
const byte = e => e.r[30]+16*e.r[33];
const triple = (e, lane) => [e.st[lane], e.st[21+lane], e.st[24+lane]];
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
  assert.deepEqual(data(c), before, 'whole reader preserves105/56/15');
  const initial = {command: 0, state: machineSnapshot(c)}, readerEnd = {command: 6720, state: initial.state};
  assert.equal(ip(initial.state.ik1302), 0x35); assert.equal(initial.state.ik1302.r[23], 1);
  const origin = [], core = [];
  const t = trace(c, c => finish(c, spec), {
    extraIps: Array.from({length: 256}, (_, i) => i), fullState: true, allWrites: true,
    otherChipsAt: e => {
      const save = () => ({command: e.command, ip: e.ip, slot: e.slot, state: machineSnapshot(c)});
      if (origin.length < 65) origin.push(save());
      if (e.command >= spec.start && e.command <= spec.last) core.push(save());
      return false;
    }});
  const es = t.events;
  assert.equal(es.length, spec.end); assert.ok(es.every((e, i) => e.command === i));
  for (const group of [readerOrigin, readerCore, origin, core])
    assert.ok(group.every((e, i) => !i || e.command === group[i-1].command+1));
  assert.equal(readerOrigin.length, 65); assert.equal(readerCore.length, 375);
  assert.equal(origin.length, 65); assert.equal(core.length, spec.last-spec.start+1);
  assert.deepEqual(t.primitives, []);
  assert.ok(!es.some(e => [0xC9, 0xF9, 0xBB, 0xBC, 0xD4].includes(e.ip)),
    'complete suffix contains no programme/Ms writer or numeric M1/D4 write');
  const first8C = core.find(e => e.command === 2264), a = es[2264], restored = es[2277];
  assert.equal(a.ip, 0x8C); assert.deepEqual([a.r[2], a.r[23], a.r[26], a.s1, a.r[41]], [5, 0, 0, 1, 0]);
  assert.deepEqual(triple(a, 2), [5, 1, 0], 'joint third buffer exists BEFORE the first full restore');
  assert.equal(a.st[25], 0); assert.equal(a.st[30]+16*a.st[33], 0x99); assert.equal(byte(a), 1);
  assert.equal(restored.ip, 0x8D);
  assert.deepEqual([restored.r[2], restored.r[23], restored.r[26]], spec.C ? [5, 1, 0] : [0, 0, 0]);
  assert.equal(byte(restored), 0x99, '8C imports oldST0 byte, not the pressed1 or a raw cache byte');
  assert.deepEqual(raw.map(j => restored.r[j]), raw.map(j => initial.state.ik1302.r[j]));
  assert.equal(es[2278].ip, 0x8F); assert.equal(es[2279].ip, 0x81);
  assert.equal(es[2280].ip, 0x82); assert.equal(es[2280].r[26], 0); assert.equal(es[2281].ip, 0x84);
  assert.equal(es[2314].ip, 0x40); assert.equal(es[2315].ip, 0x41);
  assert.deepEqual(triple(es[2314], 1), [5, 0, 0], 'original pre-8C control fields were reserved inST1');
  assert.equal(es[2314].st[23], spec.C, 'first91 imported the numeric C flag intoST2');
  assert.deepEqual(triple(es[2315], 2), [5, 0, 0], '40 overwrites ST2 joint fields from oldST1');
  const at47 = es[2325], at49 = es[2326], be = es[2340];
  assert.equal(es[2324].ip, 0xE7); assert.equal(es[2324].slot, 'X');
  assert.deepEqual(es[2324].r.filter((_, i) => i < 36 && i % 3 === 0),
    [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0], 'numeric working-X write contains only entered1');
  assert.equal(at47.ip, 0x47); assert.equal(at49.ip, 0x49); assert.equal(es[2327].ip, 0xBD);
  assert.equal(es[2328].ip, 0x91); assert.equal(es[2328].sp[0], 0xBE, 'originalBD, not a repaired return');
  assert.equal(be.ip, 0xBE); assert.deepEqual([be.r[2], be.r[23], be.r[26]], [5, 0, 0]);
  assert.equal(be.pc, 0x90); assert.equal(byte(be), 0xFF); assert.equal(es[2341].ip, 0xB0);
  assert.deepEqual(be.r.filter((_, i) => i < 36 && i % 3 === 0),
    at47.r.filter((_, i) => i < 36 && i % 3 === 1), 'BE source is actual oldB from before47');
  assert.equal(be.pc, at47.st[31]+16*at47.st[34], 'BE address from actual oldST1 before47');
  assert.deepEqual([be.r[2], be.r[23], be.r[26]], triple(at47, 2), 'BE fields from actual oldST2 before47');
  const numericM2Writes = es.filter(e => e.ip === 0xE7).map(e => ({command: e.command, slot: e.slot}));
  assert.deepEqual(numericM2Writes, [{command: 2324, slot: 'X'}]);
  const primaryWrites = t.writes.filter(e => e.chip === 3);
  assert.equal(primaryWrites.length, 12);
  assert.ok(primaryWrites.every(e => e.ip === 0xE7 && e.command === 2324 &&
    e.slot === 'X' && e.nibble % 3 === 1 && e.nibble <= 34),
    'all12 primary writes are numeric M2 of physical workingX; no hidden Ms/programme write');
  const after = data(c), end = {command: spec.end, state: machineSnapshot(c)};
  assert.deepEqual(after, before, 'all105 programme/56 Ms/15 ordinary words held; workingX alone changes');
  assert.equal(ip(end.state.ik1302), 0x35); assert.equal(t.display, '1,');
  if (mirror) {
    const plain = prepare(spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), readerInitial.state, 'fresh unobserved preparation');
    reader(plain); data(plain);
    assert.deepEqual(machineSnapshot(plain), initial.state, 'fresh unobserved complete reader');
    finish(plain, spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), end.state, 'fresh unobserved complete suffix');
  }
  const report = {...spec, nativeKeyboardOnly: true, observerIndependent: mirror,
    all105Programme56Ms15OrdinaryHeld: true, nativeOriginalBEEntry: true,
    pre8CFlag: 0, first8C: 2264, first8D: 2277, first82: 2280, first82Counter: 0,
    byteReplacedBy8C: {before: 1, after: 0x99}, first40: 2314,
    thirdBufferFlagBefore40: spec.C, thirdBufferFlagAfter40: 0,
    first47: 2325, first49: 2326, originalBE: 2340, originalBEFields: [5, 0, 0],
    originalBEByte: 0xFF, originalBEPC: 0x90, originalBENext: 0xB0,
    numericM2Writes, physicalPrimaryWriteCount: primaryWrites.length,
    nativeWriterGateOpen: false, persistentMsCopy: false, partialK2: false};
  if (log) console.log(JSON.stringify(report));
  return {report, readerInitial, readerOrigin, readerCore, readerEnd, initial, origin, core, first8C, end};
}
if (require.main === module) {
  if (process.argv.includes('--proof-input')) console.log(JSON.stringify(specs.map(spec => capture(spec, {log: false}))));
  else specs.forEach(spec => capture(spec));
}
module.exports = {specs, prepare, finish, capture};
