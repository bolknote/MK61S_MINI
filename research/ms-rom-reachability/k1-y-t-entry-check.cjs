#!/usr/bin/env node
'use strict';
// A native preparatory operation, NOT a completed K1 or a clean exit.
const assert=require('node:assert/strict');
const probe=require('./k1-y-t-entry.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing,analyzeTrace}=require('./k1-permutation-oracle.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const m='9990FFFFFFF0',zero='000000000000';
const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
const markers=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicDisplayOnly:true,initialPhaseOffsetExcluded:true,assumedSuccessfulAttempts:1};
}
function check(r) {
  same(r.options.afterClone??[],[]);same(r.options.clonePrefix,[]);
  same(r.options.cloneKeys,['↔']);same(r.options.clonePhase,0);
  checks.protectedFields(r,[0],['U','V','W','Q']);
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const start=r.traced.events.find(e=>e.ring),at=checks.boundary(r,'clone-sign'),end=checks.boundary(r,'done');
  same(raw(end.ring.marker),raw(start.ring.marker),'the full true-marker numeric word is preserved');
  assert.ok(r.traced.writes.filter(x=>x.slot==='marker'&&x.nibble%3===1&&x.nibble<37)
    .every(x=>x.before===x.value),'true-marker numeric tetras held even transiently');
  const free=checks.boundary(r,'w-to-x-0');
  same(raw(free.ring.U,0),zero);same(visible(free),[p,zero,zero,u,w]);same(markers(free),['marker']);
  const readInput=checks.boundary(r,'read-q/attempt-0/read-prep-0');
  same(raw(readInput.ring.U,0),w);same(raw(readInput.ring.X),u);
  const readEnd=checks.boundary(r,'payload-rotate-0');
  same(raw(readEnd.ring.U,0),w);same(visible(readEnd).slice(1),[q,zero,u,w]);
  same(visible(at),['00008FFFFFFF',m,u,q,m]);same(markers(at),['T','X','marker']);
  same(['U','V','W','Q'].map(n=>raw(at.ring[n])),[v,u,q,p]);
  same(visible(end),[q,v,m,q,m]);same(markers(end),['T','Y','marker']);
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+v,V:r.before.V.slice(0,2)+u,
    W:r.before.W.slice(0,2)+q,Q:r.before.Q.slice(0,2)+p});
  const mapping=Array.from({length:23},(_,i)=>i);
  for(const [dst,src] of [[0,17],[15,16],[16,15],[17,18],[18,0]])mapping[dst]=src;
  const oracle=analyzeTrace({beforeEvent:start,afterEvent:end,writes:r.traced.writes,expectedMapping:mapping});
  same(oracle.status,'PERMUTATION_INSTANCE_ONLY');same(oracle.fixedMapping.status,'matches_this_fixture');
  same(snapshotFromRing(at.ring).words,snapshotFromRing(end.ring).words,
    'the final key changes no stored numeric word');
  const rows=repack.boundaryLosses(r);
  same(rows.filter(e=>e.missing.length),[],'all 23 originals live at every native action boundary');
  const es=r.traced.events.filter(e=>e.stage==='clone-sign');
  assert.ok(es.every(e=>e.otherChips?.[4]),'complete secondary trace');
  const gates=es.filter(e=>e.ip===0x9C);
  same(gates.map(e=>[e.slot,e.nextIp]),[['control',0x9E],['control',0x9E]]);
  const reads=es.filter(e=>e.ip===0xEE);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['W',q,0xA1],['X',v,0xE3]]);
  const copies=es.filter(e=>e.ip===0xE9);same(copies.length,1);
  repack.exactCopy(r,copies[0],'X1',q);
  const requests=es.filter(e=>e.ip===0xA3);same(requests.length,1);const request=requests[0];
  same(request.slot,'Y');same(raw(request.m),u);
  const header=ringAt(r,request.command);
  for(const [n,value] of [[28,8],[31,4],[34,1]])header.Y[n]=value;
  same(ringAt(r,request.command+1),header,'only the three Y request-header tetras change');
  same(r.traced.writes.filter(x=>x.command===request.command).map(x=>[x.chip,x.slot,x.nibble,x.value]),
    [[3,'Y',28,8],[3,'Y',31,4],[3,'Y',34,1]]);
  // This is NOT an X/Y swap: a displaced request makes the secondary
  // reader carry U, while the old X marker is the second output word.
  const secondaryAll=r.traced.writes.filter(x=>x.command>=at.command&&x.command<end.command&&x.chip===4);
  const housekeeping=secondaryAll.filter(x=>x.ip===0x27);
  same(housekeeping.map(x=>[x.slot,x.nibble]),[['control',31]]);
  assert.ok(housekeeping.every(x=>x.before===x.value),'secondary request housekeeping is idempotent');
  const secondary=secondaryAll.filter(x=>x.ip!==0x27);
  same(secondary.map(x=>[x.ip,x.slot,x.nibble]),['X','Y'].flatMap((n,i)=>
    Array.from({length:12},(_,j)=>[i?0x2A:0x4E,n,1+3*j])));
  const first=secondary[0].command;
  same(secondary.map(x=>x.command),[...Array(12).fill(first),...Array(12).fill(first+1)]);
  same(r.traced.writes.filter(x=>x.command>=first&&x.command<first+2),secondary,
    'no concurrent primary or tertiary write during the secondary pair');
  const beforeSecondary=ringAt(r,first),expected=structuredClone(beforeSecondary);
  same(raw(beforeSecondary.U),v);same(raw(beforeSecondary.X),m);
  for(let j=0;j<12;j++) {
    expected.X[1+3*j]=beforeSecondary.U[1+3*j];
    expected.Y[1+3*j]=beforeSecondary.X[1+3*j];
  }
  same(ringAt(r,first+2),expected,'exact U-to-X, old-X-to-Y among all 630 tetras');
  const late=es.filter(e=>e.ip===0xE7);same(late.length,1);
  same(late[0].nextIp,0x47);repack.exactCopy(r,late[0],'U',v);
  const allowed=new Set([copies[0].command,request.command,first,first+1]);
  same(r.traced.writes.filter(x=>x.command>=at.command&&x.command<end.command&&x.before!==x.value)
    .filter(x=>!allowed.has(x.command)),[],'no undeclared changed tetra in the final operation');
  return {boundaries:rows.length,all23LiveAtEveryActionBoundary:true,
    all23InStoredWordsAtEnd:true,finalOperationLeavesAll23StoredWordsUnchanged:true,
    other14OrdinaryUpper4ProgramAndServicesHeld:true,control:gates.map(e=>e.command),
    read:reads.map(e=>e.command),copyX1:copies[0].command,requestY:request.command,
    secondaryCopies:{command:first,sources:['U','X'],destinations:['X','Y']},lateIdempotentU:late[0].command,
    storedCycles:oracle.data.cycles,remainingMarkers:['Y','T'],hiddenMsMarkers:false,
    workingExit:false,numericDomainProved:false,fullK1:false};
}
if(require.main===module) {
  const o={...probe.defaults,...JSON.parse(process.env.K1_Y_T_OPTIONS||'{}')};
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS preserving Y/T entry:',JSON.stringify(check(r)));
  if(process.env.K1_Y_T_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,check};
