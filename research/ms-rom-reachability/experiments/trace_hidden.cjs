#!/usr/bin/env node
'use strict';
// Exploratory probe, not a physical keyboard protocol; see the research README.

const { MK61 } = require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
const { makeProgram } = require('/Users/bolk/Projects/MK-61/tests/emulator/probe-pustyshka-program.cjs');
const hex = value => value.toString(16).toUpperCase().padStart(2, '0');

const calc = new MK61();
const { program } = makeProgram({ literal: true, repeats: 1 });
calc.loadProgram(program);
calc.press('В/О');
const chip = calc.ik1302;
const originalTick = chip.tick;
const recent = [];
const reports = [];
const counts = new Map();
let commandIndex = 0;
let lastHit = -1000;
chip.tick = function () {
  if (this.tickIndex === 0) {
    const ip = this.r[36] + 16 * this.r[39];
    const event = { n: commandIndex++, ip, s1: this.s1,
      r: [25, 26, 28, 31, 34, 35, 38].map(i => this.r[i]),
      sp: [0, 1, 2].map(lane => this.stack[36 + lane] + 16 * this.stack[39 + lane]) };
    recent.push(event);
    counts.set(ip, (counts.get(ip) || 0) + 1);
    if (recent.length > 16) recent.shift();
    if ([0x28, 0x7E, 0x77, 0x6D, 0x60, 0xC7, 0xC8].includes(ip)
        && commandIndex - lastHit > 1) {
      reports.push(recent.slice());
      lastHit = commandIndex;
    }
  }
  return originalTick.call(this);
};
calc.press('С/П');
calc.runUntilStable({ maxFrames: 2000, stableFrames: 8 });
chip.tick = originalTick;
console.log('COUNTS ' + [0x85, 0xDD, 0xE6, 0x28, 0x7E, 0x77, 0x6D, 0x60, 0xC7, 0xC8]
  .map(ip => `${hex(ip)}=${counts.get(ip) || 0}`).join(' '));
for (const report of reports) {
  console.log(report.map(e => `${e.n}:${hex(e.ip)} s${e.s1.toString(16).toUpperCase()} `
    + `r${e.r.map(x => x.toString(16).toUpperCase()).join('')} `
    + `sp${e.sp.map(hex).join('/')}`).join('\n'));
  console.log('---');
}
