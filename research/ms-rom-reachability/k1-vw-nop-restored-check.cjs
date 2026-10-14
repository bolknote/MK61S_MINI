#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-vw-nop-restored.cjs');
const nop=require('./k1-vw-nop-read-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {snapshotFromRing,analyzeTrace}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const same=(a,b)=>assert.deepEqual(a,b);
function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicDisplayOnly:true,initialPhaseOffsetExcluded:true,assumedSuccessfulAttempts:1};
}
function check(r) {
  const start=checks.boundary(r,'restore/first/push-marker-0');
  const prefix=nop.clean(r,start.stage);
  const post=r.options.verifyExit?checks.boundary(r,'post/program').command:Infinity;
  checks.protectedFields({...r,traced:{...r.traced,
    events:r.traced.events.filter(e=>e.command<post),writes:r.traced.writes.filter(w=>w.command<post),
    primitives:r.traced.events.filter(e=>e.command<post&&[0xC7,0xC8].includes(e.ip)).map(e=>e.ip)}},
    [0],['U','V','W','Q']);
  assert.ok(r.traced.writes.filter(w=>w.command>=post&&
    ((w.nibble%3===0&&w.nibble<36)||(Object.hasOwn(r.before,w.slot)&&w.nibble%3===1)||
      [36,37,39,40].includes(w.nibble))).every(w=>w.before===w.value),
    'program execution preserves all stored words and numerical service tetras');
  const [u,v,w,q,a]=['U','V','W','Q','P7'].map(n=>r.before[n].slice(2));
  const p=r.beforeRegisters[0],end=checks.boundary(r,r.options.verifyExit?'post/manual':'done');
  const pushes=['first','second'].map(s=>checks.exactPush(r,'restore/'+s+'/push',['T','U','V','W']));
  same(pushes.map(x=>x.displaced),[a,'000010000000']);
  same(['U','V','W','Q'].map(n=>raw(end.ring[n])),[u,q,v,p]);
  same(r.after,{...r.before,U:r.before.U,V:r.before.V.slice(0,2)+q,
    W:r.before.W.slice(0,2)+v,Q:r.before.Q.slice(0,2)+p});
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15),['marker']);
  const mapping=Array.from({length:23},(_,i)=>i);
  mapping[0]=17;mapping[16]=18;mapping[17]=16;mapping[18]=0;
  const audit=analyzeTrace({beforeEvent:r.traced.events.find(e=>e.ring),afterEvent:end,
    writes:r.traced.writes,expectedMapping:mapping});
  same(audit.fixture.distinct,true);same(audit.data.bijection,true);
  same(audit.fixedMapping.status,'matches_this_fixture');
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  const allowed=new Set(pushes.flatMap(p=>[p.command+1,p.command+2,p.command+3]));
  for(const wr of r.traced.writes.filter(w=>w.command>=start.command&&w.command<post&&w.before!==w.value)) {
    if(wr.nibble%3===0)assert.fail('ordinary register changed during restoration: '+JSON.stringify(wr));
    if(Object.hasOwn(r.before,wr.slot))assert.ok(wr.chip===3&&allowed.has(wr.command)&&
      ['U','V','W'].includes(wr.slot)&&wr.nibble%3===1&&wr.nibble<37,
      'undeclared Ms change during restoration: '+JSON.stringify(wr));
  }
  if(r.options.verifyExit) {
    same(r.beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50]);
    same(raw(checks.boundary(r,'post/zero').ring.X),'000050000000');
    same(raw(checks.boundary(r,'post/program').ring.X),'000000000000');
    const final=checks.boundary(r,'done');same(raw(final.ring.X),'000050000000');
    same(snapshotFromRing(final.ring).words,snapshotFromRing(end.ring).words);
    same(Object.keys(final.ring).filter(n=>final.ring[n][22]===15),['marker']);
  }
  return {prefix,boundaries:rows.length,pushes,all23BackInStoredWords:true,
    mapping,allExtraMarkersRemoved:true,programServiceAndOther14OrdinaryHeld:true,
    workingExitTested:!!r.options.verifyExit,upperWordsUnchanged:true,fullK1:false};
}
if(require.main===module) {
  const o={verifyExit:true,...JSON.parse(process.env.K1_RESTORED_OPTIONS||'{}')};
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS restored:',JSON.stringify(check(r)));
  if(process.env.K1_RESTORED_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,check};
