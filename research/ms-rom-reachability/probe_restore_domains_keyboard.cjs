#!/usr/bin/env node
'use strict';
// Read-only boundary observations during explicitly chosen keyboard tests.
const assert = require('node:assert/strict');
const {MK61, preparePaused} = require('./paused_keyboard_state.cjs');
const indices = [0, 1, 2, 3, 4, 5, 30, 31, 32, 33, 34, 35];

function observe(name, calc, action, expectedPrimitives=[]) {
  const chip = calc.ik1302, tick = chip.tick;
  const records = [], seen = new Set(), ac = [], primitives = [];
  let previous = null, beforeFirstMs=true;
  chip.tick = function () {
    if (this.tickIndex === 0) {
      const ip = this.r[36]+16*this.r[39];
      if (ip === 0xC7 || ip === 0xC8) {
        primitives.push(ip);
        beforeFirstMs=false;
      }
      const interior = (previous === 0x93 && ip === 0x94) ||
        (previous === 0x12 && ip === 0xC6);
      previous = ip;
      const row = {ip, sp:[0,1,2].map(i => this.stack[36+i]+16*this.stack[39+i]),
        vector:this.r[37]+16*this.r[40], s1:this.s1, r38:this.r[38],
        r26:this.r[26], r35:this.r[35], r41:this.r[41], s:this.s,
        values:[...indices.map(i => this.r[i]), ...indices.map(i => this.stack[i])]};
      if (!interior && beforeFirstMs) {
        const signature = JSON.stringify(row);
        if (!seen.has(signature)) {
          seen.add(signature);
          records.push(row);
        }
      }
      if (ip === 0xAC) ac.push({r1:this.r[1], pc:this.r[31]+16*this.r[34],
        st32:this.stack[32], st35:this.stack[35], sp:row.sp});
    }
    return tick.call(this);
  };
  try { action(calc); } finally { chip.tick = tick; }
  assert.deepEqual(primitives, expectedPrimitives, name+' unexpected Ms entry count');
  return {name, records, ac, primitives};
}

function run() {
  const results = [];
  results.push(observe('manual_pc58_arithmetic', new MK61(), calc => {
    calc.pressSequence(['БП', '5', '8']);
    assert.equal(calc.programCounter(), '58');
    calc.inputNumber('12345673', {clear:true});
    calc.pressSequence(['В↑', '1', '+']);
    assert.equal(calc.programCounter(), '58');
  }));
  results.push(observe('L2_program_read', new MK61(), calc => {
    calc.pressSequence(['F','ВП','F','БП','0','3','С/П','С/П','F','/-/','В/О']);
    assert.deepEqual([0,1,2,3].map(i => calc.readCommand(i)), [0x58,3,0x50,0x50]);
    calc.inputNumber('1', {clear:true}).pressSequence(['X→П','2']);
    calc.inputNumber('12345673', {clear:true}).pressSequence(['В/О','С/П']);
    calc.runFrames(4);
  }));
  results.push(observe('paused_entry_and_PRG', preparePaused(), calc => {
    calc.inputNumber('1E13', {clear:true});
    calc.pressSequence(['F','ВП','K','1','K','2','F','/-/']);
    calc.runFrames(4);
  }));
  results.push(observe('memory_read_and_negative_exponent', new MK61(), calc => {
    calc.pressSequence(['БП','5','8']);
    calc.inputNumber('-1E-3', {clear:true}).pressSequence(['X→П','0','Сx','П→X','0','В↑','+']);
  }));
  const {prepare}=require('./check_600_keyboard.cjs');
  results.push(observe('real_AC_PC58_exponent600',prepare(true),calc=>{
    calc.pressSequence(['В/О','С/П']);calc.runFrames(12);
    calc.pressSequence(['БП','5','8','↔']);calc.runFrames(5);
  }));
  results.push(observe('real_AC_high_R1_exponent580',
    prepare(true,{input:'1E72',multiplier:'1.0000005E4'}),calc=>{
      calc.pressSequence(['В/О','С/П']);calc.runFrames(6);
    }));
  results.push(observe('raw_PC9C_saved_tail',new MK61(),calc=>{
    calc.pressSequence(['БП','9','ВП']);
    assert.equal(calc.programCounter(),'9С');
    calc.inputNumber('12345673',{clear:true}).pressSequence(['В↑','1','+']);
    assert.equal(calc.programCounter(),'9С');
  }));
  const {prepare700,finish700,prepareWrapped1200}=require('./check_tail_sources_keyboard.cjs');
  results.push(observe('real_700_persistent_tail',prepare700(),finish700));
  results.push(observe('real_1200_wraps_to_200',prepareWrapped1200(),calc=>{
    calc.pressSequence(['В/О','С/П']).runFrames(12);
  }));
  const {finishSignature700,prepareCombined,finishCombined}=require('./check_ac_signature_keyboard.cjs');
  results.push(observe('joint_AC_PC58_R1_5_ST32_F_ST35_9',prepare700(),finishSignature700));
  results.push(observe('joint_AC_and_real600_counter_zero',prepareCombined(),finishCombined));
  // The cover stops at the FIRST Ms primitive. Do not validate later states
  // against pre-C8 invariants; the witness itself separately checks its exits.
  results.push(observe('real_first_C8_keyboard_prefix',prepareCombined({counter:1}),
    finishCombined,[0xC8,0xC8,0xC8]));
  const accessible = results[0].ac.filter(row => row.pc === 0x58);
  assert.ok(accessible.length, 'AC with genuine manually selected PC58');
  assert.ok(accessible.every(row => row.r1 === 0 && row.st32 === 0 && row.st35 === 0),
    'ordinary arithmetic does not prepare the artificial AC/A9 signature');
  return results;
}

if (require.main === module) {
  const results = run();
  if (process.argv.includes('--json')) console.log(JSON.stringify(results));
  else for (const row of results) console.log(`PASS ${row.name}: `+
    `${row.records.length} distinct pre-Ms boundary observations, ${row.ac.length} AC entries, `+
    `${row.primitives.length} Ms entries`);
}
module.exports = {run};
