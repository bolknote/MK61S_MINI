#!/usr/bin/env node
'use strict';
// Only real calculator keys prepare the examples; tick wrapping is read-only.
const assert = require('node:assert/strict');
const path = require('node:path');
const { MK61 } = require(path.join(process.env.MK61_REFERENCE_ROOT ||
  path.resolve(__dirname, '../../..', 'MK-61'), 'tests/emulator/mk61.cjs'));
const address = chip => chip.r[36] + 16*chip.r[39];
for (const [stored,x] of [['42','12345673'],['12345673','0'],['7','98765432']]) {
  const calc = new MK61();
  calc.inputNumber(stored,{clear:true}).pressSequence(['X→П','5']);
  calc.inputNumber(x,{clear:true});
  const chip = calc.ik1302, tick = chip.tick, events = [];
  let entry;
  chip.tick = function () {
    if (this.tickIndex === 0)
      entry = {ip:address(this),r2:this.r[2],r38:this.r[38]};
    const result = tick.call(this);
    if (this.tickIndex === 0)
      events.push({...entry,next:address(this),after2:this.r[2],after38:this.r[38]});
    return result;
  };
  try { calc.pressSequence(['П→X','5']); } finally { chip.tick = tick; }
  const start = events.findIndex(e => e.ip === 0xA6);
  assert.ok(start >= 0);
  const dd = events.findIndex((e,i) => i > start && e.ip === 0xDD);
  assert.ok(dd >= 0);
  assert.equal(events[dd].next,0xD6);
  assert.equal(events[dd+1].ip,0xD6);
  assert.equal(events[dd+1].next,0xA7);
  assert.equal(events[dd+2].ip,0xA7);
  assert.equal(events[dd+2].next,0xE5);
  const finish = events.findIndex((e,i) => i > dd && e.ip === 0xE6);
  assert.ok(finish > dd);
  assert.equal(events[finish].next,0xE8);
  assert.ok([12,13].includes(events[finish].after38));
  assert.ok(events.slice(dd+1,finish+1).every(e => e.r38 === events[dd].after38));
  assert.ok(events.slice(start,dd+2).every(e => e.r2 === events[start].r2));
  assert.ok(!events.some(e => e.ip === 0xC7 || e.ip === 0xC8));
  assert.equal(calc.displayText(),stored+',');
  console.log(`PASS: P5=${stored}, X=${x}: A6 -> DD/D6 -> A7 -> E5/E6; `+
    `selector ${events[dd].after38.toString(16)} replaced by `+
    `${events[finish].after38.toString(16)}, no C7/C8`);
}
console.log('PASS: 3 keyboard-only read-return cases; no host-written chip state');
