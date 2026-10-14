'use strict';
// Reproducible preparation by keys only. No assignment to chip state, no
// breakpoint-controlled timing, and no program-memory write API.
const assert = require('node:assert/strict');
const path = require('node:path');
const { MK61 } = require(path.join(process.env.MK61_REFERENCE_ROOT ||
  path.resolve(__dirname, '../../..', 'MK-61'), 'tests/emulator/mk61.cjs'));

function fields(ch) {
  return {ip:ch.r[36]+16*ch.r[39], pc:ch.r[31]+16*ch.r[34],
    r2:ch.r[2], r26:ch.r[26], r25:ch.r[25], r31:ch.r[31],
    r32:ch.r[32], r38:ch.r[38]};
}

function snapshot(ch) {
  return {r:ch.r.slice(), m:ch.memory.slice(), st:ch.stack.slice(),
    s:ch.s, s1:ch.s1, l:ch.l, t:ch.t, carry:ch.carry};
}

function preparePaused() {
  const calc = new MK61();
  calc.pressSequence(['F','ВП','БП','K','X→П','9','С/П','F','/-/','В/О']);
  assert.deepEqual([0,1,2].map(i => calc.readCommand(i)), [0x51,0xB9,0x50]);
  calc.inputNumber('12345678', {clear:true});
  calc.press('С/П').runFrames(4);
  calc.press('С/П').runFrames(4);
  const a = fields(calc.ik1302);
  assert.equal(calc.ik1302.tickIndex, 0);
  assert.deepEqual([a.ip,a.pc,a.r2,a.r26,a.r38], [0x35,0xD7,8,0,13]);
  return calc;
}

module.exports = {MK61, fields, snapshot, preparePaused};
