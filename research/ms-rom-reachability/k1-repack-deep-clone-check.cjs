#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-repack-deep-clone-probe.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repackChecks=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {M1_SLOTS}=require('./k1-permutation-oracle.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const m='9990FFFFFFF0',zero='000000000000';
const markers=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
function check(r,endStage='done') {
  if(endStage==='done')assert.ok(!(r.options.afterClone??[]).length);
  const end=checks.boundary(r,endStage);
  // A prefix view of an already recorded, uninterrupted native run. This
  // does not restore or inject machine state, or shorten the actual protocol.
  if(endStage!=='done')r={...r,
    after:Object.fromEntries(Object.keys(r.before).map(n=>[n,raw(end.ring[n],1,14)])),
    afterRegisters:M1_SLOTS.map(n=>raw(end.ring[n],0)),
    traced:{...r.traced,events:r.traced.events.filter(e=>e.command<=end.command),
      writes:r.traced.writes.filter(e=>e.command<end.command)}};
  checks.protectedFields(r,[0],['U','V','W','Q']);
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const values=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
  const rows=repackChecks.boundaryLosses(r);
  assert.ok(rows.every(x=>!x.missing.length),JSON.stringify(rows.filter(x=>x.missing.length)));
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  const free=checks.boundary(r,'w-to-x-0');
  same(raw(free.ring.U,0),zero);
  same(values(free),[p,zero,zero,u,w]);
  same(markers(free),['marker']);
  const readInput=checks.boundary(r,'read-q/attempt-0/read-prep-0');
  same(raw(readInput.ring.U,0),w);same(raw(readInput.ring.X),u);
  const readEnd=checks.boundary(r,'payload-rotate-0');
  same(raw(readEnd.ring.U,0),w);same(values(readEnd).slice(1),[q,zero,u,w]);
  const at=checks.boundary(r,'clone-sign');
  same(values(at),['00008FFFFFFF',m,u,q,m]);
  same(['U','V','W','Q'].map(n=>raw(at.ring[n])),[v,u,q,p]);
  const es=r.traced.events.filter(e=>e.stage==='clone-sign');
  if(r.options.clonePhase===0) {
    same(r.after,{...r.before,U:r.before.U.slice(0,2)+v,V:r.before.V.slice(0,2)+u,
      W:r.before.W.slice(0,2)+q,Q:r.before.Q.slice(0,2)+p});
    same(values(end),[q,m,'32'+q[2]+u.slice(3),q,m]);
    const ctrl=es.find(e=>e.ip===0x9C);same([ctrl.slot,ctrl.nextIp],['control',0x9E]);
    const ee=es.find(e=>e.ip===0xEE);same([ee.slot,ee.raw],['W',q]);
    const copy=es.find(e=>e.ip===0xE9);repackChecks.exactCopy(r,copy,'X1',q);
    const request=es.find(e=>e.ip===0xA3);same(request.slot,'Y');
    same(markers(end),['T','X','marker']);
    return {boundaries:rows.length,rejected:'unshifted clone request misses V',all23HeldAtEveryBoundary:true,
      control:ctrl.command,read:ee.command,copy:copy.command,request:request.command,fullK1:false};
  }
  same(r.options.clonePhase,1);
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+v,V:r.before.V.slice(0,2)+m,
    W:r.before.W.slice(0,2)+m,Q:r.before.Q.slice(0,2)+p});
  same(values(end),['00008FFFFFFF','000010000000',u,q,m]);
  same(markers(end),['T','V','W','marker']);
  const first=es.findIndex(e=>e.ip===0x9C),route=es.slice(first,first+25);
  const ips=[0x9C,0x9E,0x9F,0xA0,...Array(5).fill(0xE5),0xE6,0xED,0xEE,0xA1,
    0xE5,0xE5,0xE6,0xE9,...Array(7).fill(0xA2),0xA3];
  const names=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
  same(route.map(e=>[e.ip,e.slot]),ips.map((ip,i)=>[ip,names[(7+i)%15]]));
  same(route[0].nextIp,0x9E);same(raw(route[0].m),v);
  same([route[0].r[30],route[0].r[33]],[2,3]);same(route[11].raw,m);
  repackChecks.exactCopy(r,route[16],'V',m);
  const lateRead=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);assert.ok(lateRead);
  same([lateRead.slot,lateRead.raw],['X',m]);
  const late=es.find(e=>e.command>lateRead.command&&e.ip===0xE7);
  same(raw(late.m),q);repackChecks.exactCopy(r,late,'W',m);
  return {boundaries:rows.length,all23HeldAtEveryBoundary:true,upper4AndOther14OrdinaryAndProgramHeld:true,
    control:route[0].command,read:route[11].command,cloneV:route[16].command,
    request:route[24].command,lateRead:lateRead.command,cloneW:late.command,
    live:{ordinaryP0:'w',visibleY:'u',visibleZ:'q',msU:'v',msQ:'p'},
    remainingMarkers:['T','V','W'],workingExit:false,upperExchange:false,fullK1:false};
}
function surface(o={clonePhase:1}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  const frames=2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  return {keys,frames,publicDisplayOnly:true,assumedSuccessfulAttempts:1,initialPhaseOffsetExcluded:true};
}
if(require.main===module) {
  const o=JSON.parse(process.env.K1_DEEP_OPTIONS||'{}');
  console.log('PASS keyboard surface:',JSON.stringify(surface({clonePhase:o.clonePhase??1})));
  const r=probe.run(o);console.log('PASS conditional deeper entry:',JSON.stringify(check(r)));
  if(process.env.K1_DEEP_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={check,surface};
