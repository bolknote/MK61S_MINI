#!/usr/bin/env node
'use strict';
// Negative controls for specific proposed extensions, never a proof that
// every user program or every exponent-edit timing must fail.
const assert=require('node:assert/strict');
const programProbe=require('./probe_ms_program_transfer.cjs');
const shifted=require('./probe_ms_shifted_swap.cjs');

function checkProgram(marker) {
  const r=programProbe.run(marker?{marker}:{});
  assert.equal(r.before.U,'00958912345678');
  assert.equal(r.afterRegisters[1],'000000000000');
  assert.ok(!r.traced.events.some(e=>e.ip===0xD4),'the intended store was never reached');
  assert.notDeepEqual(r.afterProgram,r.beforeProgram,'this is not a program-preserving reader');
  if(marker==='register') {
    assert.equal(r.beforeRegisters[8],'0000F0000000');
    assert.deepEqual(r.after,{...r.before,U:'009F8912345678',W:r.before.V,Q:'00000000000000'});
    assert.ok(r.traced.writes.some(w=>w.chip===4&&w.ip===0x27&&w.slot==='U'&&w.nibble===31&&w.before!==w.value));
  } else {
    assert.deepEqual(r.after,{...r.before,W:'00000010000000',Q:r.before.W,P7:r.before.Q});
  }
  console.log('PASS: negative control:',marker??'logical marker',
    'in this user program misses D4 and changes both Ms and program.');
}

function checkExponent() {
  const r=shifted.run({lifts:1,sourceKey:['ВП','0'],save:false});
  assert.equal(r.before.U,'00958912345678');
  assert.deepEqual(r.after,r.before);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  const writes=r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.deepEqual(writes,[],'no temporary numeric/service Ms changes either');
  const writers=r.traced.events.filter(e=>e.stage==='shifted-swap'&&e.ip===0xE7);
  assert.ok(writers.length>0);assert.ok(writers.every(e=>e.slot==='X'));
  assert.ok(!r.traced.events.some(e=>e.stage==='shifted-swap'&&e.ip===0x34));
  console.log('PASS: negative control: false marker Y + ВП 0 writes X, leaves U unchanged; no header repair.');
}

if(require.main===module){checkProgram();checkProgram('register');checkExponent();}
module.exports={checkProgram,checkExponent};
