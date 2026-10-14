#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_read6_guarded.cjs');
const {check:checkBackup}=require('./check_ms_read6_backup.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const guard='958912345678';
function check(r) {
  assert.equal(r.beforeRegisters[2],guard);assert.equal(r.afterRegisters[2],guard);
  checkBackup(r,{upperP8:guard});
  const es=r.traced.events,stage=es.filter(e=>e.stage==='upper-prime');
  const source=stage.find(e=>e.ip===0xD6);
  assert.equal(source.slot,'W');assert.equal(raw(source.m,0),guard,'ordinary P2, not a lower backup');
  const at=es.findIndex(e=>e.stage==='upper-prime'&&e.ip===0xE7&&e.slot==='P7'&&e.nextIp===0x47);
  assert.ok(at>=0);const write=checkSwapBlock(r,at,1);
  assert.equal(raw(write.body[0].r,0),guard);assert.equal(write.body[0].raw,r.before.P7.slice(2));
  assert.ok(stage.filter(e=>e.ip===0xE7).every(e=>['X','P7'].includes(e.slot)));
  const swap=es.filter(e=>e.stage==='upper-swap');
  const stale=swap.find(e=>e.ip===0xEE&&e.nextIp===0xE3);
  assert.ok(stale);assert.equal(stale.raw,guard);
  const format=swap.find(e=>e.ip===0xE7&&e.nextIp===0x47);
  assert.equal(format.slot,'X');assert.equal(raw(format.r,0),guard);
  const begin=es.find(e=>e.stage==='upper-after-0').command;
  assert.ok(r.traced.writes.filter(w=>w.command>=begin&&Object.hasOwn(r.before,w.slot)&&w.nibble%3===1)
    .every(w=>w.before===w.value),'sixth-word capture leaves guarded Ms unchanged');
}
function main() {
  const cases=[...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true,upperValues:['-1E-99','0','333','444']})),
    {phaseOffset:2,stress:true,values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
      upperValues:['6.5432109E-23','-8.7654321E-17','333','444']},
    {stress:true,upperValues:['0','0','333','444']},
    {stress:true,settleFrames:12,markerFrames:8}];
  let firstDigest;
  for(const o of cases) {
    const r=p.run(o);firstDigest??=digest(r.calc);check(r);
    console.log('PASS:',JSON.stringify(o),'six exact original Ms words saved; guard reuses P2; program and unrelated registers preserved.');
  }
  const plain=p.prepare(cases[0]);p.finish(plain,cases[0]);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);
  console.log('PASS: observed/unobserved complete core state:',firstDigest);
  console.log('LIMIT: lower Ms modified; Ms P8 holds guard; V marker remains. No cleanup, Ms restoration, or full K1 is claimed.');
}
if(require.main===module)main();
module.exports={check};
