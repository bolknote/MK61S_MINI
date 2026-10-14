#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_upper_guarded_read2.cjs');
const {check:checkExit}=require('./check_ms_upper_read2_exit.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const {analyze}=require('./probe_ms_swap_handoff.cjs');
const guard='958912345678';
function check(r) {
  const es=r.traced.events;
  const beforePrime=es.find(e=>e.stage==='upper-prime');
  assert.equal(raw(beforePrime.ring.marker,0),r.before.P7.slice(2),'fifth already backed up in ordinary P8');
  const read=es.find(e=>e.stage==='upper-prime'&&e.ip===0xD6);
  assert.ok(read);assert.equal(read.slot,'P7');assert.equal(raw(read.m,0),guard);
  const liftAt=es.findIndex(e=>e.stage==='upper-prime'&&e.ip===0xE7&&e.nextIp===0xA8);
  const lifted=checkSwapBlock(r,liftAt,4);
  assert.equal(raw(lifted.body[0].r,0),guard);
  assert.deepEqual(lifted.body.map(e=>e.slot),['X','Y','Z','T']);
  const guardAt=es.findIndex(e=>e.stage==='upper-prime'&&e.ip===0xE7&&e.slot==='P7'&&e.nextIp===0x47);
  assert.ok(guardAt>liftAt);
  const guarded=checkSwapBlock(r,guardAt,1);
  assert.equal(guarded.body[0].raw,r.before.P7.slice(2));assert.equal(raw(guarded.body[0].r,0),guard);
  const changed=r.traced.writes.filter(w=>w.command>=beforePrime.command&&w.command<=guarded.body[0].command&&
    Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.ok(changed.every(w=>w.slot==='P7'&&w.chip===3&&w.nibble<=34));
  const first=es.find(e=>e.stage==='upper-swap');
  assert.equal(raw(first.ring.P7),guard);assert.equal(raw(first.ring.P8),r.before.P8.slice(2));
  const swapAt=es.findIndex(e=>e.stage==='upper-swap'&&e.otherChips?.[4].ip===0x4E&&e.otherChips[4].slot==='P7');
  assert.ok(swapAt>=0);const pair=es.slice(swapAt,swapAt+3),a=pair[0].otherChips[4];
  assert.equal(raw(a.r,0),r.before.P8.slice(2));assert.equal(raw(a.m),guard);
  assert.deepEqual(pair.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),[[0x4E,'P7'],[0x2A,'P8'],[0x39,'P9']]);
  const expected=structuredClone(pair[0].ring);
  for(let i=0;i<12;i++){expected.P7[1+3*i]=a.r[3*i];expected.P8[1+3*i]=a.m[1+3*i];}
  assert.deepEqual(pair[2].ring,expected,'all 630 ring tetras after the guarded exchange');
  const writes=r.traced.writes.filter(w=>w.command>=pair[0].command&&w.command<pair[2].command);
  assert.equal(writes.length,24);assert.ok(writes.every(w=>w.chip===4&&w.nibble%3===1&&w.nibble<=34));
  const report=analyze(r);
  assert.equal(report.cached.m,guard);assert.equal(report.secondaryWrite.t-report.cached.t,1,
    'primary still caches the OLD fifth one whole command before the secondary exchange');
  assert.equal(report.formatter.slot,'X');assert.equal(report.formatter.a,guard);
  assert.equal(report.c9.length,0);
  checkExit(r,{upperP8:guard});
  return {read:report.cached.t,swap:report.secondaryWrite.t,format:report.formatter.t};
}
function main() {
  const complex={stress:true,values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
    upperValues:['6.5432109E-23','-8.7654321E-17','333','444']};
  const cases=[...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true,upperValues:['-1E-99','0','333','444']})),
    ...[0,1,2].map(phaseOffset=>({...complex,phaseOffset})),
    ...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true})),
    {stress:true,upperValues:['0','0','333','444']},
    {stress:true,upperValues:['0','222','333','444']},
    {stress:true,upperValues:['-9.8765432E99','1.2345678E99','333','444']},
    {...complex,settleFrames:12,markerFrames:8}];
  let firstDigest;
  for(const o of cases) {
    const r=p.run(o);firstDigest??=digest(r.calc);const times=check(r);
    console.log('PASS:',JSON.stringify(o),JSON.stringify(times),'guarded two-word backup; exact ring writes; marker removed; arithmetic and preserved program return 5.');
  }
  const plain=p.prepare(cases[0]);p.finish(plain,cases[0]);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);
  console.log('PASS: observed/unobserved complete core state:',firstDigest);
  console.log('LIMIT: all original fifth digits survive in ordinary P8, but Ms P8 now holds the guard. Lower Ms is also modified. NOT intact Ms or full K1.');
}
if(require.main===module)main();
module.exports={check};
