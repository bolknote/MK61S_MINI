#!/usr/bin/env node
'use strict';
// The F-comma alternative leaves only V marked in hidden memory.
// It is a conditional entry, not a completed upper-bank operation.
const assert=require('node:assert/strict');
const probe=require('./k1-repack-deep-clone-probe.cjs');
const deep=require('./k1-repack-deep-clone-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const defaults={clonePhase:0,clonePrefix:['F'],cloneKeys:[',']};
const m='9990FFFFFFF0';
const names=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const values=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
function entry(r,endStage='done') {
  same(r.options.clonePhase,0);same(r.options.clonePrefix,['F']);same(r.options.cloneKeys,[',']);
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const at=checks.boundary(r,'clone-sign'),end=checks.boundary(r,endStage);
  same(values(at),['00008FFFFFFF',m,u,q,m]);
  same(['U','V','W','Q'].map(n=>raw(at.ring[n])),[v,u,q,p]);
  same(values(end),['00008FFFFFFF',u,q,m,m]);
  same(['U','V','W','Q'].map(n=>raw(end.ring[n])),[v,m,q,p]);
  same(raw(end.ring.U,0),w);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),['T','V','Z','marker']);
  const es=r.traced.events.filter(e=>e.stage==='clone-sign');
  const start=es.findIndex(e=>e.ip===0x9C),route=es.slice(start,start+25);
  const ips=[0x9C,0x9E,0x9F,0xA0,...Array(5).fill(0xE5),0xE6,0xED,0xEE,0xA1,
    0xE5,0xE5,0xE6,0xE9,...Array(7).fill(0xA2),0xA3];
  same(route.map(e=>[e.ip,e.slot]),ips.map((ip,i)=>[ip,names[(7+i)%15]]));
  same(route[0].nextIp,0x9E);same(raw(route[0].m),v);
  same([route[0].r[30],route[0].r[33]],[5,2]);same(route[11].raw,m);
  repack.exactCopy(r,route[16],'V',m);
  const read=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);assert.ok(read);
  same([read.slot,read.raw],['X',m]);
  const late=es.find(e=>e.command>read.command&&e.ip===0xE7);
  same(raw(late.m),m);repack.exactCopy(r,late,'V',m);
  return {control:route[0].command,read:route[11].command,cloneV:route[16].command,
    request:route[24].command,visibleRotation:repack.visibleRotation(r,'clone-sign'),
    lateRead:read.command,lateWrite:late.command};
}
function check(r) {
  same(r.options.afterClone??[],[]);
  checks.protectedFields(r,[0],['U','V','W','Q']);
  const rows=repack.boundaryLosses(r);
  assert.ok(rows.every(x=>!x.missing.length),JSON.stringify(rows.filter(x=>x.missing.length)));
  same(r.afterRegisters,r.beforeRegisters.map((v,i)=>i?v:r.before.W.slice(2)));
  return {boundaries:rows.length,all23HeldAtEveryBoundary:true,
    upper4AndOther14OrdinaryAndProgramHeld:true,paths:entry(r),
    onlyHiddenMarker:'V',visibleMarkers:['Z','T'],
    workingExit:false,upperExchange:false,fullK1:false};
}
if(require.main===module) {
  const o={...defaults,...JSON.parse(process.env.K1_SINGLE_V_OPTIONS||'{}')};
  console.log('PASS keyboard surface:',JSON.stringify(deep.surface(o)));
  const r=probe.run(o);console.log('PASS single V entry:',JSON.stringify(check(r)));
  if(process.env.K1_SINGLE_V_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={defaults,entry,check};
