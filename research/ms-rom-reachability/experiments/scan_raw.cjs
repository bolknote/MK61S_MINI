#!/usr/bin/env node
'use strict';
// Exploratory probe, not a physical keyboard protocol; see the research README.

const { MK61 } = require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
const hex = value => value.toString(16).toUpperCase().padStart(2, '0');

function probe(code) {
  const calc = new MK61();
  calc.loadProgram([code, 0x50]);
  calc.press('В/О');
  const chip = calc.ik1302;
  const originalTick = chip.tick;
  const transitions = [];
  const visits = [];
  let previous = null;
  let snapshot = null;
  chip.tick = function () {
    if (this.tickIndex === 0) {
      const ip = this.r[36] + 16 * this.r[39];
      if (previous === 0x1F) transitions.push({ next: ip, ...snapshot });
      if ([0x12, 0x60, 0xC6, 0xC7, 0xC8].includes(ip)) visits.push(ip);
      snapshot = ip === 0x1F ? {
        s1: this.s1,
        r: [25, 28, 31, 34, 37, 38, 40].map(i => this.r[i]),
      } : null;
      previous = ip;
    }
    return originalTick.call(this);
  };
  calc.press('С/П');
  chip.tick = originalTick;
  return { code, transitions, visits };
}

for (let code = 0; code < 256; code++) {
  const result = probe(code);
  if (result.transitions.some(x => x.next === 0x12) || result.visits.length) {
    console.log(JSON.stringify({ code: hex(code), transitions: result.transitions.map(x => ({
      next: hex(x.next), s1: x.s1.toString(16).toUpperCase(), r: x.r.map(n => n.toString(16).toUpperCase()).join(''),
    })), visits: result.visits.map(hex) }));
  }
}
