#!/usr/bin/env node
'use strict';
// Exploratory probe, not a physical keyboard protocol; see the research README.

const { MK61 } = require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
const hex = value => value.toString(16).toUpperCase().padStart(2, '0');

function experiment(digit, from, to) {
  const calc = new MK61();
  calc.press('K');
  const chip = calc.ik1302;
  const originalTick = chip.tick;
  const trace = [];
  let injected = false;
  let sawHandler = false;
  chip.tick = function () {
    if (this.tickIndex === 0) {
      let ip = this.r[36] + 16 * this.r[39];
      if (ip === 0x14 + digit) sawHandler = true;
      if (!injected && sawHandler && ip === from) {
        this.r[36] = to & 15;
        this.r[39] = to >>> 4;
        ip = to;
        injected = true;
      }
      if (injected && trace.length < 800) trace.push(ip);
    }
    return originalTick.call(this);
  };
  calc.press(String(digit));
  chip.tick = originalTick;
  const counts = Object.fromEntries([0x12,0x60,0x68,0xBF,0xC0,0xC1,0xC2,0xC3,
    0xC4,0xC5,0xC6,0xC7,0xC8,0xC9,0xCD].map(ip =>
      [hex(ip), trace.filter(x => x === ip).length]));
  return { digit, redirect: `${hex(from)}->${hex(to)}`, injected,
    display: calc.displayText(), counts, trace: trace.slice(0, 260).map(hex).join(' ') };
}

for (const [digit, from, targets] of [
  [1, 0x0F, [0x12, 0xBF, 0xC0, 0xC4, 0xC6, 0xC7]],
  [2, 0x3F, [0x12, 0x60, 0x68, 0xBF, 0xC0, 0xC4, 0xC6, 0xC8]],
]) {
  for (const target of targets) console.log(JSON.stringify(experiment(digit, from, target)));
}
