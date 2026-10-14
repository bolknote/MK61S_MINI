#!/usr/bin/env node
'use strict';
// Exploratory probe, not a physical keyboard protocol; see the research README.

const { MK61 } = require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
const hex = value => value.toString(16).toUpperCase().padStart(2, '0');

function experiment(register, value) {
  const calc = new MK61();
  calc.inputNumber(value, {clear:true});
  const chip = calc.ik1302;
  const originalTick = chip.tick;
  const events = [];
  let previous = null;
  let afterDD = -1;
  chip.tick = function () {
    if (this.tickIndex === 0) {
      const ip = this.r[36] + 16 * this.r[39];
      if (ip === 0xDD) afterDD = 0;
      if (afterDD >= 0 && afterDD < 24) {
        events.push({prev:previous,ip,r:[25,26,31,35,38].map(i=>this.r[i]),s1:this.s1});
        afterDD++;
      }
      previous = ip;
    }
    return originalTick.call(this);
  };
  calc.pressSequence(['X→П', register]);
  chip.tick = originalTick;
  return {register,value,events:events.map(event=>({
    prev:hex(event.prev),ip:hex(event.ip),s1:event.s1.toString(16).toUpperCase(),
    r:event.r.map(x=>x.toString(16).toUpperCase()).join(''),
  }))};
}

for (const register of ['0','1','2','3','4','5','6','7','8','9']) {
  console.log(JSON.stringify(experiment(register, '123')));
}
