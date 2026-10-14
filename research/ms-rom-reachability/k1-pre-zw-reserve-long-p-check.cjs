#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-pre-zw-reserve-long-p.cjs');
const read=require('./k1-zw-read-check.cjs');
const zq=require('./k1-zq-origin-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const m='9990FFFFFFF0';
function endpoint(r,e) {
  const s=snapshotFromRing(e.ring),initial=snapshotFromRing(r.initial??r.traced.events.find(x=>x.ring).ring);
  const [p,u,v,w,q,a,b,c,d]=[0,15,16,17,18,19,20,21,22].map(i=>initial.words[i]);
  const expected=initial.words.slice();
  for(const [i,value] of [[0,w],[15,u],[16,p],[17,a],[18,m],[19,q],[20,a],[21,p],[22,c]])expected[i]=value;
  same(s.words,expected);same(['X1','X','Y','Z','T'].map(n=>raw(e.ring[n])),['00008FFFFFFF',b,u,m,v]);
  same(raw(e.ring.marker),d);same(slots.filter(n=>e.ring[n][22]===15),['Z','Q']);
  same(initial.words.filter(x=>!s.words.includes(x)),[v,b,d]);
  same(initial.words.filter(x=>![...s.words,...slots.map(n=>raw(e.ring[n]))].includes(x)),[]);
}
function frameCheck(r) {
  const initial=snapshotFromRing(r.initial),d=r.before.P10.slice(2);same(new Set(initial.words).size,23);
  for(const row of r.rows) {
    const s=snapshotFromRing(row.ring);
    same(s.words.slice(1,15),initial.words.slice(1,15));same(s.program,initial.program);same(s.services,initial.services);
    if(row.missing.length){same(row.missing,[d]);same(row.values.marker,d);}
    same(initial.words.filter(x=>![...s.words,...slots.map(n=>row.values[n])].includes(x)),[]);
  }
  endpoint(r,r.rows.find(x=>x.stage==='immediate'));endpoint(r,r.rows.find(x=>x.stage==='done'));
  return {boundaries:r.rows.length,all23IncludingPhysicalMarker:true,originalP8OnlyInX:true,fullK1:false};
}
function check(r) {
  same(r.options.afterW,probe.defaults.afterW);same(r.options.afterWPhases,probe.defaults.afterWPhases);
  const prefix=read.check(prefixView(r,'w/tail-1',{afterW:[['K','0']],afterWPhases:[0]}));
  checks.protectedFields(r,[0],Object.keys(r.before));
  // Rename stages only in the passive journal to reuse the exact existing
  // origin-moving operation audit. No machine state is restored or edited.
  const rename=s=>s==='w/tail-1'?'w/tail-0':s==='w/tail-2'?'w/tail-1':s==='w/tail-0'?'pre-reserve/nop':s;
  const local={...r,traced:{...r.traced,events:r.traced.events.map(e=>({...e,stage:rename(e.stage)})),
    writes:r.traced.writes.map(w=>({...w,stage:rename(w.stage)}))}};
  const [a,b,c,d]=['P7','P8','P9','P10'].map(n=>r.before[n].slice(2)),q=r.before.Q.slice(2),p=r.beforeRegisters[0];
  const move=zq.operation(local,0,{origin:'control',reads:[['V',a,0xAB],['V',a,0xE3]],
    targets:['P8','P9','P10','marker'],displaced:'000FFFFFFFFF',target:'P8',value:a,
    markers:['Z','W'],formatClass:0,final:{P8:a,P9:b,P10:c,marker:d},
    path:'9C 9E 9F AA E5 E6 ED EE AB AD A6 01 01 01 01 02 03 04 BA CB DD D6 A7 E5 E6 E8 E7 A8 A8 A8 A9 AC E2 E5 E5 E6 ED EE'});
  const shift=zq.operation(local,1,{origin:'T',reads:[['P7',p,0xF0],['V',p,0xE3]],
    targets:['V','W','Q','P7'],displaced:p,target:'P9',value:p,
    markers:['Z','Q'],formatClass:0,final:{V:p,W:a,Q:m,P7:q,P9:p},
    path:'9C 9E 8C 91 92 93 94 95 98 9A 93 94 95 98 9A 8D 4F FF E5 E6 EE F0 E0 A7 E5 E5 E5 E5 E5 E5 E6 E8 E7 A8 A8 A8 A9 E1 91 92 93 94 95 98 9A 93 94 95 98 9A E2 E5 E5 E5 E5 E5 E5 E5 E5 E5 E6 ED EE'});
  endpoint(r,checks.boundary(r,'done'));
  const initial=snapshotFromRing(r.traced.events.find(e=>e.ring).ring),rows=r.traced.events.filter(e=>e.ring&&r.traced.events.find(x=>x.stage===e.stage)===e);
  for(const e of rows) {
    const s=snapshotFromRing(e.ring),live=[...s.words,...slots.map(n=>raw(e.ring[n]))];
    same(initial.words.filter(x=>!live.includes(x)),[]);
  }
  return {prefix,boundaries:rows.length,move,shift,longPFormatterWritesP9:true,originalP8OnlyInX:true,
    all23IncludingPhysicalMarker:true,vOnlyInT:true,qOnlyInP7:true,workingExit:false,fullK1:false};
}
if(require.main===module) {
  const options=JSON.parse(process.env.K1_PRE_ZW_OPTIONS||'{}');
  if(!process.env.K1_PRE_ZW_NATIVE_ONLY)console.log('PASS frames:',JSON.stringify(frameCheck(probe.run(options))));
  const r=probe.traced(options);console.log('PASS native:',JSON.stringify(check(r)));
  if(process.env.K1_PRE_ZW_UNOBSERVED)console.log('PASS complete state without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={endpoint,frameCheck,check};
