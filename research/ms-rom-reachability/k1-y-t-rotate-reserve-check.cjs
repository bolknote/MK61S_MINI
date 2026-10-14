#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-y-t-rotate-reserve.cjs');
const entry=require('./k1-y-t-entry-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const m='9990FFFFFFF0';
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const visible=ring=>['X1','X','Y','Z','T'].map(n=>raw(ring[n]));
function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicDisplayOnly:true,fixturePreparationExcluded:true,assumedSuccessfulAttempts:1};
}
function setWord(ring,slot,value) {
  [...value].reverse().forEach((x,j)=>{ring[slot][1+3*j]=parseInt(x,16);});
}
function check(r,endStage='done') {
  if(endStage!=='done')r=prefixView(r,endStage);
  assert.ok(!r.options.stopAfterRotate);assert.ok(!r.options.afterClonePhase);
  same(r.options.afterClone,[['F',',']]);
  const prefix=entry.check(prefixView(r,'after-clone-0',{afterClone:[]}));
  checks.protectedFields(r,[0],['U','V','W','Q']);
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const at=checks.boundary(r,'after-clone-0'),middle=checks.boundary(r,'rotate/reserve'),end=checks.boundary(r,'done');
  same(visible(at.ring),[q,v,m,q,m]);
  same(visible(middle.ring),[q,u,'25'+q.slice(2),m,v]);
  same(visible(end.ring),visible(middle.ring));
  same(['U','V','W','Q'].map(n=>raw(middle.ring[n])),[v,v,q,p]);
  same(['U','V','W','Q'].map(n=>raw(end.ring[n])),[v,u,q,p]);
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+v,V:r.before.V.slice(0,2)+u,
    W:r.before.W.slice(0,2)+q,Q:r.before.Q.slice(0,2)+p});
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),['Z','marker']);
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  const missingStored=ring=>original.filter(x=>!snapshotFromRing(ring).words.includes(x));
  same(missingStored(middle.ring),[u]);same(missingStored(end.ring),[]);
  same(['X1','X','Y','Z','T'].filter(n=>raw(middle.ring[n])===u),['X']);
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);

  const es=r.traced.events.filter(e=>e.stage==='after-clone-0');
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]),'complete other-chip trace');
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['control',0x9E],['control',0x9E]]);
  const reads=es.filter(e=>e.ip===0xEE);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['W',q,0xA1],['X',v,0xE3]]);
  const saves=es.filter(e=>e.ip===0xE9);same(saves.length,1);repack.exactCopy(r,saves[0],'X1',q);
  const requests=es.filter(e=>e.ip===0xA3);same(requests.length,1);const request=requests[0];
  same(request.slot,'Z');const header=ringAt(r,request.command),headerValues=[parseInt(q[2],16),5,2];
  [28,31,34].forEach((n,i)=>{header.Z[n]=headerValues[i];});
  same(ringAt(r,request.command+1),header,'exact Z request, all 630 tetras');
  same(r.traced.writes.filter(x=>x.command===request.command).map(x=>[x.chip,x.slot,x.nibble,x.value]),
    [28,31,34].map((n,i)=>[3,'Z',n,headerValues[i]]));

  const all=r.traced.writes.filter(x=>x.command>=at.command&&x.command<middle.command&&x.chip===4);
  const acknowledgements=all.filter(x=>x.ip===0x27);
  same(acknowledgements.map(x=>[x.slot,x.nibble]),[['control',31],['control',31]]);
  assert.ok(acknowledgements.every(x=>x.before===x.value));
  const secondary=all.filter(x=>x.ip!==0x27),first=secondary[0].command;
  same(secondary.map(x=>[x.command-first,x.ip,x.slot,x.nibble]),['X','Y','Z','T'].flatMap((n,i)=>
    Array.from({length:12},(_,j)=>[i,i===3?0x2A:0x3A,n,1+3*j])));
  same(r.traced.writes.filter(x=>x.command>=first&&x.command<first+4),secondary,
    'no concurrent writer during the four secondary output words');
  const beforeOutput=ringAt(r,first),expected=structuredClone(beforeOutput);
  for(const [target,source] of [['X','V'],['Y','Z'],['Z','T'],['T','U']])
    for(let j=0;j<12;j++)expected[target][1+3*j]=beforeOutput[source][1+3*j];
  same(ringAt(r,first+4),expected,'exact V/Z/T/U -> X/Y/Z/T output, all 630 tetras');
  const path=[0x6E,0x5E,0x50,0x52,0x53,0x4F,0x24,0x26,0x28,0xD3,0x37,0x37,
    0x27,0xD4,0xD4,0xD4,0xD4,0xD4,0xC4,0x2C,0x3B,0x2B,0x60,
    0x37,0x37,0x37,0x37,0x27,0x61,0x3A,0x3A,0x3A,0x2A,0x39];
  const start=first-29,consumer=es.filter(e=>e.command>=start&&e.command<start+path.length);
  same(consumer.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),path.map((ip,i)=>[ip,slots[(4+i)%15]]));
  const s0=consumer[0].otherChips[4];same(s0.r[29],0);
  same([s0.st[36],s0.st[39],s0.st[37],s0.st[40]],[10,3,10,3]);
  same(raw(consumer[4].otherChips[4].m),u);
  same(reads[1].command,first-1,'primary reads old X before secondary overwrites it');
  const late=es.filter(e=>e.ip===0xE7);same(late.length,1);repack.exactCopy(r,late[0],'V',v);
  assert.ok(first+4<late[0].command,'secondary creates Z marker before late formatter output');
  const expectedMiddle=structuredClone(at.ring);
  for(const [n,value] of Object.entries({X:u,Y:'25'+q.slice(2),Z:m,T:v,V:v}))setWord(expectedMiddle,n,value);
  same(middle.ring,expectedMiddle,'complete rotate endpoint, all 630 tetras');
  const allowed=new Set([saves[0].command,request.command,first,first+1,first+2,first+3,late[0].command]);
  same(r.traced.writes.filter(x=>x.command>=at.command&&x.command<middle.command&&x.before!==x.value)
    .filter(x=>!allowed.has(x.command)),[],'no undeclared changed tetra in F-comma');

  const ns=r.traced.events.filter(e=>e.stage==='rotate/reserve');
  same(ns.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['control',0x9E],['T',0x9E]]);
  const firstGate=ns.find(e=>e.ip===0x9C);same([firstGate.r[23],firstGate.r[26],firstGate.r[29]],[0,0,4]);
  const nr=ns.filter(e=>e.ip===0xEE);
  same(nr.map(e=>[e.slot,e.raw,e.nextIp]),[['V',v,0xAB],['X',u,0xE3]]);
  same(ns.filter(e=>[0xE9,0xA3,0xA8].includes(e.ip)),[],'NOP has no request, X1 overwrite or push');
  const nw=ns.filter(e=>e.ip===0xE7);same(nw.length,1);repack.exactCopy(r,nw[0],'V',u);
  same(r.traced.writes.filter(x=>x.command>=middle.command&&x.command<end.command&&x.before!==x.value)
    .filter(x=>x.command!==nw[0].command),[],'NOP changes only its exact V numeric copy');
  const expectedEnd=structuredClone(middle.ring);setWord(expectedEnd,'V',u);
  same(end.ring,expectedEnd,'complete NOP endpoint, all 630 tetras');
  return {prefix,boundaries:rows.length,all23LiveAtEveryActionBoundary:true,all23StoredAtEnd:true,
    VAlsoReservedInX:true,qStillStoredInW:true,remainingMarker:'Z',
    primaryReadOldX:reads[1].command,secondaryOutput:first,lateOverwriteV:late[0].command,
    nopReadX:nr[1].command,nopRestoreV:nw[0].command,
    other14OrdinaryUpper4ProgramAndServicesHeld:true,upperWordsChanged:0,
    workingExit:false,continuousRepeatTested:false,numericDomainProved:false,fullK1:false};
}
if(require.main===module) {
  const o={...probe.defaults,...JSON.parse(process.env.K1_ROTATE_RESERVE_OPTIONS||'{}')};
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS stored Z reserve:',JSON.stringify(check(r)));
  if(process.env.K1_ROTATE_RESERVE_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,check};
