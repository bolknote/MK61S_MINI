#!/usr/bin/env node
'use strict';
// Four ordinary cycle preparations on the full, unchanged reference machine.
// Program, counters, and X are entered only by keys; tick hooks only observe.
const assert = require('node:assert/strict');
const path = require('node:path');
const { MK61 } = require(path.join(process.env.MK61_REFERENCE_ROOT ||
  path.resolve(__dirname, '../../..', 'MK-61'), 'tests/emulator/mk61.cjs'));
const cases = [
  { name: 'L0', code: 0x5D, key: 'П→X', index: 0 },
  { name: 'L1', code: 0x5B, key: 'X→П', index: 1 },
  { name: 'L2', code: 0x58, key: 'БП', index: 2 },
  { name: 'L3', code: 0x5A, key: 'ПП', index: 3 },
];
for (const test of cases) {
  const calc = new MK61();
  calc.pressSequence(['F', 'ВП', 'F', test.key, '0', '3', 'С/П', 'С/П',
    'F', '/-/', 'В/О']);
  assert.deepEqual([0, 1, 2, 3].map(i => calc.readCommand(i)),
    [test.code, 0x03, 0x50, 0x50]);
  calc.inputNumber('1', { clear: true }).pressSequence(['X→П', String(test.index)]);
  calc.inputNumber('12345673', { clear: true }).press('В/О');
  const chip = calc.ik1302, tick = chip.tick;
  const events = [], primitives = [];
  let active = false;
  chip.tick = function () {
    if (this.tickIndex === 0) {
      const ip = this.r[36]+16*this.r[39];
      if (ip === 0xC7 || ip === 0xC8) primitives.push(ip);
      if (ip === 0xAD && this.r[35] === 5 && this.r[32] === (test.code & 15)) active = true;
      if (active && events.length < 500) events.push({
        ip, r0: this.r[0], r2: this.r[2], r26: this.r[26],
        r32: this.r[32], r35: this.r[35], r38: this.r[38], s1: this.s1,
        vector: this.r[37]+16*this.r[40],
        sp: [0, 1, 2].map(i => this.stack[36+i]+16*this.stack[39+i]),
      });
    }
    return tick.call(this);
  };
  try {
    calc.press('С/П').runUntilStable({ maxFrames: 12, stableFrames: 4 });
  } finally {
    chip.tick = tick;
  }
  assert.ok(active, test.name+' decoded cycle context');
  const read = events.find(e => e.ip === 0x2E);
  const ddIndex = events.findIndex(e => e.ip === 0xDD);
  assert.ok(read && ddIndex >= 0, test.name+' read and DD observed');
  const dd = events[ddIndex], exit = events[ddIndex+1];
  assert.equal(read.r32, test.index, test.name+' read index');
  assert.equal(read.r26, 0);
  assert.equal(read.r35, 5);
  assert.equal(dd.r0, 3);
  assert.equal(dd.r26, 0);
  assert.equal(dd.r32, test.index);
  assert.equal(dd.r35, 5);
  assert.equal(dd.r38, 0xD);
  assert.equal(dd.s1, 6);
  assert.equal(dd.vector, 0xFF);
  assert.equal(dd.sp[0], 0x2F);
  assert.equal(exit.ip, 0xD6);
  assert.equal(exit.r38, 4);
  assert.ok(events.slice(0, ddIndex+2).every(e => e.r2 === 0), test.name+' low-mode preparation');
  const sevenIndex = events.findIndex((e, i) => i > ddIndex && e.ip === 0x07);
  assert.ok(sevenIndex >= 0, test.name+' first 07 after the cycle read');
  assert.equal(events[sevenIndex+1].ip, 0x09);
  assert.deepEqual(primitives, []);
  console.log(`PASS ${test.name}/${test.code.toString(16).toUpperCase()}: `+
    `read index ${read.r32}, DD R0=3/R26=0/R35=5, selector4, `+
    'R2=0 throughout, 07->09, no C7/C8');
}
