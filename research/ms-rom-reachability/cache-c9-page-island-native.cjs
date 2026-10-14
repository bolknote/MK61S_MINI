#!/usr/bin/env node
'use strict';
// Source-selected reader and ordinary editor controls, public keys ONLY.
// C9 swaps are observed passively. A temporary number/programme parking
// swap is NOT called a persistent Ms exchange or a native K2.
const assert = require('node:assert/strict');
const {prepare: cold} = require('./cache-control-f-transfer-native.cjs');
const {prepare: marker} = require('./cache-da-keyboard.cjs');
const {prepareSelector} = require('./st34-origin-trace.cjs');
const {finishSignature700, registerKey, rawMemoryRegister} = require('./check_ac_signature_keyboard.cjs');
const {fixtures, install} = require('./check_partial_k2_program_scan.cjs');
const {reader} = require('./cache-cf-buffer-native.cjs');
const {trace, aligned} = require('./probe_ee_ring_source.cjs');
const {machineSnapshot} = require('./probe_c8_pc_reader.cjs');
const {fullMsPages} = require('./probe_c8_payload.cjs');
const {locations, slots} = require('./cache-d4-native-topology.cjs');
const lane14 = (values, lane) => Array.from({length: 14}, (_, i) => values[3*i+lane]);
const data = c => ({program: Array.from({length: 105}, (_, i) => c.readCommand(i)),
  ms: fullMsPages(c), registers: Array.from({length: 15}, (_, i) => rawMemoryRegister(c, i))});
const ip = a => a.r[36]+16*a.r[39];
const specs = [
  {name: 'reader_digits', kind: 'reader', fixture: fixtures[0], swaps: 6, coreStart: 1325, coreEnd: 1699},
  {name: 'reader_raw', kind: 'reader', fixture: fixtures[1], swaps: 6, coreStart: 1325, coreEnd: 1699},
  {name: 'editor_A3', kind: 'editor', fixture: fixtures[0], swaps: 8, coreStart: 45, coreEnd: 484},
];

function prepare(spec) {
  const c = cold();
  if (spec.kind === 'reader') {
    c.inputNumber('0', {clear: true}).pressSequence(['X→П', registerKey(12)]); aligned(c);
    marker({fixture: spec.fixture, calc: c, values: '7.7754327E-91'});
    prepareSelector(c, {selector: 9}); finishSignature700(c); aligned(c);
  } else {
    install(c, spec.fixture);
    c.pressSequence(['БП', '8', '7', 'F', 'ВП', 'K', 'ПП']); aligned(c);
    assert.equal(c.readCommand(87), 4, 'pending editor prefix has not written A3 yet');
  }
  // Resolve the programme page independently from readCommand addresses.
  const [chip, address] = c.commandAddress(84, 1);
  assert.equal(slots[locations.findIndex(([n, end]) => n === chip && address === end)], 'Y');
  return c;
}
function finish(c, spec) {
  if (spec.kind === 'reader') reader(c);
  else { c.pressSequence(['3', 'F', '/-/', 'В/О']).runFrames(2); aligned(c); }
}

function capture(spec, {mirror = true, log = true} = {}) {
  const c = prepare(spec), before = data(c), initial = {command: 0, state: machineSnapshot(c)};
  assert.deepEqual(before.program.slice(84, 91), spec.fixture.bytes);
  const origin = [], core = []; let afterSwap = -1;
  const t = trace(c, c => finish(c, spec), {
    extraIps: Array.from({length: 256}, (_, i) => i), fullState: true,
    otherChipsAt: e => {
      const save = () => ({command: e.command, ip: e.ip, slot: e.slot, state: machineSnapshot(c)});
      if (origin.length < 65) origin.push(save());
      if (e.command >= spec.coreStart && e.command <= spec.coreEnd) core.push(save());
      if (e.ip === 0xC9) afterSwap = e.command+1;
      return false;
    },
    ringAt: e => [0xC8, 0xC9].includes(e.ip) || e.command === afterSwap,
  });
  const events = t.events, swaps = events.filter(e => e.ip === 0xC9), after = data(c);
  assert.equal(events.length, 6720); assert.equal(swaps.length, spec.swaps);
  assert.ok(events.every((e, i) => e.command === i));
  assert.equal(origin.length, 65); assert.equal(core.length, spec.coreEnd-spec.coreStart+1);
  for (const group of [origin, core])
    assert.ok(group.every((e, i) => !i || e.command === group[i-1].command+1));
  const pairs = [];
  for (let index = 0; index < swaps.length; index += 2) {
    const first = swaps[index], second = swaps[index+1];
    const old = lane14(first.m, 2), parked = lane14(first.r, 1), restored = lane14(second.r, 1);
    assert.deepEqual([first.sp[0], second.sp[0]], [0x67, 0x06]);
    assert.equal(first.s1, 9); assert.equal(second.s1, 9);
    assert.equal(first.slot, 'Y'); assert.equal(second.slot, 'Y');
    assert.equal(second.command-first.command, 60);
    const changed = old.flatMap((v, j) => v === restored[j] ? [] : [j]);
    const writing = spec.kind === 'editor' && index === 0;
    assert.deepEqual(changed, writing ? [4, 5] : []);
    if (writing) {
      assert.equal(first.r[26], 0); assert.deepEqual(restored.slice(4, 6), [3, 10]);
    } else assert.notEqual(first.r[26], 0);
    const afterFirst = events[first.command+1], afterSecond = events[second.command+1];
    assert.deepEqual(lane14(afterFirst.ring.Y, 2), parked, 'actual complete parked programme word');
    assert.deepEqual(lane14(second.m, 2), parked, 'parked word survives to the restoring C9');
    assert.deepEqual(lane14(afterSecond.ring.Y, 2), restored, 'actual physical programme restoration/patch');
    assert.deepEqual(lane14(afterSecond.r, 1), parked, 'second C9 returns the parked numeric word to B');
    const inside = events.slice(first.command+1, second.command);
    assert.ok(!inside.some(e => [0xBB, 0xBC, 0xC7, 0xD4, 0xE7, 0xE9].includes(e.ip)));
    assert.ok(inside.filter(e => e.ip === 0xCC).every(e => e.s1 === 9));
    pairs.push({first: first.command, second: second.command, offset: first.r[35],
      firstFlag: first.r[26], original14: old, parked14: parked, returned14: restored,
      changedTetras: changed, nativeF9: inside.some(e => e.ip === 0xF9)});
  }
  const changes = before.program.flatMap((value, address) =>
    value === after.program[address] ? [] : [{address, before: value, after: after.program[address]}]);
  assert.deepEqual(after.ms, before.ms, 'all56 Ms bytes held');
  assert.deepEqual(after.registers, before.registers, 'all15 ordinary numeric words held');
  let sourceMs = null;
  if (spec.kind === 'reader') {
    assert.deepEqual(t.primitives, [0xC8]); assert.deepEqual(changes, []);
    const source = events.find(e => e.ip === 0xC8);
    assert.equal(source.command, 1325); assert.equal(source.slot, 'W');
    const word = lane14(source.m, 1);
    assert.deepEqual(word, [...before.ms.W].reverse().map(v => parseInt(v, 16)));
    assert.deepEqual(pairs[0].parked14.slice(0, 10), word.slice(0, 10),
      'first five raw MsW bytes genuinely reach the temporary programme page');
    assert.notDeepEqual(pairs[0].parked14.slice(10, 12), word.slice(10, 12));
    assert.notDeepEqual(pairs[0].parked14.slice(12, 14), word.slice(12, 14));
    for (const e of events.filter(e => e.ring))
      assert.deepEqual(lane14(e.ring.W, 1), word, 'the original MsW word remains intact');
    sourceMs = {slot: 'W', word14: word, firstFiveByteCopy: true,
      parkedSixthAndSeventhChanged: true, persistentCopy: false};
  } else {
    assert.deepEqual(t.primitives, []);
    assert.deepEqual(changes, [{address: 87, before: 4, after: 0xA3}]);
    assert.equal(events.filter(e => e.ip === 0xF9).length, 1);
  }
  const end = {command: 6720, state: machineSnapshot(c)};
  assert.equal(ip(end.state.ik1302), 0x35);
  if (mirror) {
    const plain = prepare(spec); data(plain);
    assert.deepEqual(machineSnapshot(plain), initial.state, 'fresh unobserved complete preparation');
    finish(plain, spec);
    assert.deepEqual(data(plain), after); assert.deepEqual(machineSnapshot(plain), end.state,
      'fresh completely unobserved ALL5 mirror');
  }
  const report = {name: spec.name, kind: spec.kind, end: 6720, fixture: spec.fixture.name,
    keys: spec.kind === 'reader' ? ['П→X', '9'] : ['3', 'F', '/-/', 'В/О'],
    nativeKeyboardOnly: true, observerIndependent: mirror, sourceMs, pairs,
    programmeChanges: changes, all56MsBytesHeld: true, all15OrdinaryWordsHeld: true,
    persistentMsCopy: false, partialK2: false};
  if (log) console.log(JSON.stringify(report));
  return {report, initial, origin, core, end};
}
if (require.main === module) {
  if (process.argv.includes('--proof-input'))
    console.log(JSON.stringify(specs.map(spec => capture(spec, {log: false}))));
  else specs.forEach(spec => capture(spec));
}
module.exports = {specs, prepare, finish, capture};
