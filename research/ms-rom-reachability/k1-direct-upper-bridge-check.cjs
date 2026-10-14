#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const bridge=require('./k1-direct-upper-bridge.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {pair}=require('./k1-first-upper-bridge-check.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const same=(a,b)=>assert.deepEqual(a,b),m='9990FFFFFFF0',z='000000000000';
function check(r) {
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);
  const [u,v,w,q,a]=['U','V','W','Q','P7'].map(n=>r.before[n].slice(2));
  const p=r.beforeRegisters[0],at=s=>checks.boundary(r,s);
  const visible=s=>['X1','X','Y','Z','T'].map(n=>raw(at(s).ring[n]));
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:u));
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+m,
    V:r.before.V.slice(0,2)+'1F'+q[2]+'000000000',
    W:r.before.W.slice(0,2)+p,Q:r.before.Q.slice(0,2)+a,P7:r.before.P7.slice(0,2)+q});
  same(visible('tail-0').slice(1),[z,v,w,m]);
  same(visible('tail-1').slice(1),[z,z,v,w]);
  same(visible('tail-2').slice(1),[q,z,v,w]);
  same(visible('done'),[q,q,z,v,w]);
  same(Object.keys(at('done').ring).filter(n=>at('done').ring[n][22]===15),['marker','U']);
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  assert.equal(new Set(original).size,23);assert.ok(!original.includes(z));
  const seen=new Set();let boundaries=0;
  for(const e of r.traced.events)if(e.ring&&!seen.has(e.stage)) {
    seen.add(e.stage);boundaries++;
    const live=[...snapshotFromRing(e.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]))];
    for(const word of original)assert.ok(live.includes(word),'lost '+word+' at '+e.stage);
  }
  const secondary=r.traced.events.filter(e=>e.stage==='tail-2').map(e=>e.otherChips?.[4]);
  assert.ok(secondary.every(Boolean));
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
    exchange:pair(r,'tail-2','Q','P7'),ordinary14AndProgramHeld:true,
    remainingThreeUpperHeld:true,remainingMarker:'U',workingExit:false,completePair:false,fullK1:false};
}
function surface() {
  const ds=['1,','2,','3,'],a=control.record(ds,{},bridge.finish);
  same(a,control.record(ds,{incoming:'unread',values:['unread'],fullUpper:['unread'],p3:'unread'},bridge.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  const frames=keys*2+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  return {keys,frames,publicDisplayOnly:true,assumedSuccessfulAttempt:1};
}
function shortFailure(r) {
  same(r.options.phaseOffset,1);same(r.options.incoming,'201');
  same(r.options.values,['1','822','833','844']);
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);
  const [u,v,w,q,a]=['U','V','W','Q','P7'].map(n=>r.before[n].slice(2));
  const p=r.beforeRegisters[0],end=checks.boundary(r,'done');
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:u));
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+m,
    V:r.before.V.slice(0,2)+'1F0000000000',W:r.before.W.slice(0,2)+p,
    Q:r.before.Q.slice(0,2)+q,P7:r.before.P7.slice(0,2)+q});
  same(['X1','X','Y','Z','T'].map(n=>raw(end.ring[n])),[q,z,z,v,w]);
  const exchange=pair(r,'tail-2','Q','P7');
  const es=r.traced.events.filter(e=>e.stage==='tail-2');
  const read=es.find(e=>e.ip===0xEE&&e.sp[0]===0xE3);assert.ok(read);
  same([read.slot,raw(read.m)],['Q',q]);
  assert.ok(read.command<exchange.command,'formatter source read before secondary exchange');
  const overwrite=es.find(e=>e.command>exchange.command&&e.ip===0xE7&&e.slot==='Q');assert.ok(overwrite);
  same([raw(overwrite.m),raw(overwrite.r,0),overwrite.nextIp],[a,q,0x47]);
  const expected=ringAtLocal(r,overwrite.command);
  for(let j=0;j<12;j++)expected.Q[1+3*j]=overwrite.r[3*j];
  same(ringAtLocal(r,overwrite.command+1),expected,'late formatter writes only Q, erasing returned upper original');
  const originals=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  const seen=new Set();
  for(const e of r.traced.events)if(e.ring&&!seen.has(e.stage)) {
    seen.add(e.stage);
    const live=[...snapshotFromRing(e.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]))];
    same(originals.filter(n=>!live.includes(n)),e.stage==='done'?[a]:[]);
  }
  return {rejected:'short Q=1',exchange,sourceRead:read.command,
    overwrittenUpperOriginal:a,lateOverwrite:overwrite.command,all23Preserved:false,fullK1:false};
}
const ringAtLocal=require('./check_ms_clone_delayed_request.cjs').ringAt;
if(require.main===module) {
  console.log('PASS keyboard surface:',JSON.stringify(surface()));
  const r=bridge.run(process.env.K1_DIRECT_NEGATIVE?{phaseOffset:1,values:['1','822','833','844']}:
    JSON.parse(process.env.K1_DIRECT_OPTIONS||'{}'));
  console.log(process.env.K1_DIRECT_NEGATIVE?'PASS rejected short upper entry:':'PASS direct first-upper entry:',
    JSON.stringify(process.env.K1_DIRECT_NEGATIVE?shortFailure(r):check(r)));
  if(process.env.K1_DIRECT_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,bridge.finish));
}
module.exports={check,surface,shortFailure};
