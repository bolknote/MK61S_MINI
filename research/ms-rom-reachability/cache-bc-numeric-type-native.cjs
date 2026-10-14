#!/usr/bin/env node
'use strict';
// Source-selected C profile: mantissa3 proposes flag3, exponent36 proposes
// operand6/type3. The original AC replaces the order from ST2 first.
// This is a fresh native NEGATIVE diagnostic + unobserved mirror; no model
// repair, and no new consecutive ALL5 replay count is claimed for this file.
const assert = require('node:assert/strict');
const {prepare} = require('./cache-writer-flag-native.cjs');
const {reader} = require('./cache-cf-buffer-native.cjs');
const {trace, aligned} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const {rawMemoryRegister} = require('./check_ac_signature_keyboard.cjs');
const spec = {C: 3, value: '3.0000005E36', rawC: '036030000005', ST10: 5};
const data = c => ({program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c), registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i))});
const finish = c => {c.pressSequence(['K', '0']).runFrames(2); aligned(c);};
const c = prepare(spec), before = data(c), cold = machineSnapshot(c);
reader(c); assert.deepEqual(data(c), before);
const initial = machineSnapshot(c);
assert.deepEqual([initial.ik1302.st[1], initial.ik1302.st[22], initial.ik1302.st[25]], [5, 3, 0]);
const t = trace(c, finish, {extraIps: Array.from({length: 256}, (_, i) => i), fullState: true});
assert.equal(t.events.length, 3360);
assert.ok(!t.events.some(e => [0xBC, 0xBB, 0xC9, 0xF9, 0xD4].includes(e.ip)));
const ac = t.events[1171], afterAC = t.events[1172], e4 = t.events[1198], d6 = t.events[1200];
assert.equal(ac.ip, 0xAC);
assert.deepEqual([ac.st[28], ac.st[31], ac.st[34]], [6, 9, 15]);
assert.deepEqual([ac.st[29], ac.st[32], ac.st[35]], [0, 8, 5]);
assert.deepEqual([afterAC.st[28], afterAC.st[31], afterAC.st[34]], [0, 8, 5]);
assert.deepEqual(afterAC.st.slice(0, 27).filter((_, i) => i % 3 === 1),
  ac.st.slice(0, 27).filter((_, i) => i % 3 === 1));
assert.equal(e4.ip, 0xE4);
assert.deepEqual([e4.r[2], e4.r[23], e4.r[26], e4.r[29], e4.r[32], e4.r[35]], [5, 3, 0, 0, 8, 5]);
assert.equal(d6.ip, 0xD6);
assert.deepEqual([d6.r[2], d6.r[23], d6.r[26], d6.r[29], d6.r[32], d6.r[35]], [5, 7, 0, 0, 8, 5]);
assert.deepEqual(data(c), before);
const end = machineSnapshot(c);
assert.equal(end.ik1302.r[36]+16*end.ik1302.r[39], 0xE5);
const plain = prepare(spec); data(plain); assert.deepEqual(machineSnapshot(plain), cold);
reader(plain); data(plain); assert.deepEqual(machineSnapshot(plain), initial);
finish(plain); data(plain); assert.deepEqual(machineSnapshot(plain), end);
console.log(JSON.stringify({label: 'NATIVE_NUMERIC_ORDER_NEGATIVE_DIAGNOSTIC', ...spec,
  originalOrderIsNotLateTypeSupplier: true, all105Programme56Ms15OrdinaryHeld: true,
  originalAC: {command: 1171, oldST1Upper3: [6, 9, 15], oldST2Upper3: [0, 8, 5], newST1Upper3: [0, 8, 5]},
  originalE4: {command: 1198, flags: [5, 3, 0], operand: 0, type: 8, pending: 5},
  completeSuffix: 3360, freshUnobservedMirror: true, extraConsecutiveALL5ReplayClaimed: false,
  nativeBC: false, partialK2: false}));
