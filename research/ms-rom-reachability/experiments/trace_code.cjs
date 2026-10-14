#!/usr/bin/env node
'use strict';
// Exploratory probe, not a physical keyboard protocol; see the research README.

const { MK61 } = require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
const hex = value => value.toString(16).toUpperCase().padStart(2, '0');
const code = parseInt(process.argv[2] || '28', 16);
const calc = new MK61();
calc.loadProgram([code, 0x50]);
calc.press('В/О');
const chip = calc.ik1302;
const originalTick = chip.tick;
const events = [];
let started = false;
chip.tick = function () {
  if (this.tickIndex === 0) {
    const ip = this.r[36] + 16 * this.r[39];
    if (ip === 0x1F || ip === code) started = true;
    if (started && events.length < 500) events.push({ip, s1:this.s1,
      r:[25,26,31,35,38].map(i=>this.r[i]), spc:[0,1,2].map(l=>this.stack[36+l]+16*this.stack[39+l])});
  }
  return originalTick.call(this);
};
calc.press('С/П');
chip.tick = originalTick;
console.log(events.map(e => `${hex(e.ip)}[s${e.s1.toString(16).toUpperCase()} r${e.r.map(x=>x.toString(16).toUpperCase()).join('')} sp${e.spc.map(hex).join('/')} ]`).join(' '));
