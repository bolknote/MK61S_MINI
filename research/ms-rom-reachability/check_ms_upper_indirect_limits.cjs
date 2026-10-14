#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_upper_indirect.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
function main() {
  const zero=p.run({pointer:'0'});
  assert.equal(zero.afterRegisters[0],zero.before.P8.slice(2));
  assert.notEqual(zero.afterRegisters[0],zero.before.P7.slice(2));
  assert.equal(zero.afterRegisters[1],zero.beforeRegisters[1]);
  assert.deepEqual(zero.afterProgram,zero.beforeProgram);
  console.log('PASS: pointer=0 selects P0, overwrites the fifth-word backup, and leaves P1 untouched.');
  for(const phaseOffset of [0,1]) {
    const r=p.run({phaseOffset,afterKeys:[['↔']]}),es=r.traced.events;
    assert.equal(r.afterRegisters[0],r.before.P7.slice(2));
    assert.equal(r.afterRegisters[1],r.before.P8.slice(2));
    assert.deepEqual(r.afterProgram,r.beforeProgram);
    const controls=es.filter(e=>e.stage==='upper-after-1'&&e.ip===0x9C&&e.nextIp===0x9E);
    const pair=es.filter(e=>e.stage==='upper-after-1'&&e.otherChips?.[4].ip===0x4E);
    assert.ok(pair.length>0);
    if(phaseOffset===0) {
      assert.equal(controls[0].slot,'W');assert.equal(pair[0].otherChips[4].slot,'X');
      assert.equal(r.after.P7,r.before.P8);assert.equal(r.after.P8,r.before.P7);
      assert.notEqual(r.after.Q,r.before.V);
    } else {
      assert.equal(controls[0].slot,'control');assert.equal(pair[0].otherChips[4].slot,'P7');
      assert.equal(r.after.P7,r.before.P7);assert.equal(r.after.P8,r.before.P8);
    }
    console.log('PASS: one extra exchange, phase',phaseOffset,
      phaseOffset===0?'swaps visible X/Y, leaves Ms pair reversed, and changes Q.':'restores the Ms pair.');
  }
  console.log('COUNTEREXAMPLE: a second exchange is not a phase-independent inverse or a safe exit.');
  const lost=p.run({stress:true,upperValues:['-1E-99','0','333','444']});
  assert.equal(lost.before.P7.slice(2),'000000000000');assert.equal(lost.before.P8.slice(2),'901910000000');
  const overwrite=lost.traced.events.find(e=>e.stage==='upper-swap'&&e.ip===0xE7&&e.slot==='P7'&&e.nextIp===0x47);
  assert.ok(overwrite);assert.equal(overwrite.raw,lost.before.P8.slice(2));assert.equal(raw(overwrite.r,0),'000000000000');
  assert.equal(lost.afterRegisters[1],'000000000000');
  console.log('PASS: zero-fifth counterexample also affects the original pointer=1 reader: the swap formatter erases sixth before its backup.');
}
if(require.main===module)main();
