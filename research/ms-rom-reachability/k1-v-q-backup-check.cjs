#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-v-q-backup.cjs');
const single=require('./k1-single-v-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {pair}=require('./k1-first-upper-bridge-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const m='9990FFFFFFF0',zero='000000000000';
const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
function check(r,negative=false,endStage='done') {
  if(endStage==='done')same(r.options.afterReserve??[],[]);
  const end=checks.boundary(r,endStage);
  checks.protectedFields(r,[0],['U','V','W','Q',...(endStage==='done'?[]:['P7'])]);
  assert.ok(r.traced.writes.filter(e=>e.command<end.command&&e.slot==='P7'&&e.nibble%3===1)
    .every(e=>e.before===e.value),'upper P7 held throughout the complete backup prefix');
  single.entry(r,'after-clone-phase');
  const [u,v,w,q,a]=['U','V','W','Q','P7'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const rows=repack.boundaryLosses(r).filter(e=>e.command<=end.command);
  assert.ok(rows.every(x=>!x.missing.length),JSON.stringify(rows.filter(x=>x.missing.length)));
  same(visible(checks.boundary(r,'after-clone-1')),['00008FFFFFFF',zero,u,q,m]);
  same(visible(checks.boundary(r,'after-clone-2')),['00008FFFFFFF',negative?a:q,zero,u,q]);
  const at=checks.boundary(r,'after-clone-0').command;
  assert.ok(r.traced.writes.filter(e=>e.command>=at&&e.command<end.command&&
    Object.hasOwn(r.before,e.slot)&&e.nibble%3===1)
    .every(e=>e.before===e.value),'all eight Ms unchanged during the backup continuation');
  const first=checks.exactPush(r,'after-clone-0',['X','Y','Z','T']);same(first.displaced,m);
  const paths=[1,2].map(i=>{
    const es=r.traced.events.filter(e=>e.stage==='after-clone-'+i);
    const source=es.find(e=>e.ip===0xEE),name=i===1?'W':'Q',value=i===1?q:p;
    same([source.slot,source.raw,source.nextIp],[name,value,i===1?0xE0:0xF0]);
    same([source.s1,source.r[23],source.r[26],source.r[29],...source.sp],
      [i===1?13:14,0,0,0,i===1?0xE0:0xF0,0x8E,0x9A]);
    const push=checks.exactPush(r,'after-clone-'+i,['X','Y','Z','T']);
    same(push.displaced,i===1?m:q);
    const lateRead=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);
    same([lateRead.slot,lateRead.raw],['P7',a]);
    const late=es.find(e=>e.command>lateRead.command&&e.ip===0xE7);
    repack.exactCopy(r,late,negative?'X':'P7',a);
    if(negative&&i===2)same(raw(late.m),p,'the read Q is really overwritten by the late formatter');
    return {source:source.command,slot:name,push,lateRead:lateRead.command,
      lateWrite:late.command,lateTarget:late.slot};
  });
  const after=Object.fromEntries(Object.keys(r.before).map(n=>[n,raw(end.ring[n],1,14)]));
  same(after,{...r.before,U:r.before.U.slice(0,2)+v,V:r.before.V.slice(0,2)+m,
    W:r.before.W.slice(0,2)+q,Q:r.before.Q.slice(0,2)+p});
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  same(visible(end),['00008FFFFFFF',negative?a:p,negative?a:q,zero,u]);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),['V','marker']);
  return {boundaries:rows.length,all23HeldAtEveryBoundary:true,paths,
    qBackedInY:!negative,pBackedInX:!negative,upper4AndOther14OrdinaryAndProgramHeld:true,
    workingExit:false,fullK1:false,...(negative?{rejected:'late P7 read overwrites the new Q copy'}:{})};
}
function guard(r) {
  same(r.options.afterReservePhase,1);
  same(r.options.afterReserve,[['K','5'],['↔']]);same(r.options.afterReserveWaits,[8,8]);
  const prefix=check(r,false,'after-reserve-phase'),rows=repack.boundaryLosses(r);
  assert.ok(rows.every(x=>!x.missing.length),JSON.stringify(rows.filter(x=>x.missing.length)));
  const [u,v,w,q,a]=['U','V','W','Q','P7'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const sign=r.traced.events.filter(e=>e.stage==='after-reserve-0');
  const read=sign.find(e=>e.ip===0xEE&&e.nextIp===0xA1);
  same([read.slot,read.raw],['P7',a]);
  const copy=sign.find(e=>e.ip===0xE9);repack.exactCopy(r,copy,'X1',a);
  const lateRead=sign.find(e=>e.ip===0xEE&&e.nextIp===0xE3);
  same([lateRead.slot,lateRead.raw],['P7',a]);
  const late=sign.find(e=>e.command>lateRead.command&&e.ip===0xE7);
  same(raw(late.m),'000910000000');repack.exactCopy(r,late,'P7',a);
  same(visible(checks.boundary(r,'after-reserve-1')),[a,p,q,zero,u]);
  const swap=r.traced.events.filter(e=>e.stage==='after-reserve-1');
  const qCopy=swap.find(e=>e.ip===0xE9);same(raw(qCopy.m),p);
  repack.exactCopy(r,qCopy,'Q',p);
  const swapRead=swap.find(e=>e.ip===0xEE&&e.nextIp===0xE3);
  same([swapRead.slot,swapRead.raw],['X',p]);
  const upperCopy=swap.find(e=>e.command>swapRead.command&&e.ip===0xE7);
  same(raw(upperCopy.m),a);repack.exactCopy(r,upperCopy,'P7',p);
  const end=checks.boundary(r,'done');
  same(visible(end),[a,q,p,zero,u]);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),['V','marker']);
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+v,V:r.before.V.slice(0,2)+m,
    W:r.before.W.slice(0,2)+'3F'+a[2]+q.slice(3),Q:r.before.Q.slice(0,2)+p,
    P7:r.before.P7.slice(0,2)+p});
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  return {prefix,boundaries:rows.length,all23HeldAtEveryBoundary:true,
    backup:{read:read.command,copy:copy.command,lateRead:lateRead.command,restore:late.command},
    swap:pair(r,'after-reserve-1','X','Y'),rewriteQ:qCopy.command,writeUpper:upperCopy.command,
    oldUpperOnlyInX1:true,upper3AndOther14OrdinaryAndProgramHeld:true,
    workingExit:false,fullK1:false};
}
function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  const frames=2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  return {keys,frames,publicDisplayOnly:true,assumedSuccessfulAttempts:1,initialPhaseOffsetExcluded:true};
}
if(require.main===module) {
  const o=JSON.parse(process.env.K1_V_Q_OPTIONS||'{}'),negative=!!process.env.K1_V_Q_NEGATIVE;
  const guarding=!!process.env.K1_V_Q_GUARD;assert.ok(!(negative&&guarding));
  if(negative)o.fullUpper=['9011','9022','9033','9044'];
  if(guarding)Object.assign(o,{afterReservePhase:1,afterReserve:[['K','5'],['↔']],afterReserveWaits:[8,8]});
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS Q backup check:',JSON.stringify(guarding?guard(r):check(r,negative)));
  if(process.env.K1_V_Q_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={check,guard,surface};
