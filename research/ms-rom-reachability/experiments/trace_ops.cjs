#!/usr/bin/env node
'use strict';
// Exploratory probe, not a physical keyboard protocol; see the research README.

const { MK61 } = require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
const hex = value => value.toString(16).toUpperCase().padStart(2, '0');

function traceAction(label, setup, action) {
  const calc = new MK61();
  setup(calc);
  const chip = calc.ik1302;
  const originalTick = chip.tick;
  const ips = [];
  chip.tick = function () {
    if (this.tickIndex === 0) ips.push(this.r[36] + 16 * this.r[39]);
    return originalTick.call(this);
  };
  action(calc);
  chip.tick = originalTick;
  const first12 = ips.indexOf(0x12);
  const firstC6 = ips.indexOf(0xC6);
  const firstC7 = ips.indexOf(0xC7);
  const firstC8 = ips.indexOf(0xC8);
  const begin = Math.max(0, [first12, firstC6, firstC7, firstC8].filter(x => x >= 0).sort((a,b)=>a-b)[0] - 5 || 0);
  const excerpt = ips.slice(begin, begin + 220).map(hex).join(' ');
  console.log(JSON.stringify({label, counts: Object.fromEntries([0x12,0x60,0xC6,0xC7,0xC8,0xCD]
    .map(ip => [hex(ip), ips.filter(x => x === ip).length])), excerpt}));
}

traceAction('keyboard multiply', c => c.pressSequence(['2', 'В↑', '3']), c => c.press('*'));
traceAction('program multiply', c => c.loadProgram([0x02,0x0E,0x03,0x12,0x50]), c => c.pressSequence(['В/О','С/П']));
traceAction('keyboard divide', c => c.pressSequence(['2', 'В↑', '3']), c => c.press('/'));
