#!/usr/bin/env node
'use strict';
// Exploratory probe, not a physical keyboard protocol; see the research README.

const { MK61 } = require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
const hex = value => value.toString(16).toUpperCase().padStart(2, '0');

function traceDigit(digit) {
  const calc = new MK61();
  calc.press('K');
  const chip = calc.ik1302;
  const originalTick = chip.tick;
  const originalExecute = chip.executeMicroOrder;
  const writes = [];
  const visits = [];
  let currentIp = null;
  chip.tick = function () {
    if (this.tickIndex === 0) {
      currentIp = this.r[36] + 16 * this.r[39];
      if (currentIp === 0x60) visits.push({ writeIndex: writes.length,
        r25: this.r[25], r31: this.r[31], r38: this.r[38] });
    }
    return originalTick.call(this);
  };
  chip.executeMicroOrder = function (number, acc) {
    const tick = this.tickIndex;
    const targetsR38 = (tick === 38 && number >= 15 && number <= 21)
      || (tick === 39 && number === 22) || (tick === 40 && number === 23);
    const before = this.r[38];
    const result = originalExecute.call(this, number, acc);
    if (targetsR38) writes.push({ ip: hex(currentIp), tick, order: number,
      sigma: acc.sigma, s: this.s, s1: this.s1, before, after: this.r[38] });
    return result;
  };
  calc.press(String(digit));
  chip.tick = originalTick;
  chip.executeMicroOrder = originalExecute;
  console.log(JSON.stringify({ digit, visits: visits.map(visit => ({ ...visit,
    precedingWrites: writes.slice(Math.max(0, visit.writeIndex - 8), visit.writeIndex),
  })) }, null, 2));
}

traceDigit(1);
traceDigit(2);
