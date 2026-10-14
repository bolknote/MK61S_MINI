#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./k1-first-upper-bridge.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const same=(a,b)=>assert.deepEqual(a,b),m='9990FFFFFFF0',z='000000000000';
function pair(r,stage,left,right) {
  const es=r.traced.events,start=es.find(e=>e.stage===stage),next=es.find(e=>e.command>start.command&&e.stage!==stage);
  assert.ok(start&&next);
  const writes=r.traced.writes.filter(w=>w.command>=start.command&&w.command<next.command&&w.chip===4&&
    ((w.ip===0x4E&&w.slot===left)||(w.ip===0x2A&&w.slot===right)));
  same(writes.map(w=>[w.ip,w.slot,w.nibble]),[[0x4E,left],[0x2A,right]]
    .flatMap(([ip,n])=>Array.from({length:12},(_,i)=>[ip,n,1+3*i])));
  const expected=ringAt(r,writes[0].command),original=structuredClone(expected);
  for(let j=0;j<12;j++){expected[left][1+3*j]=original[right][1+3*j];expected[right][1+3*j]=original[left][1+3*j];}
  same(ringAt(r,writes.at(-1).command+1),expected,'exact '+left+'/'+right+' exchange among all 630 tetras');
  return {command:writes[0].command,left,right};
}
function check(r) {
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);
  const [u,v,w,q,a]=['U','V','W','Q','P7'].map(n=>r.before[n].slice(2)),oldP=r.beforeRegisters[0];
  const at=s=>checks.boundary(r,s),end=at('done');
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:u));
  // A3/ACK replace the two request-code tetras; the third request tetra
  // comes from the copied p word's exponent units, not a constant 2.
  const selector=oldP[2];
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+'1F'+selector+'0FFFFFFF0',
    V:r.before.V.slice(0,2)+'1F'+selector+'000000000',
    W:r.before.W.slice(0,2)+q,Q:r.before.Q.slice(0,2)+a,P7:r.before.P7.slice(0,2)+oldP});
  same(['X1','X','Y','Z','T'].map(n=>raw(end.ring[n])),[oldP,oldP,q,v,w]);
  same(['X','Y','Z','T'].map(n=>raw(at('clone-swap-0').ring[n])),[z,v,w,m]);
  same(['X','Y','Z','T'].map(n=>raw(at('tail-0').ring[n])),[q,v,w,m]);
  same(['X','Y','Z','T'].map(n=>raw(at('tail-1').ring[n])),[z,q,v,w]);
  same(Object.keys(at('tail-1').ring).filter(n=>at('tail-1').ring[n][22]===15),['marker','U']);
  same(raw(at('tail-2').ring.X),oldP);
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  assert.equal(new Set(original).size,23);assert.ok(!original.includes(z),'distinct from the generated zero');
  const seen=new Set();let boundaries=0;
  for(const e of r.traced.events)if(e.ring&&!seen.has(e.stage)) {
    seen.add(e.stage);boundaries++;
    const live=[...snapshotFromRing(e.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]))];
    for(const word of original)assert.ok(live.includes(word),'lost '+word+' at '+e.stage);
  }
  const secondary=r.traced.events.filter(e=>e.stage==='tail-2').map(e=>e.otherChips?.[4]);
  assert.ok(secondary.every(Boolean),'complete secondary-chip trace for the upper request');
  const writer=secondary.findIndex(e=>e.ip===0x4E&&e.slot==='Q');assert.ok(writer>=0);
  const source=secondary.findLastIndex((e,i)=>i<writer&&e.ip===0x53);assert.ok(source>=4);
  same([secondary[source].l,secondary[source].s1,...[32,35,41].map(i=>secondary[source].r[i])],[1,6,5,0,5]);
  same(raw(secondary[source].m),a);
  const route=secondary.slice(source-4,writer+3);
  same(route.map(e=>[e.ip,e.slot]),[
    [0x6E,'U'],[0x5E,'V'],[0x50,'W'],[0x52,'Q'],[0x53,'P7'],
    [0x4F,'P8'],[0x41,'P9'],[0x43,'P10'],[0x4D,'marker'],[0x60,'control'],
    ...['X1','X','Y','Z','T','U'].map(n=>[0x37,n]),
    [0x27,'V'],[0x61,'W'],[0x4E,'Q'],[0x2A,'P7'],[0x39,'P8']]);
  same(route[0].r[29],0);same(route[0].m[22],15);
  same([route[1].m[34],route[1].m[31]],[1,4]);
  return {phase:r.options.phaseOffset??0,boundaries,all23HeldAtEveryBoundary:true,
    exchanges:[pair(r,'clone-swap-0','W','Q'),pair(r,'tail-2','Q','P7')],
    firstUpperReceivesOriginalP0:true,firstUpperOriginalInQ:true,
    remainingThreeUpperHeld:true,ordinary14AndProgramHeld:true,
    remainingMarker:'U',workingExit:false,completePair:false,fullK1:false};
}
function surface() {
  const ds=['1,','2,','3,'];
  const a=control.record(ds,{},p.finish);
  same(a,control.record(ds,{incoming:'unread',values:['unread'],fullUpper:['unread'],p3:'unread'},p.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  const frames=keys*2+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  return {keys,frames,publicDisplayOnly:true,assumedSuccessfulAttempt:1};
}
function checkPhaseFailure(r) {
  // Deliberately fixed counterexample; do not generalize it to other data.
  assert.equal(r.options.phaseOffset,1);same(r.options.incoming,'201');
  same(r.options.values,['811','822','833','844']);
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);
  const [u,v,w,q,a]=['U','V','W','Q','P7'].map(n=>r.before[n].slice(2)),oldP=r.beforeRegisters[0];
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:u));
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+m,V:r.before.V.slice(0,2)+'1F2000000000',
    W:r.before.W.slice(0,2)+oldP,Q:r.before.Q.slice(0,2)+a,P7:r.before.P7.slice(0,2)+q});
  const at=s=>checks.boundary(r,s),end=at('done');
  same(['X1','X','Y','Z','T'].map(n=>raw(end.ring[n])),[q,q,z,z,w]);
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  const live=e=>[...snapshotFromRing(e.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]))];
  assert.ok(original.every(word=>live(at('clone-swap-0')).includes(word)));
  same(original.filter(word=>!live(at('tail-0')).includes(word)),[v]);
  same(original.filter(word=>!live(end).includes(word)),[v]);
  const lo=at('clone-swap-0').command,hi=at('tail-0').command;
  const copies=r.traced.writes.filter(x=>x.command>=lo&&x.command<hi&&x.chip===4&&x.ip===0x2A&&x.slot==='Y');
  same(copies.map(x=>x.nibble),Array.from({length:12},(_,j)=>1+3*j));
  assert.ok(copies.every(x=>x.command===copies[0].command&&x.value===0));
  const expected=ringAt(r,copies[0].command);
  for(let j=0;j<12;j++)expected.Y[1+3*j]=0;
  same(ringAt(r,copies[0].command+1),expected,'missed routing replaces Y by zero');
  return {rejectedPhase:1,lostOldV:v,zeroOverwrite:copies[0].command,
    upperPairStillExecutes:pair(r,'tail-2','Q','P7'),wrongUpperSource:q,requiredUpperSource:oldP,
    all23Preserved:false,safeRetry:false,fullK1:false};
}
if(require.main===module) {
  console.log('PASS keyboard surface:',JSON.stringify(surface()));
  const o=process.env.K1_BRIDGE_NEGATIVE?{phaseOffset:1}:JSON.parse(process.env.K1_BRIDGE_OPTIONS||'{}');
  const r=p.run(o);
  console.log(process.env.K1_BRIDGE_NEGATIVE?'PASS rejected phase:':'PASS conditional first-upper bridge:',
    JSON.stringify(process.env.K1_BRIDGE_NEGATIVE?checkPhaseFailure(r):check(r)));
  if(process.env.K1_BRIDGE_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,p.finish));
}
module.exports={pair,check,surface,checkPhaseFailure};
