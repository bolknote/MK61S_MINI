#!/usr/bin/env node
'use strict';
// An exact partial-entry contract, not a permutation, return or full K1.
const assert=require('node:assert/strict');
const p=require('./k1-two-hole-prefix.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const same=(a,b)=>assert.deepEqual(a,b),m='9990FFFFFFF0',g='958912345678',z='000000000000';
function scratchRead(r,prefix,t,s,endStage) {
  const first=checks.boundary(r,prefix+'attempt-0/duplicate');
  const w=raw(first.ring.W),before=snapshotFromRing(first.ring).words;let attempts=0;
  for(let i=0;i<3;i++) {
    const stage=prefix+'attempt-'+i+'/';
    if(!r.traced.events.some(e=>e.stage===stage+'store'))break;
    attempts++;
    const input=checks.boundary(r,stage+'store');
    same(['X','Y','Z','T'].map(n=>raw(input.ring[n])),[z,t,s,m]);
    const source=r.traced.events.find(e=>e.stage===stage+'store'&&e.ip===0xEE);
    assert.ok(source&&['W','X'].includes(source.slot));same(source.raw,source.slot==='W'?w:z);
    const clean=checks.exactPush(r,stage+'clean',['X','Y','Z','T']);same(clean.displaced,m);
    const next=r.traced.events.find(e=>e.stage===prefix+'attempt-'+(i+1)+'/retry-0'&&e.ring)
      ??checks.boundary(r,endStage);
    same(['X','Y','Z','T'].map(n=>raw(next.ring[n])),[source.raw,z,t,s]);
    const wanted=before.slice();wanted[0]=source.raw;
    same(snapshotFromRing(next.ring).words,wanted,'only explicitly disposable P0 changes');
  }
  same(raw(checks.boundary(r,endStage).ring.X),w);
  return attempts;
}
function check(r) {
  assert.ok(!r.options.swaps&&!r.options.clearBeforeSwap&&!r.options.stopAfterGuard&&!r.options.signBuffer&&!r.options.zeroGuard);
  checks.protectedFields(r,[0],['U','V','W']);
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2)),originalP=r.beforeRegisters[0];
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:u));
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+m,V:r.before.V.slice(0,2)+g,
    W:r.before.W.slice(0,2)+originalP});
  const end=checks.boundary(r,'done');
  same(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[m,v,w,m]);
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  assert.equal(new Set(original).size,23);assert.ok(!original.includes(g),'guard must not masquerade as an origin');
  let boundaries=0;const seen=new Set();
  for(const e of r.traced.events)if(e.ring&&!seen.has(e.stage)) {
    seen.add(e.stage);boundaries++;
    const live=[...snapshotFromRing(e.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]))];
    for(const word of original)assert.ok(live.includes(word),'lost '+word+' at '+e.stage);
  }
  const attempts=[scratchRead(r,'read-v/',w,originalP,'compact-v-w'),
    scratchRead(r,'read-u/',v,w,'prepare-marker-rotate-0')];
  const pushes=['park-p0/push','park-guard/push','plant-u'].map(stage=>checks.exactPush(r,stage,['T','U','V','W']));
  same(pushes.map(x=>x.displaced),[w,v,u]);
  return {phase:r.options.phaseOffset??0,attempts,boundaries,all23RetainedAtEveryBoundary:true,
    ordinaryP0:u,lowerMs:[m,g,originalP,q],visible:[m,v,w,m],pushes,
    fullK1:false,workingExit:false,upperEntryComplete:false};
}
function surface() {
  const outputs=[];
  for(const ds of [['1,','2,','3,'],['0,','1,','0,','2,','0,','0,','3,']]) {
    const a=control.record(ds,{},p.finish);
    same(a,control.record(ds,{incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},p.finish));
    same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
    const frames=keys*2+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
    outputs.push({keys,frames,publicDisplayOnly:true,attempts:ds.length});
  }
  return outputs;
}
function checkSwapLoss(r) {
  assert.equal(r.options.swaps,1);assert.ok(!r.options.clearBeforeSwap&&!r.options.zeroGuard);
  checks.protectedFields(r,[0],['U','V','W']);
  const at=checks.boundary(r,'clone-swap-0'),end=checks.boundary(r,'done');
  const v=r.before.V.slice(2),original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  const available=e=>[...snapshotFromRing(e.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]))];
  assert.ok(original.every(w=>available(at).includes(w)));
  same(original.filter(w=>!available(end).includes(w)),[v]);
  const request=r.traced.events.find(e=>e.stage==='clone-swap-0'&&e.ip===0xA3&&e.slot==='Y');
  assert.ok(request);same(raw(request.m),v);
  const header=ringAt(r,request.command);
  for(let j=0;j<3;j++)header.Y[28+3*j]=request.r[27+3*j];
  same(ringAt(r,request.command+1),header,'request corrupts only three Y header tetras');
  const copies=r.traced.writes.filter(w=>w.command>request.command&&w.chip===4&&w.ip===0x2A&&w.slot==='Y');
  same(copies.map(w=>w.nibble),Array.from({length:12},(_,j)=>1+3*j));
  assert.ok(copies.every(w=>w.command===copies[0].command));
  const expected=ringAt(r,copies[0].command);
  for(let j=0;j<12;j++)expected.Y[1+3*j]=parseInt(m[11-j],16);
  same(ringAt(r,copies[0].command+1),expected,'secondary chip replaces all twelve Y tetras with marker');
  return {lostOldV:v,firstHeaderCorruption:request.command,fullReplacement:copies[0].command,
    replacementValue:m,all23HeldBeforeRejectedStep:true,
    fullK1:false,rejectedContinuation:true};
}
if(require.main===module) {
  console.log('PASS keyboard surface:',JSON.stringify(surface()));
  const o=JSON.parse(process.env.K1_HOLE_OPTIONS||'{}');
  if(process.env.K1_HOLE_NEGATIVE){assert.equal(process.env.K1_HOLE_NEGATIVE,'plain');o.swaps=1;o.clearBeforeSwap=false;}
  const r=p.run(o);
  console.log(process.env.K1_HOLE_NEGATIVE?'PASS rejected swap continuation:':'PASS conditional two-hole prefix:',
    JSON.stringify(process.env.K1_HOLE_NEGATIVE?checkSwapLoss(r):check(r)));
  if(process.env.K1_HOLE_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,p.finish));
}
module.exports={scratchRead,check,surface,checkSwapLoss};
