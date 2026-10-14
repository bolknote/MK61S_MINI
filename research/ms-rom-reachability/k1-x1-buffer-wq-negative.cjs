#!/usr/bin/env node
'use strict';
// Counterexample: W/Q exchange overwrites the newly retained P0 in X1.
// This rejects only this composition, NOT full K1 or every use of X1.
const assert=require('node:assert/strict');
const buffer=require('./k1-x1-buffer-reader.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const defaults={...historical.defaults,incoming:'-6.5432109E65',
  values:['12345678','-9.8765432E99','-1E-99','844']};
function finish(c,o={},record=()=>{}) {
  buffer.prime(c,o,record);
  record('buffer-wq');c.press('↔').runFrames(8);
}
function check(r) {
  const p=r.beforeRegisters[0],w=r.before.W.slice(2),q=r.before.Q.slice(2);
  const before=checks.boundary(r,'buffer-wq'),end=checks.boundary(r,'done');
  assert.equal(raw(before.ring.X1),p);
  assert.equal(raw(before.ring.U,0),buffer.marker);
  assert.equal(new Set(snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words).size,23);
  const read=r.traced.events.find(e=>e.stage==='buffer-wq'&&e.ip===0xEE);
  assert.deepEqual([read.slot,read.raw],['W',w]);
  const save=r.traced.events.find(e=>e.stage==='buffer-wq'&&e.ip===0xE9);
  assert.deepEqual([save.slot,raw(save.r,0)],['X1',w]);
  const expected=ringAt(r,save.command);
  for(let i=0;i<12;i++)expected.X1[1+3*i]=save.r[3*i];
  assert.deepEqual(ringAt(r,save.command+1),expected,'E9 changes only X1 among all 630 tetras');
  assert.equal(raw(end.ring.X1),w);
  assert.equal(r.after.W,r.before.W.slice(0,2)+q);
  assert.equal(r.after.Q,r.before.Q.slice(0,2)+w);
  const pair=r.traced.writes.filter(x=>x.command>=before.command&&x.chip===4&&[0x4E,0x2A].includes(x.ip));
  assert.deepEqual(pair.map(x=>[x.ip,x.slot,x.nibble]),
    [[0x4E,'W'],[0x2A,'Q']].flatMap(([ip,n])=>Array.from({length:12},(_,i)=>[ip,n,1+3*i])));
  const pairExpected=ringAt(r,pair[0].command),pairBefore=structuredClone(pairExpected);
  for(let i=0;i<12;i++) {
    pairExpected.W[1+3*i]=pairBefore.Q[1+3*i];
    pairExpected.Q[1+3*i]=pairBefore.W[1+3*i];
  }
  assert.deepEqual(ringAt(r,pair.at(-1).command+1),pairExpected,'exact W/Q pair among all 630 tetras');
  checks.protectedFields(r,[0],['U','W','Q']);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((x,i)=>i===0?buffer.marker:x));
  const uBefore=before.ring.U,uAfter=end.ring.U;
  for(let i=0;i<42;i++)if(![28,31,34].includes(i))assert.equal(uAfter[i],uBefore[i]);
  assert.deepEqual([uAfter[34],uAfter[31]],[1,15]);
  const live=[...snapshotFromRing(end.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(end.ring[n]))];
  assert.ok(!live.includes(p),'original P0 is absent from stored and five stack words');
  assert.ok(!live.includes(r.before.U.slice(2)),'original U header also remains unrepaired');
  return {expectedFailure:true,exchangeWQ:true,bufferClobberedAt:save.command,
    missingStoredOrigins:['ordinary P0','Ms U'],fullK1Impossible:false};
}
if(require.main===module) {
  const a=keyboard.record(defaults,finish);
  assert.deepEqual(a,keyboard.record({...defaults,incoming:'not read',values:['not read']},finish));
  const r=capture.run(defaults,finish);
  console.log('PASS rejected buffered W/Q composition:',JSON.stringify(check(r)));
  if(process.env.K1_X1_UNOBSERVED)console.log('PASS observer-free negative:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,finish));
}
module.exports={defaults,finish,check};
