#!/usr/bin/env node
'use strict';
// Exploratory probe, not a physical keyboard protocol; see the research README.

const { MK61 } = require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
const hex = value => value.toString(16).toUpperCase().padStart(2, '0');

function experiment(selector) {
  const calc = new MK61();
  calc.loadProgram([0x58, 0x00, 0x50]); // L2 00; C/P
  calc.press('В/О');

  const chip = calc.ik1302;
  const originalTick = chip.tick;
  let saw2e = false;
  let injected = false;
  const trace = [];
  const visits = new Map();
  chip.tick = function () {
    if (this.tickIndex === 0) {
      const ip = this.r[36] + 16 * this.r[39];
      if (ip === 0x2E) saw2e = true;
      if (!injected && saw2e && ip === 0xCD) {
        this.s1 = selector;
        injected = true;
      }
      if (injected) {
        if (trace.length < 500) trace.push(ip);
        visits.set(ip, (visits.get(ip) || 0) + 1);
      }
    }
    return originalTick.call(this);
  };

  calc.press('С/П');
  chip.tick = originalTick;

  const first = trace.slice(0, 160).map(hex).join(' ');
  const special = [...visits.entries()]
    .filter(([ip]) => ip >= 0xC0 && ip <= 0xC9)
    .map(([ip, count]) => `${hex(ip)}:${count}`).join(' ');
  return {
    selector: selector.toString(16).toUpperCase(),
    injected,
    pc: calc.programCounter(),
    display: calc.displayText(),
    special,
    trace: first,
  };
}

for (let selector = 0; selector < 16; selector++) {
  console.log(JSON.stringify(experiment(selector)));
}
