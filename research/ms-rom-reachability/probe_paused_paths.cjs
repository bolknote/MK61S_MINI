#!/usr/bin/env node
'use strict';
// Trace selected, structurally motivated keys from the real paused state.
// Exported trace data are observations; there is no state-loading interface.
const {fields, snapshot, preparePaused} = require('./paused_keyboard_state.cjs');

function tracePaused(keys) {
  const calc = preparePaused(), chip = calc.ik1302;
  const initial = snapshot(chip), original = chip.tick;
  const entries = [], primitives = [], bootstrap = [], checkpoints = [];
  let key = null, command = 0, before;
  chip.tick = function () {
    if (this.tickIndex === 0) {
      before = {...fields(this), r5:this.r[5], r0:this.r[0], r35:this.r[35],
        r29:this.r[29], s1:this.s1, vector:this.r[37]+16*this.r[40],
        sp:[0,1,2].map(i => this.stack[36+i]+16*this.stack[39+i]), key,
        command:command++};
      if ([0xC7,0xC8].includes(before.ip)) primitives.push(before);
      if (before.ip === 0x60 && before.r38 === 9 && before.r26 === 1 &&
          before.r2 >= 5 && before.r25 === before.r31) bootstrap.push(before);
      if ([0x7C,0x77].includes(before.ip) ||
          (before.ip === 0x60 && before.r25 === before.r31))
        checkpoints.push({fields:before,snapshot:snapshot(this)});
    }
    const result = original.call(this);
    if (this.tickIndex === 0) {
      const after = fields(this);
      const entry = {...before, next:after.ip, afterR2:after.r2,
        afterR26:after.r26, afterR38:after.r38, afterPC:after.pc};
      // Suppress only identical self-loop repetitions. Counts retain the
      // duration; every primitive and bootstrap check above remains uncapped.
      const last = entries.at(-1);
      const signature = e => JSON.stringify({...e, command:0, count:0});
      if (last && entry.ip === entry.next && signature(entry) === signature(last))
        last.count++;
      else entries.push({...entry,count:1});
    }
    return result;
  };
  try {
    for (key of keys) calc.press(key);
    key = null;
    calc.runFrames(4);
  } finally {
    chip.tick = original;
  }
  return {keys,initial,entries,final:snapshot(chip),primitives,bootstrap,checkpoints};
}

if (require.main === module)
  console.log(JSON.stringify(tracePaused(process.argv.slice(2))));
module.exports = {tracePaused};
