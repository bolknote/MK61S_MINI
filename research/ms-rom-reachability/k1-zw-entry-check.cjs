#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-zw-entry.cjs');
const deep=require('./k1-z-backed-deep-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const m='9990FFFFFFF0',invalid='00008FFFFFFF';
const marks=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
const word=deep.word,ips=deep.ips,path=deep.path;

function endpoint(r,e,expectedVisibleSource='P7') {
  const initial=snapshotFromRing(r.initial??r.traced.events.find(x=>x.ring).ring),s=snapshotFromRing(e.ring);
  const [p,u,v,w,q,a]=[0,15,16,17,18,19].map(i=>initial.words[i]);
  const expected=initial.words.slice();
  for(const [dst,value] of [[0,w],[15,u],[16,a],[17,m],[18,q],[19,p]])expected[dst]=value;
  same(s.words,expected);same(visible(e),[invalid,r.before[expectedVisibleSource].slice(2),u,m,v]);same(marks(e),['W','Z','marker']);
  same(initial.words.filter(x=>!s.words.includes(x)),[v]);
  same(['X1','X','Y','Z','T'].filter(n=>raw(e.ring[n])===v),['T']);
  same(s.program,initial.program);same(s.services,initial.services);
}

function frameCheck(r,expectedVisibleSource='P7') {
  const original=snapshotFromRing(r.initial);same(new Set(original.words).size,23);
  same(r.rows.filter(x=>x.missing.length),[]);
  for(const row of r.rows) {
    const s=snapshotFromRing(row.ring);same(s.words.slice(1,15),original.words.slice(1,15));
    same(s.words.slice(20),original.words.slice(20));same(s.program,original.program);same(s.services,original.services);
    same(row.values.marker,'000FFFFFFFFF');
  }
  endpoint(r,r.rows.find(e=>e.stage==='immediate'),expectedVisibleSource);
  endpoint(r,r.rows.find(e=>e.stage==='done'),expectedVisibleSource);
  return {boundaries:r.rows.length,all23LiveAtEveryFrameBoundary:true,hiddenMarkerMovedToW:true,
    vOnlyInT:true,all23StoredAtEnd:false,workingExit:false,fullK1:false};
}

function formatter(r,stage,read,late,target,markers) {
  // The two native fixtures use full eight-digit mantissas and positive
  // scientific exponents. The wider class-0..4 claim has a separate proof.
  same(read.raw[0],'0');assert.ok(Number(read.raw.slice(1,3))>=8);assert.notEqual(read.raw.at(-1),'0');
  const seq=ips('EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE D0 F3 F7 F1');
  seq.push(...Array.from({length:8},()=>[0xF4,0xF6]).flat(),...ips('F4 EA EC 40 41 42 46'));
  while(!markers.includes(slots[(slots.indexOf(read.slot)+seq.length)%15]))seq.push(0xE5);
  seq.push(...ips('E5 E6 E8 E7'));
  same(late.command-read.command+1,seq.length);same(late.slot,target);
  path(r.traced.events.filter(e=>e.stage===stage),read.command,read.slot,seq);
}

function operation(r,index,spec) {
  const stage='deep/tail-'+index,endStage=index===1?'deep/tail-2':'done';
  const start=checks.boundary(r,stage),end=checks.boundary(r,endStage),es=r.traced.events.filter(e=>e.stage===stage);
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  const gates=es.filter(e=>e.ip===0x9C),reads=es.filter(e=>e.ip===0xEE),late=es.filter(e=>e.ip===0xE7&&e.nextIp===0x47);
  same(gates.map(e=>[e.slot,e.nextIp]),[['control',0x9E]]);same(late.length,1);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),spec.reads);
  path(es,gates[0].command,'control',ips(spec.path));
  const push=checks.exactPush(r,stage,spec.targets);same(push.displaced,spec.displaced);
  if(index===2) {
    const d6=es.filter(e=>e.ip===0xD6);same(d6.length,1);same(d6[0].slot,'marker');
    same(raw(ringAt(r,d6[0].command).marker,0),r.beforeRegisters[8]);
    same(raw(ringAt(r,push.command+4).V),r.beforeRegisters[8]);
  }
  repack.exactCopy(r,late[0],spec.late,spec.lateValue);
  formatter(r,stage,reads[1],late[0],spec.late,spec.markers);
  const ww=r.traced.writes.filter(w=>w.command>=start.command&&w.command<end.command);
  same(ww.map(w=>[w.chip,w.command,w.slot,w.nibble]),
    [...spec.targets.map((n,i)=>[push.command+i,n]),[late[0].command,spec.late]]
      .flatMap(([c,n])=>Array.from({length:12},(_,j)=>[3,c,n,1+3*j])),
    'only the 48 push and 12 late-copy tetras; no secondary/tertiary writers');
  const want=structuredClone(start.ring);
  for(const [dst,value] of Object.entries(spec.final))word(want,dst,value);
  same(end.ring,want,'all 630 endpoint tetras');
  return {stage,read:reads[0].command,push,lateRead:reads[1].command,lateCopy:late[0].command};
}

function check(r) {
  same(r.options.deepTail,probe.defaults.deepTail);same(r.options.deepTailPhases,probe.defaults.deepTailPhases);
  same(r.options.afterW??[],[]);
  const prefix=deep.check(prefixView(r,'deep/tail-1',{deepTail:[['K','0']],deepTailPhases:[1]}));
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);
  same(r.traced.writes.filter(w=>w.slot==='marker'&&w.nibble%3===1&&w.before!==w.value),[]);
  const [u,v,w,q,a]=['U','V','W','Q','P7'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const enter=operation(r,1,{reads:[['U',u,0xE0],['P7',a,0xE3]],
    targets:['X','Y','Z','T'],displaced:m,late:'X',lateValue:a,markers:['marker','Z','V'],
    final:{X:a,Y:u,Z:m,T:v},
    path:'9C 9E 8C 91 92 93 94 95 98 9A 93 94 95 98 9A 8D 4F EF E5 E6 ED EE E0 A7 E5 E5 E5 E5 E5 E5 E6 E8 E7 A8 A8 A8 A9 E1 91 92 93 94 95 98 9A 93 94 95 98 9A E2 E5 E5 E6 ED EE'});
  same(marks(checks.boundary(r,'deep/tail-2')),['V','Z','marker']);
  const shift=operation(r,2,{reads:[['V',m,0xAB],['X',a,0xE3]],
    targets:['V','W','Q','P7'],displaced:a,late:'V',lateValue:a,markers:['marker','Z','W'],
    final:{V:a,W:m,Q:q,P7:p},
    path:'9C 9E 9F AA E5 E6 ED EE AB AD A6 01 01 01 01 02 02 02 02 02 02 02 02 02 03 04 BA CB DD D6 A7 E5 E5 E5 E5 E6 E8 E7 A8 A8 A8 A9 AC E2 E5 E6 ED EE'});
  endpoint(r,checks.boundary(r,'done'));
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  return {prefix,boundaries:rows.length,enter,shift,all23LiveAtEveryActionBoundary:true,
    other14OrdinaryUpper3ProgramAndServicesHeld:true,hiddenMarkerMovedToW:true,
    originalP0InP7:true,oldP7InV:true,vOnlyInT:true,extraMarkers:['Z','W'],
    all23StoredAtEnd:false,workingExit:false,lastTwoMsChanged:false,fullK1:false};
}

if(require.main===module) {
  const o={...probe.defaults,...JSON.parse(process.env.K1_ZW_OPTIONS||'{}')};
  console.log('PASS public surface:',JSON.stringify(deep.surface(o,probe.finish)));
  console.log('PASS frame boundaries:',JSON.stringify(frameCheck(probe.run(o))));
  const r=probe.traced(o);console.log('PASS exact Z/W entry:',JSON.stringify(check(r)));
  if(process.env.K1_ZW_UNOBSERVED)console.log('PASS complete state without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={endpoint,frameCheck,formatter,operation,check};
