#!/usr/bin/env node
'use strict';
// The ROM and all internal state are untouched. Setup and the operation use
// only calculator keys; tick wrapping observes command-boundary transitions.
const assert = require('node:assert/strict');
const path = require('node:path');
const { MK61 } = require(path.join(process.env.MK61_REFERENCE_ROOT ||
  path.resolve(__dirname, '../../..', 'MK-61'), 'tests/emulator/mk61.cjs'));
const address = chip => chip.r[36]+16*chip.r[39];
const hex = n => n.toString(16).toUpperCase().padStart(2,'0');

for (const [pointer, incremented, selector] of [['2',3,4],['3',4,5],['7',8,9]]) {
  const calc = new MK61();
  calc.inputNumber(pointer,{clear:true}).pressSequence(['X→П','5']);
  calc.inputNumber('12345678',{clear:true});
  const chip = calc.ik1302, original = chip.tick, events = [];
  let entry;
  chip.tick = function () {
    if (this.tickIndex === 0) entry = {ip:address(this),r0:this.r[0],r2:this.r[2],
      r25:this.r[25],r26:this.r[26],r31:this.r[31],r32:this.r[32],
      r35:this.r[35],r38:this.r[38],s1:this.s1};
    const result = original.call(this);
    if (this.tickIndex === 0 && [0xDD,0x7E,0x77,0x6D,0x60,0xC7,0xC8].includes(entry.ip))
      events.push({...entry,next:address(this),afterR38:this.r[38]});
    return result;
  };
  try {calc.pressSequence(['K','X→П','5']);} finally {chip.tick = original;}

  assert.equal(calc.readRegister('5'),`0000000${incremented},`, 'P5 increments before use');
  const gateIndex = events.findIndex(e => e.ip === 0x7E);
  assert.ok(gateIndex >= 0);
  const gate = events[gateIndex];
  assert.deepEqual([gate.r32,gate.r35,gate.r38,gate.r26,gate.r25,gate.r31,gate.next],
    [5,1,selector,15,0,0,0x71]);
  const writes = events.slice(0,gateIndex).filter(e => e.ip === 0xDD);
  assert.deepEqual(writes.map(e => [e.r0,e.s1,e.next,e.afterR38]),
    [[8,6,0xD6,9],[incremented,4,0xD4,selector]]);
  assert.equal(events.filter(e => e.ip === 0xC7 || e.ip === 0xC8).length,0);
  assert.equal(events.filter(e => e.ip === 0x60).length,0);
  console.log(`PASS: P5=${pointer}->${incremented}, X=12345678, K X→П 5: `+
    `DD selectors 9->${selector}; R32=5/R38=${selector} at 7E->${hex(gate.next)}, never 60/C7/C8`);
}
console.log('PASS: 3 keyboard-only cases; compatible data at 7E do not establish entry at 60');
