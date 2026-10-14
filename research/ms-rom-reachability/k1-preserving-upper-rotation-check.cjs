#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-preserving-upper-rotation.cjs');
const single=require('./k1-single-v-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const cycles=require('./k1-six-word-cycle-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const upper=['P7','P8','P9','P10'],zero='000000000000',m='9990FFFFFFF0';
const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
function cleanup(r,readbackTarget='X') {
  const [u,q,a]=['U','Q','P7'].map(n=>r.before[n].slice(2));
  const before=checks.boundary(r,'after-clone-0');
  same(visible(before),['00008FFFFFFF',u,q,m,m]);
  same(visible(checks.boundary(r,'after-clone-1')),['00008FFFFFFF',zero,u,q,m]);
  const copied=readbackTarget==='X'?a:zero;
  same(visible(checks.boundary(r,'after-clone-2')),['00008FFFFFFF',copied,u,q,m]);
  const clean=checks.boundary(r,'after-clone-3');
  same(visible(clean),['00008FFFFFFF',zero,copied,u,q]);
  same(Object.keys(clean.ring).filter(n=>clean.ring[n][22]===15).sort(),['V','marker']);
  const pushes=[0,2].map(i=>checks.exactPush(r,'after-clone-'+i,['X','Y','Z','T']));
  same(pushes.map(p=>p.displaced),[m,m]);
  const zeros=[0,2].map(i=>{
    const e=r.traced.events.find(e=>e.stage==='after-clone-'+i&&e.ip===0xE7&&e.nextIp===0x47);
    repack.exactCopy(r,e,'X',zero);return e.command;
  });
  const es=r.traced.events.filter(e=>e.stage==='after-clone-1');
  const read=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);
  same([read.slot,read.raw],['P7',a]);
  const late=es.find(e=>e.command>read.command&&e.ip===0xE7);
  repack.exactCopy(r,late,readbackTarget,a);
  const lo=before.command,hi=clean.command;
  assert.ok(r.traced.writes.filter(w=>w.command>=lo&&w.command<hi&&
    Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&
    !(readbackTarget==='W'&&w.slot==='W')).every(w=>w.before===w.value),
    'hidden words held except the explicitly checked readback destination');
  if(readbackTarget==='W')same(raw(clean.ring.W),a);
  return {pushes,zeros,read:read.command,readback:late.command,readbackTarget,onlyHiddenMarker:'V'};
}
function rotation(r,stage='after-clone-3',lateTarget='X') {
  const out=cycles.rotation(r,stage,upper),first=out.command;
  const es=r.traced.events.filter(e=>e.stage===stage);
  const buffer=es.filter(e=>e.command>=first-16&&e.command<first).map(e=>e.otherChips[4]);
  same(buffer.map(e=>[e.ip,e.slot]),[
    ...['Q',...upper].map(n=>[0xD4,n]),[0xC4,'marker'],[0x2C,'control'],[0x3B,'X1'],
    [0x2B,'X'],[0x60,'Y'],...['Z','T','U','V'].map(n=>[0x37,n]),[0x27,'W'],[0x61,'Q']]);
  same([buffer[0].l,buffer[0].s1,...[37,38,40,41].map(i=>buffer[0].r[i])],[1,9,4,0,13,6]);
  same([0,1,2].map(i=>buffer[0].st[36+i]+16*buffer[0].st[39+i]),[0x29,0x3A,0x3A]);
  const before=ringAt(r,first-16),a=raw(before.P7);
  same(raw(buffer[0].r,2),a);same(raw(buffer[0].r,1),raw(before.P8));
  same(before.V[22],15);same(before.W[31],15);
  assert.ok(['Z','T','U'].every(n=>before[n][22]!==15));
  const request=es.find(e=>e.ip===0xA3);
  same([request.slot,request.r[32],request.r[35]],['W',5,2]);
  const source=es.find(e=>e.ip===0xEE&&e.nextIp===0xA1);
  same([source.slot,source.raw],['P7',a]);
  repack.exactCopy(r,es.find(e=>e.ip===0xE9),'X1',a);
  const lateRead=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);
  same([lateRead.slot,lateRead.raw],['P7',a]);
  const late=es.find(e=>e.command>lateRead.command&&e.ip===0xE7);
  repack.exactCopy(r,late,lateTarget,a);
  return {...out,buffer:first-16,source:source.command,request:request.command,
    lateRead:lateRead.command,lateWrite:late.command,lateTarget};
}
function check(r) {
  same(r.options.upperLeadPhase,1);
  checks.protectedFields(r,[0],Object.keys(r.before));
  const rows=repack.boundaryLosses(r);
  assert.ok(rows.every(x=>!x.missing.length),JSON.stringify(rows.filter(x=>x.missing.length)));
  const entry=single.entry(r,'after-clone-phase'),removed=cleanup(r);
  const rotations=[rotation(r)];
  for(const [i,k] of (r.options.afterUpper??[]).entries()) {
    same(k,['F',',']);rotations.push(rotation(r,'after-upper-'+i));
  }
  const count=rotations.length,[u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2));
  const p=r.beforeRegisters[0],a=r.before.P7.slice(2),last=r.before[upper[(count-1)%4]].slice(2);
  const end=checks.boundary(r,'done');
  same(visible(end),[last,last,a,u,q]);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),['V','marker']);
  const want={...r.before,U:r.before.U.slice(0,2)+v,V:r.before.V.slice(0,2)+m,
    W:r.before.W.slice(0,2)+'2F'+last[2]+q.slice(3),Q:r.before.Q.slice(0,2)+p};
  upper.forEach((n,i)=>{want[n]=r.before[n].slice(0,2)+r.before[upper[(i+count)%4]].slice(2);});
  same(r.after,want);same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  return {boundaries:rows.length,all23HeldAtEveryBoundary:true,
    other14OrdinaryAndProgramAndServiceHeld:true,entry,cleanup:removed,rotations,
    lowerLive:{ordinaryP0:'w',msU:'v',msQ:'p',visibleZ:'u',visibleT:'q'},
    workingExit:false,fullK1:false};
}
function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  const frames=2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  return {keys,frames,publicDisplayOnly:true,assumedSuccessfulAttempts:1,initialPhaseOffsetExcluded:true};
}
function negative(r,which) {
  checks.protectedFields(r,[0],Object.keys(r.before));
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:r.before.W.slice(2)));
  single.entry(r,'after-clone-phase');
  const rows=repack.boundaryLosses(r),bad=rows.filter(x=>x.missing.length);
  const es=r.traced.events;
  if(which==='unshifted') {
    same(r.options.upperLeadPhase,0);cleanup(r);
    const copy=es.find(e=>e.stage==='after-clone-3'&&e.ip===0xE9);
    same(raw(copy.m),r.beforeRegisters[0]);repack.exactCopy(r,copy,'Q',zero);
    same(bad.map(x=>[x.stage,x.missing]),[['done',[r.beforeRegisters[0]]]]);
    upper.forEach(n=>same(r.after[n],r.before[n]));
    return {rejected:'no extra frame before upper request',firstDestructiveCopy:copy.command,
      target:'Q',lost:'original ordinary P0',notGeneralImpossibility:true};
  }
  if(which==='short-upper') {
    same(r.options.fullUpper,['-1E-99','9022','9033','9044']);cleanup(r,'W');
    const path=rotation(r,'after-clone-3','P7');
    const late=es.find(e=>e.command===path.lateWrite);
    same(raw(late.m),r.before.P8.slice(2));
    same(bad.map(x=>[x.stage,x.missing]),[['done',[r.before.P8.slice(2)]]]);
    return {rejected:'canonical formatter class 7',rotation:path,
      lost:'original upper P8',notGeneralImpossibility:true};
  }
  same(which,'recall');same(r.options.afterUpper,[['П→X','0']]);cleanup(r);rotation(r);
  const q=r.before.Q.slice(2),b=r.before.P8.slice(2),w=r.before.W.slice(2);
  const push=checks.exactPush(r,'after-upper-0',['X','Y','Z','T']);same(push.displaced,q);
  const late=es.find(e=>e.stage==='after-upper-0'&&e.ip===0xE7&&e.nextIp===0x47);
  same(raw(late.m),b);repack.exactCopy(r,late,'P7',w);
  same(bad.map(x=>[x.stage,x.missing]),[['done',[q,b]]]);
  return {rejected:'ordinary recall is not a cleanup',push,lateWrite:late.command,
    lost:['original lower Q','original upper P8'],notGeneralImpossibility:true};
}
if(require.main===module) {
  const o=JSON.parse(process.env.K1_PRESERVING_UPPER_OPTIONS||'{}');
  const which=process.env.K1_PRESERVING_UPPER_CASE??'entry';
  assert.ok(['entry','unshifted','short-upper','recall'].includes(which));
  if(which==='unshifted')o.upperLeadPhase=0;
  if(which==='short-upper')o.fullUpper=['-1E-99','9022','9033','9044'];
  if(which==='recall')o.afterUpper=[['П→X','0']];
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS '+which+':',JSON.stringify(which==='entry'?check(r):negative(r,which)));
  if(process.env.K1_PRESERVING_UPPER_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={cleanup,rotation,check,surface,negative};
