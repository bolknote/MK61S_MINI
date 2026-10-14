#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-z-backed-lastx.cjs');
const deep=require('./k1-z-backed-deep-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const m='9990FFFFFFF0';
const names=['X1','X','Y','Z','T'];
const markers=ring=>Object.keys(ring).filter(n=>ring[n][22]===15).sort();

function frameCheck(r) {
  const original=snapshotFromRing(r.initial),end=r.rows.find(e=>e.stage==='done');
  same(new Set(original.words).size,23);
  same(r.rows.filter(x=>x.missing.length).map(x=>[x.stage,x.missing]),[]);
  for(const row of r.rows) {
    const s=snapshotFromRing(row.ring);
    same(s.program,original.program);same(s.services,original.services);
    same(s.words.slice(1,15),original.words.slice(1,15));
    same(s.words.slice(19),original.words.slice(19));
    same(row.values.marker,'000FFFFFFFFF');
  }
  const [p,u,v,w,q,a]=[0,15,16,17,18,19].map(i=>original.words[i]);
  same(['X','Y','Z','T','U','V','W','Q'].map(n=>end.values[n]),[p,u,m,v,u,a,q,p]);
  same(end.registers[0],w);same(markers(end.ring),['Z','marker']);
  return {boundaries:r.rows.length,all23LiveAtEveryFrameBoundary:true,
    visibleReadOfQ:true,copyOfP7InV:true,vOnlyInT:true,extraMarkers:['Z'],fullK1:false};
}

function check(r) {
  same(r.options.deepTail,[['K','0'],['F','В↑']]);same(r.options.deepTailPhases,[1,1]);
  const prefix=deep.check(prefixView(r,'deep/tail-phase-1',
    {deepTail:[['K','0']],deepTailPhases:[1]}));
  checks.protectedFields(r,[0],['U','V','W','Q']);
  same(r.traced.writes.filter(w=>w.slot==='marker'&&w.nibble%3===1&&w.before!==w.value),[]);
  const [u,v,w,q,a]=['U','V','W','Q','P7'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const at=checks.boundary(r,'deep/tail-1'),end=checks.boundary(r,'done');
  same(at.ring,checks.boundary(r,'deep/tail-phase-1').ring,'fixed phase wait is read-only');
  same(names.map(n=>raw(at.ring[n])),['00008FFFFFFF',u,m,v,m]);
  same(markers(at.ring),['T','V','Y','marker']);
  const es=r.traced.events.filter(e=>e.stage==='deep/tail-1');
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  const gates=es.filter(e=>e.ip===0x9C),reads=es.filter(e=>e.ip===0xEE);
  same(gates.map(e=>[e.slot,e.nextIp]),[['Z',0x9E]]);
  same([gates[0].r[30],gates[0].r[33]],[15,0]);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['Q',p,0xF0],['P7',a,0xE3]]);
  deep.path(es,gates[0].command,'Z',deep.ips('9C 9E 8C 91 92 93 94 95 98 9A 93 94 95 98 9A 8D 4F FF E5 E6 EE F0 E0 A7 E5 E5 E6 E8 E7 A8 A8 A8 A9 E1 91 92 93 94 95 98 9A 93 94 95 98 9A E2 E5 E5 E6 ED EE'));
  const push=checks.exactPush(r,'deep/tail-1',['X','Y','Z','T']);same(push.displaced,m);
  const pushed=ringAt(r,push.command+4);
  same(['X','Y','Z','T'].map(n=>raw(pushed[n])),[p,u,m,v]);
  same(markers(pushed),['V','Z','marker']);
  const late=es.filter(e=>e.ip===0xE7&&e.nextIp===0x47);same(late.length,1);
  repack.exactCopy(r,late[0],'V',a);
  // Both independent native fixtures use negative-exponent class-7 a.
  // Other class-7/8 paths have a separate conditional symbolic proof.
  assert.equal(a[0],'9');assert.match(a.slice(5),/^0{7}$/);
  const fmt=deep.ips('EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE D9');
  fmt.push(...Array.from({length:8},()=>[0xF3,0xF7,0xF1]).flat(),0xF4,0xF6,0xF4,0xEA,0xEC,
    ...deep.ips('40 41 42 46 E5 E5 E5 E5 E5 E6 E8 E7'));
  deep.path(es,reads[1].command,'P7',fmt);
  const writes=r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command);
  same(writes.filter(w=>w.chip!==3),[],'no secondary or tertiary write in LastX');
  same(writes.map(w=>[w.command,w.slot,w.nibble]),
    [...['X','Y','Z','T'].map((n,i)=>[push.command+i,n]),[late[0].command,'V']]
      .flatMap(([c,n])=>Array.from({length:12},(_,j)=>[c,n,1+3*j])),
    'exactly 48 push and 12 late-copy writes, no additional writers');
  const expected=structuredClone(at.ring);
  for(const [n,value] of Object.entries({X:p,Y:u,Z:m,T:v,V:a}))deep.word(expected,n,value);
  same(end.ring,expected,'LastX endpoint, all 630 tetras');
  same(markers(end.ring),['Z','marker']);
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  same(original.filter(x=>!snapshotFromRing(end.ring).words.includes(x)),[v]);
  same(names.filter(n=>raw(end.ring[n])===v),['T']);
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  return {prefix,boundaries:rows.length,acceptedZ:gates[0].command,readQ:reads[0].command,
    push,readP7:reads[1].command,removeV:late[0].command,
    conditionalPathNowKeyboardReachable:true,all23LiveAtEveryActionBoundary:true,
    other14OrdinaryUpper4ProgramAndServicesHeld:true,extraMarkers:['Z'],
    vOnlyInT:true,all23StoredAtEnd:false,workingExit:false,fullK1:false};
}

if(require.main===module) {
  const o={...probe.defaults,...JSON.parse(process.env.K1_Z_LASTX_OPTIONS||'{}')};
  console.log('PASS public surface:',JSON.stringify(deep.surface(o,probe.finish)));
  console.log('PASS frame boundaries:',JSON.stringify(frameCheck(probe.run(o))));
  const r=probe.traced(o);console.log('PASS exact connected LastX:',JSON.stringify(check(r)));
  if(process.env.K1_Z_LASTX_UNOBSERVED)console.log('PASS complete state without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={frameCheck,check};
