#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-y-t-swap-v.cjs');
const entry=require('./k1-y-t-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const m='9990FFFFFFF0';
function prefixView(r,stage,options={}) {
  // Analyze a prefix of an uninterrupted recorded run. No calculator state
  // is imported, restored, or changed by this helper.
  const end=checks.boundary(r,stage),snapshot=snapshotFromRing(end.ring);
  return {...r,options:{...r.options,...options},
    after:Object.fromEntries(Object.keys(r.before).map(n=>[n,raw(end.ring[n],1,14)])),
    afterRegisters:snapshot.words.slice(0,15),afterProgram:snapshot.program,
    traced:{...r.traced,events:r.traced.events.filter(e=>e.command<=end.command)
      .map(e=>e.command===end.command?{...e,stage:'done'}:e),
      writes:r.traced.writes.filter(w=>w.command<end.command)}};
}
function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicDisplayOnly:true,fixturePreparationExcluded:true,assumedSuccessfulAttempts:1};
}
function check(r,endStage='done') {
  if(endStage!=='done')r=prefixView(r,endStage);
  same(r.options.afterClone,[['↔']]);assert.ok(!r.options.afterClonePhase);
  const prefix=entry.check(prefixView(r,'after-clone-0',{afterClone:[]}));
  checks.protectedFields(r,[0],['U','V','W','Q']);
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const at=checks.boundary(r,'after-clone-0'),end=checks.boundary(r,'done');
  const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
  same(visible(at),[q,v,m,q,m]);
  same(['U','V','W','Q'].map(n=>raw(at.ring[n])),[v,u,q,p]);
  same(visible(end),[q,u,v,'14'+q[2]+q.slice(3),m]);
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+v,V:r.before.V.slice(0,2)+u,
    W:r.before.W.slice(0,2)+u,Q:r.before.Q.slice(0,2)+p});
  same(raw(end.ring.marker),raw(at.ring.marker));
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),['T','marker']);
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  const stored=snapshotFromRing(end.ring).words;
  same(snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words.filter(x=>!stored.includes(x)),[q]);
  same(['X1','X','Y','Z','T'].filter(n=>raw(end.ring[n])===q),['X1']);
  const es=r.traced.events.filter(e=>e.stage==='after-clone-0');
  assert.ok(es.every(e=>e.otherChips?.[4]),'complete secondary trace');
  const gates=es.filter(e=>e.ip===0x9C);
  same(gates.map(e=>[e.slot,e.nextIp]),[['control',0x9E],['control',0x9E]]);
  const reads=es.filter(e=>e.ip===0xEE);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['W',q,0xA1],['X',u,0xE3]]);
  const saves=es.filter(e=>e.ip===0xE9);same(saves.length,1);repack.exactCopy(r,saves[0],'X1',q);
  const requests=es.filter(e=>e.ip===0xA3);same(requests.length,1);const request=requests[0];
  same(request.slot,'Z');const header=ringAt(r,request.command);
  const headerValues=[parseInt(q[2],16),4,1];
  [28,31,34].forEach((n,i)=>{header.Z[n]=headerValues[i];});
  same(ringAt(r,request.command+1),header,'only Z request header changes');
  same(r.traced.writes.filter(x=>x.command===request.command).map(x=>[x.chip,x.slot,x.nibble,x.value]),
    [28,31,34].map((n,i)=>[3,'Z',n,headerValues[i]]));
  const all=r.traced.writes.filter(x=>x.command>=at.command&&x.command<end.command&&x.chip===4);
  const housekeeping=all.filter(x=>x.ip===0x27);
  same(housekeeping.map(x=>[x.slot,x.nibble]),[['control',31]]);
  assert.ok(housekeeping.every(x=>x.before===x.value));
  const secondary=all.filter(x=>x.ip!==0x27),first=secondary[0].command;
  same(secondary.map(x=>[x.command-first,x.ip,x.slot,x.nibble]),['X','Y'].flatMap((n,i)=>
    Array.from({length:12},(_,j)=>[i,i?0x2A:0x4E,n,1+3*j])));
  same(r.traced.writes.filter(x=>x.command>=first&&x.command<first+2),secondary,
    'all-chip output journal contains only the 24 secondary writes');
  const beforePair=ringAt(r,first),expected=structuredClone(beforePair);
  same(raw(beforePair.V),u);same(raw(beforePair.X),v);
  for(let j=0;j<12;j++) {
    expected.X[1+3*j]=beforePair.V[1+3*j];expected.Y[1+3*j]=beforePair.X[1+3*j];
  }
  same(ringAt(r,first+2),expected,'V -> X, old X -> Y among all 630 tetras');
  const source=es.find(e=>e.command>request.command&&e.command<first&&
    e.otherChips[4].ip===0x53&&e.otherChips[4].slot==='V');
  assert.ok(source);same(raw(source.otherChips[4].m),u);
  const secondaryPath=[0x6E,0x5E,0x50,0x52,0x53,0x4F,0x41,0x43,0x4D,0x60,
    0x37,0x37,0x27,0x61,0x4E,0x2A,0x39];
  const names=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
  same(es.filter(e=>e.command>=first-14&&e.command<=first+2)
    .map(e=>[e.command-first,e.otherChips[4].ip,e.otherChips[4].slot]),
    secondaryPath.map((ip,i)=>[i-14,ip,names[(4+i)%15]]),'connected secondary source-to-output path');
  const late=es.filter(e=>e.ip===0xE7);same(late.length,1);repack.exactCopy(r,late[0],'W',u);
  const expectedEnd=structuredClone(at.ring);
  for(const [n,value] of Object.entries({X1:q,X:u,Y:v,Z:'14'+q.slice(2),W:u}))
    [...value].reverse().forEach((x,j)=>{expectedEnd[n][1+3*j]=parseInt(x,16);});
  same(end.ring,expectedEnd,'exact complete-operation endpoint, all 630 tetras');
  const allowed=new Set([saves[0].command,request.command,first,first+1,late[0].command]);
  same(r.traced.writes.filter(x=>x.command>=at.command&&x.command<end.command&&x.before!==x.value)
    .filter(x=>!allowed.has(x.command)),[],'no undeclared changed tetra');
  return {prefix,boundaries:rows.length,all23LiveAtEveryActionBoundary:true,
    oldUReservedInXAndW:true,oldQOnlyInX1:true,remainingMarker:'T',
    primaryReadW:reads[0].command,saveX1:saves[0].command,requestZ:request.command,
    secondaryReadV:source.command,secondaryPair:first,lateReadX:reads[1].command,lateWriteW:late[0].command,
    other14OrdinaryUpper4ProgramAndServicesHeld:true,all23StoredAtEnd:false,
    workingExit:false,numericDomainProved:false,fullK1:false};
}
if(require.main===module) {
  const o={...probe.defaults,...JSON.parse(process.env.K1_SWAP_V_OPTIONS||'{}')};
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS preserving V reserve:',JSON.stringify(check(r)));
  if(process.env.K1_SWAP_V_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={prefixView,surface,check};
