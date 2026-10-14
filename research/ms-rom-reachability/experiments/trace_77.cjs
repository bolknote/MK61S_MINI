#!/usr/bin/env node
'use strict';
// Exploratory probe, not a physical keyboard protocol; see the research README.

const { MK61 } = require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
const hex = value => value.toString(16).toUpperCase().padStart(2, '0');

const keys = ['0','1','2','3','4','5','6','7','8','9',',','/-/','ВП','Сx','В↑',
  '+','-','*','/','↔','F','K','П→X','X→П','БП','ПП','В/О','С/П','ШГ→','ШГ←'];

function trace(sequence) {
  const calc = new MK61();
  const chip = calc.ik1302;
  const originalTick = chip.tick;
  const events = [];
  let prev = null;
  chip.tick = function () {
    if (this.tickIndex === 0) {
      const ip = this.r[36] + 16 * this.r[39];
      if ([0x77,0x6D,0x60,0xC8].includes(ip)) {
        events.push({prev,ip,r25:this.r[25],r26:this.r[26],r31:this.r[31],r38:this.r[38],s1:this.s1});
      }
      prev = ip;
    }
    return originalTick.call(this);
  };
  for (const key of sequence) calc.press(key);
  chip.tick = originalTick;
  return events;
}

const sequences = [];
for (const key of keys) sequences.push([key]);
for (const prefix of ['F','K']) for (const key of keys) sequences.push([prefix,key]);
for (const sequence of sequences) {
  const events = trace(sequence);
  if (events.length) console.log(JSON.stringify({sequence, events:events.map(event => ({
    ...event, prev:hex(event.prev), ip:hex(event.ip), r:[event.r25,event.r26,event.r31,event.r38]
      .map(x=>x.toString(16).toUpperCase()).join(''),
  }))}));
}
