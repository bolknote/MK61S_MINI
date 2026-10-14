#!/usr/bin/env node
'use strict';
// Only calculator keys are used for setup and execution. Tick wrappers read
// state; they never assign registers, memory, program bytes, or ROM contents.
const assert = require('node:assert/strict');
const path = require('node:path');
const { MK61 } = require(path.join(process.env.MK61_REFERENCE_ROOT ||
  path.resolve(__dirname, '../../..', 'MK-61'), 'tests/emulator/mk61.cjs'));
const hex = n => n.toString(16).toUpperCase().padStart(2, '0');
const fields = ch => ({ip:ch.r[36]+16*ch.r[39], pc:ch.r[31]+16*ch.r[34],
  r2:ch.r[2], r26:ch.r[26], r25:ch.r[25], r31:ch.r[31],
  r32:ch.r[32], r38:ch.r[38]});
const candidateCounter = pc => pc === 0xB9 || pc === 0xF0 ||
  (pc >= 0xC0 && pc <= 0xE9 && (pc & 15) < 10);

function pausedPreparation() {
  const calc = new MK61();
  calc.pressSequence(['F','ВП','БП','K','X→П','9','С/П','F','/-/','В/О']);
  assert.deepEqual([0,1,2].map(i => calc.readCommand(i)), [0x51,0xB9,0x50]);
  calc.inputNumber('12345678', {clear:true});
  const chip = calc.ik1302, original = chip.tick, primitives = [];
  let paused, snapshot, afterK1;
  chip.tick = function () {
    if (this.tickIndex === 0 && [0xC7,0xC8].includes(fields(this).ip))
      primitives.push(fields(this));
    return original.call(this);
  };
  try {
    // Fixed released-key intervals, not a host-side edit or stop at an
    // observed microcode breakpoint. All 560*42 ticks per frame still run.
    calc.press('С/П').runFrames(4);
    calc.press('С/П').runFrames(4);
    paused = fields(chip);
    assert.equal(chip.tickIndex, 0);
    snapshot = {r:chip.r.slice(), m:chip.memory.slice(), st:chip.stack.slice(),
      s:chip.s, s1:chip.s1, l:chip.l, t:chip.t, carry:chip.carry};
    calc.pressSequence(['K','1']).runFrames(4);
    afterK1 = fields(chip);
  } finally {
    chip.tick = original;
  }
  assert.deepEqual([paused.pc,paused.r2,paused.r26,paused.r38], [0xD7,8,0,13]);
  assert.deepEqual([afterK1.pc,afterK1.r2,afterK1.r26,afterK1.r38], [0xD7,8,0,12]);
  assert.equal(primitives.length, 0);
  return {paused,snapshot,afterK1,primitives};
}

if (process.argv.includes('--paused-json')) {
  console.log(JSON.stringify(pausedPreparation()));
  process.exit(0);
}

function observe(calc, action) {
  const chip = calc.ik1302, original = chip.tick;
  const entries = [], primitives = [], bootstrap = [];
  let before;
  chip.tick = function () {
    if (this.tickIndex === 0) {
      before = fields(this);
      // These checks are never capped by the display/log sample limit.
      if ([0xC7, 0xC8].includes(before.ip)) primitives.push(before);
      if (before.ip === 0x60 && before.r38 === 9 && before.r26 === 1 &&
          before.r2 >= 5 && before.r25 === before.r31) bootstrap.push(before);
    }
    const result = original.call(this);
    if (this.tickIndex === 0 && [0x07, 0xDD, 0x7E].includes(before.ip))
      entries.push({...before, next:this.r[36]+16*this.r[39], afterR38:this.r[38]});
    return result;
  };
  try {
    action();
    calc.runUntilStable({maxFrames:12, stableFrames:4});
  } finally {
    chip.tick = original;
  }
  return {entries, primitives, bootstrap};
}

// Decimal numerical operands are controls, not a general proof for all
// malformed numbers or unusual indirect-address encodings.
for (const [target, expected] of [['20',0x20], ['119',0x19], ['120',0x20], ['150',0x50]]) {
  const calc = new MK61();
  calc.inputNumber(target, {clear:true}).pressSequence(['X→П','ВП']);
  calc.inputNumber('12345678', {clear:true});
  const report = observe(calc, () => calc.pressSequence(['K','БП','ВП']));
  assert.equal(calc.ik1302.r[31]+16*calc.ik1302.r[34], expected);
  assert.equal(report.primitives.length, 0);
  assert.equal(report.bootstrap.length, 0);
  assert.ok(report.entries.some(e => e.ip === 0xDD && e.afterR38 === 9));
  console.log(`PASS: numeric indirect target ${target} leaves PC=${hex(expected)}; `+
    'DD can prepare 9, but the bootstrap/primitive is not entered');
}

// The raw address bytes are entered as ordinary command keys at the operand
// position. They are NOT written through the emulator's program-memory API.
for (const [operand, keySequence, firstHigh] of [
  [0xB9, ['K','X→П','9'], 0xC0],
  [0xC0, ['K','ШГ→','0'], 0xC1],
]) {
  const calc = new MK61();
  calc.pressSequence(['F','ВП','БП',...keySequence,'С/П','F','/-/','В/О']);
  assert.deepEqual([0,1,2].map(i => calc.readCommand(i)), [0x51,operand,0x50]);
  calc.inputNumber('12345678', {clear:true});
  const report = observe(calc, () => calc.press('С/П'));
  const high = report.entries.filter(e => e.ip === 0x07 && candidateCounter(e.pc));
  assert.ok(high.length > 0, 'must actually visit the relevant high-counter region');
  assert.equal(high[0].pc, firstHigh);
  assert.ok(high.some(e => e.pc === 0xF0));
  for (const entry of high)
    assert.deepEqual([entry.r2,entry.r26,entry.r38,entry.next], [0,0,8,0x09]);
  assert.equal(report.primitives.length, 0, 'a high PC byte is not ROM entry C8');
  assert.equal(report.bootstrap.length, 0);
  const counters = new Set(high.map(e => e.pc));
  console.log(`PASS: keyboard program 51 ${hex(operand)} 50 visits `+
    `${counters.size} distinct candidate-range PC values, starting ${hex(firstHigh)}, `+
    'including F0; 07 has R2=0/R26=0/R38=8 and takes 09, no ROM C7/C8');
}
const paused = pausedPreparation();
console.log(`PASS: keyboard run/stop preparation gives PC=${hex(paused.paused.pc)}, `+
  'R2=8, R26=0, R38=D together; K1 keeps PC/R2 but changes R38 to C, no C7/C8');
console.log('PASS: 7 keyboard-only counter-preparation cases. High PC and high R2 '+
  'can coexist; the required marker/selector/bootstrap is still not established.');
