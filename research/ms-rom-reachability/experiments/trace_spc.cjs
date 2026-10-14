#!/usr/bin/env node
'use strict';
// Exploratory probe, not a physical keyboard protocol; see the research README.

const { MK61 } = require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
const hex = value => value.toString(16).toUpperCase().padStart(2, '0');

const calc = new MK61();
calc.loadProgram([0x52, 0x50]);
calc.press('В/О');
const chip = calc.ik1302;
const originalTick = chip.tick;
let recording = false;
let prior = null;
let count = 0;
chip.tick = function () {
  if (this.tickIndex === 0) {
    const ip = this.r[36] + 16 * this.r[39];
    const spc = [0, 1, 2].map(lane => this.stack[36 + lane] + 16 * this.stack[39 + lane]);
    if (ip === 0x12) recording = true;
    if (recording && count++ < 260) {
      const changed = !prior || spc.some((v, i) => v !== prior[i]);
      if (changed || [0x12,0xC6,0x38,0x62,0x9A,0xA3,0xA9,0xBC,0xC7,0xC8,0xC9,0xD4,0xD6,0xE7,0xE9,0xEE].includes(ip)) {
        console.log(`${String(count).padStart(3)} ip=${hex(ip)} spc=${spc.map(hex).join('/')}`);
      }
      prior = spc;
    }
  }
  return originalTick.call(this);
};
calc.press('С/П');
chip.tick = originalTick;
