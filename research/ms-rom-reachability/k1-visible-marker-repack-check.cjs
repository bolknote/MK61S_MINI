#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-visible-marker-repack.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {pair}=require('./k1-first-upper-bridge-check.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const m='0000FFFFFFF0';
function boundaryLosses(r) {
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  same(new Set(original).size,23);const seen=new Set();
  return r.traced.events.filter(e=>e.ring&&!seen.has(e.stage)&&(seen.add(e.stage),true)).map(e=>{
    const live=[...snapshotFromRing(e.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]))];
    return {stage:e.stage,command:e.command,missing:original.filter(n=>!live.includes(n))};
  });
}
function exactCopy(r,e,target,value) {
  assert.ok(e);same(e.slot,target);same(raw(e.r,0),value);
  const expected=ringAt(r,e.command);
  for(let j=0;j<12;j++)expected[target][1+3*j]=parseInt(value[11-j],16);
  same(ringAt(r,e.command+1),expected,'only one exact 12-tetra copy among all 630 tetras');
  same(r.traced.writes.filter(w=>w.command===e.command).map(w=>[w.chip,w.slot,w.nibble]),
    Array.from({length:12},(_,j)=>[3,target,1+3*j]));
}
function visibleRotation(r,stage) {
  const es=r.traced.events.filter(e=>e.stage===stage);
  assert.ok(es.every(e=>e.otherChips?.[4]),'complete secondary trace');
  const targets=['X','Y','Z','T'];
  const writes=r.traced.writes.filter(w=>w.command>=es[0].command&&w.command<=es.at(-1).command&&
    w.chip===4&&((w.ip===0x3A&&targets.slice(0,3).includes(w.slot))||(w.ip===0x2A&&w.slot==='T')));
  same(writes.map(w=>[w.ip,w.slot,w.nibble]),targets.flatMap((n,i)=>
    Array.from({length:12},(_,j)=>[i===3?0x2A:0x3A,n,1+3*j])));
  const first=writes[0].command,expected=ringAt(r,first),old=structuredClone(expected);
  for(const [i,n] of targets.entries())for(let j=0;j<12;j++)expected[n][1+3*j]=old[targets[(i+1)%4]][1+3*j];
  same(ringAt(r,first+4),expected,'exact visible rotation among all 630 tetras');
  return first;
}
function prefixPaths(r,lateTarget='U') {
  const es=r.traced.events.filter(e=>e.stage==='tail-1'),v=r.before.V.slice(2);
  const start=es.findIndex(e=>e.ip===0x9C&&e.slot==='T');assert.ok(start>=0);
  const route=es.slice(start,start+26);
  const ips=[0x9C,0x9E,0x9F,0xA0,...Array(6).fill(0xE5),0xE6,0xED,0xEE,0xA1,
    0xE5,0xE6,0xE9,...Array(8).fill(0xA2),0xA3];
  const names=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
  same(route.map(e=>[e.ip,e.slot]),ips.map((ip,i)=>[ip,names[(6+i)%15]]));
  same([route[0].r[30],route[0].r[33]],[5,2]);same(route[12].raw,v);
  same(ringAt(r,route[16].command).U[22],15);exactCopy(r,route[16],'U',v);
  const read=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);assert.ok(read);
  same([read.slot,read.raw],['X',v]);
  const late=es.find(e=>e.command>read.command&&e.ip===0xE7);exactCopy(r,late,lateTarget,v);
  return {swap:pair(r,'clone-swap-0','W','Q'),rotations:['tail-0','tail-1'].map(s=>visibleRotation(r,s)),
    removeU:route[16].command,formatterRead:read.command,formatterWrite:late.command,formatterTarget:lateTarget};
}
function check(r) {
  assert.ok(!(r.options.after??[]).length);
  checks.protectedFields(r,[0],['U','V','W','Q']);
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:u));
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+v,V:r.before.V.slice(0,2)+q,
    W:r.before.W.slice(0,2)+q,Q:r.before.Q.slice(0,2)+p});
  const end=checks.boundary(r,'done');
  same(['X1','X','Y','Z','T'].map(n=>raw(end.ring[n])),[p,w,m,q,v]);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15),['marker','Y']);
  const rows=boundaryLosses(r);assert.ok(rows.every(x=>!x.missing.length),JSON.stringify(rows.filter(x=>x.missing.length)));
  return {boundaries:rows.length,all23HeldAtEveryBoundary:true,upper4AndOther14OrdinaryAndProgramHeld:true,
    paths:prefixPaths(r),remainingMarker:'Y',workingExit:false,fullK1:false};
}
function shortVFailure(r) {
  same(r.options.values,['-1.2345678E-42','-7.654321E-23','833','-12345678']);
  checks.protectedFields(r,[0],['U','V','W','Q']);
  const w=r.before.W.slice(2),rows=boundaryLosses(r);
  same(rows.filter(x=>x.missing.length).map(x=>[x.stage,x.missing]),[['done',[w]]]);
  const paths=prefixPaths(r,'X');same(raw(ringAt(r,paths.formatterWrite).X),w);
  return {rejected:'short v=833',lost:w,paths,notAGeneralImpossibilityProof:true};
}
function recallFailure(r) {
  same(r.options.after,[['П→X','0'],['П→X','0']]);
  checks.protectedFields(r,[0],['U','V','W','Q']);
  const q=r.before.Q.slice(2),u=r.before.U.slice(2),rows=boundaryLosses(r);
  same(rows.filter(x=>x.missing.length).map(x=>[x.stage,x.missing]),[['done',[q]]]);
  const pushes=['after-0','after-1'].map(s=>checks.exactPush(r,s,['X','Y','Z','T']));
  same(pushes.map(p=>p.displaced),[r.before.V.slice(2),q]);
  const copies=['V','W'].map((n,i)=>{
    const e=r.traced.events.find(e=>e.stage==='after-'+i&&e.ip===0xE7&&e.nextIp===0x47);
    same(raw(e.m),q);exactCopy(r,e,n,u);return {command:e.command,target:n};
  });
  return {rejected:'two recalls of long u',lost:q,pushes,copies,paths:prefixPaths(r),notAGeneralImpossibilityProof:true};
}
function surface() {
  const ds=['1,','2,','3,'],a=control.record(ds,{},probe.finish);
  same(a,control.record(ds,{incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  const frames=2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  return {keys,frames,publicDisplayOnly:true,assumedSuccessfulAttempts:1,phaseOffsetExcluded:true};
}
if(require.main===module) {
  console.log('PASS keyboard surface:',JSON.stringify(surface()));
  const which=process.env.K1_REPACK_CASE??'entry';
  const o=JSON.parse(process.env.K1_REPACK_OPTIONS||'{}');
  if(which==='short-v')o.values=['-1.2345678E-42','-7.654321E-23','833','-12345678'];
  if(which==='recalls')o.after=[['П→X','0'],['П→X','0']];
  assert.ok(['entry','short-v','recalls'].includes(which));const r=probe.run(o);
  console.log('PASS '+which+':',JSON.stringify(({entry:check,'short-v':shortVFailure,recalls:recallFailure})[which](r)));
  if(process.env.K1_REPACK_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={boundaryLosses,exactCopy,visibleRotation,prefixPaths,check,shortVFailure,recallFailure,surface};
