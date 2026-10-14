#!/usr/bin/env node
'use strict';
// Audit a keyboard-created real/Y/T/V geometry, not a finished K1.
const assert=require('node:assert/strict');
const probe=require('./k1-z-backed-deep-entry.cjs');
const z=require('./k1-z-reserve-restored-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const m='9990FFFFFFF0',invalid='00008FFFFFFF';
const word=(ring,n,value)=>[...value].reverse().forEach((x,j)=>{ring[n][1+3*j]=parseInt(x,16);});
const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
const lower=e=>['U','V','W','Q'].map(n=>raw(e.ring[n]));
const markers=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
const ips=s=>s.split(' ').map(x=>parseInt(x,16));

function surface(o={},operation=probe.finish) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,operation);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread'],
    fixtureRegisters:{1:'unread',8:'unread'}},operation));
  same(a.seen,ds);same(a.result,undefined);
  const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicKeysWaitsAndDisplayOnly:true,fixturePreparationExcluded:true,assumedFirstSuccessfulReaderAttempts:true};
}

function path(es,first,source,sequence,chip=3) {
  const rows=es.filter(e=>e.command>=first&&e.command<first+sequence.length);
  same(rows.map(e=>chip===3?[e.ip,e.slot]:[e.otherChips[chip].ip,e.otherChips[chip].slot]),
    sequence.map((ip,i)=>[ip,slots[(slots.indexOf(source)+i)%15]]),'connected ROM path');
}

function check(r) {
  same(r.options.deepLeadPhase,2);same(r.options.deepTail,[['K','0']]);
  same(r.options.deepTailPhases,[1]);
  const prefix=z.unmark(r,'deep/prepare');
  checks.protectedFields(r,[0],['U','V','W','Q']);
  same(r.traced.writes.filter(w=>w.slot==='marker'&&w.nibble%3===1&&w.before!==w.value),[]);
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const at=s=>checks.boundary(r,s),ready=at('deep/clone'),cloned=at('deep/tail-phase-0'),
    nop=at('deep/tail-0'),end=at('done'),prep=at('deep/prepare');
  same(visible(at('deep/marker-0')),[u,'25'+u[2]+v.slice(3),u,v,u]);
  same(visible(ready),[invalid,m,u,v,m]);same(lower(ready),[u,u,q,p]);
  same(markers(ready),['T','X','marker']);
  repack.visibleRotation(r,'deep/prepare');
  same(r.traced.writes.filter(w=>w.command>=prep.command&&w.command<ready.command&&
    w.before!==w.value&&Object.hasOwn(r.before,w.slot)&&w.nibble%3===1),[],
    'new preparation/factory does not change any Ms word');

  const es=r.traced.events.filter(e=>e.stage==='deep/clone');
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['U',0x9E],['U',0x9E]]);
  const reads=es.filter(e=>e.ip===0xEE),saves=es.filter(e=>e.ip===0xE9),
    requests=es.filter(e=>e.ip===0xA3),late=es.filter(e=>e.ip===0xE7);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['X',m,0xA1],['X',m,0xE3]]);
  same([saves.length,requests.length,late.length],[1,1,1]);
  repack.exactCopy(r,saves[0],'V',m);repack.exactCopy(r,late[0],'U',m);
  const req=requests[0],header=ringAt(r,req.command);
  same(req.slot,'control');[28,31,34].forEach((n,i)=>{header.control[n]=[9,4,1][i];});
  same(ringAt(r,req.command+1),header);
  same(r.traced.writes.filter(w=>w.command===req.command).map(w=>[w.chip,w.slot,w.nibble,w.value]),
    [28,31,34].map((n,i)=>[3,'control',n,[9,4,1][i]]));
  const secondary=r.traced.writes.filter(w=>w.command>=ready.command&&w.command<cloned.command&&w.chip===4);
  const ack=secondary.filter(w=>w.ip===0x27),out=secondary.filter(w=>w.ip!==0x27),first=out[0].command;
  same(ack.map(w=>[w.slot,w.nibble,w.value]),[['control',31,15]]);
  same(out.map(w=>[w.command-first,w.ip,w.slot,w.nibble]),['X','Y'].flatMap((n,i)=>
    Array.from({length:12},(_,j)=>[i,i?0x2A:0x4E,n,1+3*j])));
  same(r.traced.writes.filter(w=>w.command>=first&&w.command<first+2),out);
  const pair=ringAt(r,first),before=structuredClone(pair);
  word(pair,'X',raw(before.Y));word(pair,'Y',raw(before.X));
  same(ringAt(r,first+2),pair,'exact ordinary X/Y swap');
  path(es,req.command,'marker',ips('6E 5E 50 52 53 4F 41 43 4D 60 37 37 37 37 37 37 27 61 4E 2A 39'),4);
  same(reads[1].command,first-1,'late reader still sees the old marker, not the output u');
  path(es,reads[1].command,'X',ips('EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE D9 F3 F7 F1 F3 F7 F1 F4 F6 F4 F6 F4 F6 F4 F6 F4 F6 F4 F6 F4 F6 F4 EA EC 40 41 42 46 E5 E5 E5 E6 E8 E7'));
  const allowed=new Set([saves[0].command,req.command,late[0].command,...secondary.map(w=>w.command)]);
  same(r.traced.writes.filter(w=>w.command>=ready.command&&w.command<cloned.command&&
    w.before!==w.value&&!allowed.has(w.command)),[]);
  const expected=structuredClone(ready.ring);
  for(const [n,value] of Object.entries({X:u,Y:m,U:m,V:m}))word(expected,n,value);
  [28,31,34].forEach((n,i)=>{expected.control[n]=[9,15,1][i];});
  same(cloned.ring,expected,'all 630 tetras after clone');
  same(nop.ring,cloned.ring,'fixed phase wait does not mutate the ring');
  same(markers(cloned),['T','U','V','Y','marker']);

  const ns=r.traced.events.filter(e=>e.stage==='deep/tail-0');
  assert.ok(ns.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  same(ns.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['control',0x9E],['Z',0x9E]]);
  const gate=ns.find(e=>e.ip===0x9C);same([gate.r[23],gate.r[26],gate.r[29]],[0,0,4]);
  const nr=ns.filter(e=>e.ip===0xEE),nw=ns.filter(e=>e.ip===0xE7);
  same(nr.map(e=>[e.slot,e.raw,e.nextIp]),[['W',q,0xAB],['X',u,0xE3]]);same(nw.length,1);
  same(ns.filter(e=>[0xE9,0xA3,0xA8].includes(e.ip)),[]);
  path(ns,gate.command,'control',ips('9C 9E 9F AA E5 E5 E6 ED EE AB AD A5 1F 14 D3 D5 9B 9B 9B 9C 9E 9F AA AC E2 E5 E5 E5 E5 E5 E6 ED EE'));
  repack.exactCopy(r,nw[0],'U',u);
  same(r.traced.writes.filter(w=>w.command>=nop.command&&w.command<end.command&&
    w.before!==w.value&&w.command!==nw[0].command),[],'NOP changes only U');
  word(expected,'U',u);same(end.ring,expected,'all 630 tetras after NOP');
  same(visible(end),[invalid,u,m,v,m]);same(lower(end),[u,m,q,p]);same(markers(end),['T','V','Y','marker']);
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  same(original.filter(x=>!snapshotFromRing(end.ring).words.includes(x)),[v]);
  same(['X1','X','Y','Z','T'].filter(n=>raw(end.ring[n])===v),['Z']);
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  return {prefix,boundaries:rows.length,clone:{reserveV:saves[0].command,lateReadOldMarker:reads[1].command,
    visibleSwap:first,lateMarkerToU:late[0].command},nop:{readX:nr[1].command,restoreU:nw[0].command},
    keyboardReachableYTV:true,all23LiveAtEveryActionBoundary:true,vOnlyInZ:true,
    other14OrdinaryUpper4ProgramAndServicesHeld:true,all23StoredAtEnd:false,
    workingExit:false,wholeNumericDomainProved:false,fullK1:false};
}

if(require.main===module) {
  const o={...probe.defaults,...JSON.parse(process.env.K1_Z_DEEP_OPTIONS||'{}')};
  console.log('PASS public surface:',JSON.stringify(surface(o)));
  const r=probe.traced(o);console.log('PASS native Y/T/V entry:',JSON.stringify(check(r)));
  if(process.env.K1_Z_DEEP_UNOBSERVED)console.log('PASS complete state without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,check,path,ips,word};
