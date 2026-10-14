#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-zq-origin-entry.cjs');
const entry=require('./k1-zw-entry-check.cjs');
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

function endpoint(r,e) {
  const initial=snapshotFromRing(r.initial??r.traced.events.find(x=>x.ring).ring),s=snapshotFromRing(e.ring);
  const [p,u,v,w,q,a,b,c,d]=[0,15,16,17,18,19,20,21,22].map(i=>initial.words[i]);
  const expected=initial.words.slice();
  for(const [i,value] of [[0,w],[15,u],[16,p],[17,a],[18,m],[19,q],[20,a],[21,b],[22,c]])expected[i]=value;
  same(s.words,expected);same(['X1','X','Y','Z','T'].map(n=>raw(e.ring[n])),[invalid,a,u,m,v]);
  same(raw(e.ring.marker),d);same(marks(e),['Q','Z']);
  same(initial.words.filter(x=>!s.words.includes(x)),[v,d]);
  same(initial.words.filter(x=>![...s.words,...['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]))].includes(x)),[d]);
  same(initial.words.filter(x=>![...s.words,...slots.map(n=>raw(e.ring[n]))].includes(x)),[]);
  same(s.program,initial.program);same(s.services,initial.services);
}

function frameCheck(r) {
  const original=snapshotFromRing(r.initial);same(new Set(original.words).size,23);
  const d=r.before.P10.slice(2);
  for(const row of r.rows) {
    const s=snapshotFromRing(row.ring);
    same(s.words.slice(1,15),original.words.slice(1,15));same(s.program,original.program);same(s.services,original.services);
    // Keep the standard oracle honest: d is outside its storage domain.
    if(row.missing.length) {same(row.missing,[d]);same(row.values.marker,d);}
    same(original.words.filter(x=>![...s.words,...slots.map(n=>row.values[n])].includes(x)),[]);
  }
  endpoint(r,r.rows.find(e=>e.stage==='immediate'));endpoint(r,r.rows.find(e=>e.stage==='done'));
  return {boundaries:r.rows.length,all23IncludingTemporaryMarker:true,standardBankAndStackMissing:[d],
    realMarkerRestored:false,workingExit:false,fullK1:false};
}

function formatter(r,stage,read,late,markers,expectedClass) {
  const value=read.raw;assert.equal(value[0],'0');assert.notEqual(value,'000000000000');
  let zeroes=0;while(value.at(-1-zeroes)==='0')zeroes++;
  const decimal=Number(value.slice(1,3))<=7;
  same(zeroes+Number(decimal),expectedClass);
  const seq=deep.ips('EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE D0');
  if(decimal)seq.push(0xF2);
  seq.push(...Array.from({length:zeroes+1},()=>[0xF3,0xF7,0xF1]).flat(),
    ...Array.from({length:8-zeroes},()=>[0xF4,0xF6]).flat(),...deep.ips('F4 EA EC 40 41 42 46'));
  while(!markers.includes(slots[(slots.indexOf(read.slot)+seq.length)%15]))seq.push(0xE5);
  seq.push(...deep.ips('E5 E6 E8 E7'));
  same(late.command-read.command+1,seq.length);
  deep.path(r.traced.events.filter(e=>e.stage===stage),read.command,read.slot,seq);
}

function operation(r,i,spec) {
  const stage='w/tail-'+i,start=checks.boundary(r,stage),end=checks.boundary(r,i?'done':'w/tail-1');
  const es=r.traced.events.filter(e=>e.stage===stage),gates=es.filter(e=>e.ip===0x9C),
    reads=es.filter(e=>e.ip===0xEE),late=es.filter(e=>e.ip===0xE7&&e.nextIp===0x47);
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  same(gates.map(e=>[e.slot,e.nextIp]),[[spec.origin,0x9E]]);same(late.length,1);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),spec.reads);
  deep.path(es,gates[0].command,spec.origin,deep.ips(spec.path));
  const push=checks.exactPush(r,stage,spec.targets);same(push.displaced,spec.displaced);
  if(i===0) {
    const d6=es.filter(e=>e.ip===0xD6);same(d6.length,1);same(d6[0].slot,'U');
    same(raw(ringAt(r,d6[0].command).U,0),r.before.W.slice(2));
    same(raw(ringAt(r,push.command+4).P8),r.before.W.slice(2));
  }
  repack.exactCopy(r,late[0],spec.target,spec.value);
  formatter(r,stage,reads[1],late[0],spec.markers,spec.formatClass);
  const ww=r.traced.writes.filter(w=>w.command>=start.command&&w.command<end.command);
  same(ww.map(w=>[w.chip,w.command,w.slot,w.nibble]),
    [...spec.targets.map((n,j)=>[push.command+j,n]),[late[0].command,spec.target]]
      .flatMap(([c,n])=>Array.from({length:12},(_,j)=>[3,c,n,1+3*j])),
    'exactly 48 push and 12 formatter writes, no secondary/tertiary writes');
  const expected=structuredClone(start.ring);
  for(const [n,value] of Object.entries(spec.final))deep.word(expected,n,value);
  same(end.ring,expected,'all 630 endpoint tetras');same(marks(end),spec.markers.slice().sort());
  return {stage,gate:gates[0].command,reads:reads.map(e=>[e.command,e.slot]),push,late:late[0].command};
}

function check(r) {
  same(r.options.afterW,probe.defaults.afterW);same(r.options.afterWPhases,probe.defaults.afterWPhases);
  const prefix=entry.check(prefixView(r,'w/tail-0',{afterW:[],afterWPhases:[]}));
  checks.protectedFields(r,[0],Object.keys(r.before));
  const [a,b,c,d]=['P7','P8','P9','P10'].map(n=>r.before[n].slice(2)),q=r.before.Q.slice(2),p=r.beforeRegisters[0];
  const move=operation(r,0,{origin:'control',reads:[['V',a,0xAB],['V',a,0xE3]],
    targets:['P8','P9','P10','marker'],displaced:'000FFFFFFFFF',target:'P8',value:a,
    markers:['Z','W'],formatClass:0,final:{P8:a,P9:b,P10:c,marker:d},
    path:'9C 9E 9F AA E5 E6 ED EE AB AD A6 01 01 01 01 02 03 04 BA CB DD D6 A7 E5 E6 E8 E7 A8 A8 A8 A9 AC E2 E5 E5 E6 ED EE'});
  const shift=operation(r,1,{origin:'T',reads:[['P7',p,0xF0],['V',p,0xE3]],
    targets:['V','W','Q','P7'],displaced:p,target:'V',value:p,
    markers:['Z','Q'],formatClass:6,final:{V:p,W:a,Q:m,P7:q},
    path:'9C 9E 8C 91 92 93 94 95 98 9A 93 94 95 98 9A 8D 4F FF E5 E6 EE F0 E0 A7 E5 E5 E5 E5 E5 E5 E6 E8 E7 A8 A8 A8 A9 E1 91 92 93 94 95 98 9A 93 94 95 98 9A E2 E5 E5 E5 E5 E5 E5 E5 E5 E5 E6 ED EE'});
  endpoint(r,checks.boundary(r,'done'));
  const rows=r.traced.events.filter(e=>e.ring&&r.traced.events.find(x=>x.stage===e.stage)===e);
  const originals=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  for(const e of rows) {
    const s=snapshotFromRing(e.ring),visible=['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
    const missing=originals.filter(x=>![...s.words,...visible].includes(x));
    if(missing.length){same(missing,[d]);same(raw(e.ring.marker),d);}
    same(originals.filter(x=>![...s.words,...visible,raw(e.ring.marker)].includes(x)),[]);
  }
  return {prefix,boundaries:rows.length,move,shift,all23IncludingTemporaryMarker:true,
    physicalMarkerContainsOriginalP10:true,onlyMarkers:['Z','Q'],vOnlyInT:true,
    originalQOnlyInP7:true,other14OrdinaryProgramAndServicesHeld:true,
    realMarkerRestored:false,all23StoredAtEnd:false,workingExit:false,fullK1:false};
}

if(require.main===module) {
  const o={...probe.defaults,...JSON.parse(process.env.K1_ZQ_OPTIONS||'{}')};
  console.log('PASS public surface:',JSON.stringify(deep.surface(o,probe.finish)));
  console.log('PASS frame boundaries:',JSON.stringify(frameCheck(probe.run(o))));
  const r=probe.traced(o);console.log('PASS exact Z/Q entry:',JSON.stringify(check(r)));
  if(process.env.K1_ZQ_UNOBSERVED)console.log('PASS complete state without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={endpoint,frameCheck,formatter,operation,check};
