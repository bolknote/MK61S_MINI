#!/usr/bin/env node
'use strict';
// One exact failed continuation, not a search or an impossibility theorem:
// K-multiply; clear; K-NOT; K-fraction. The final request consumes sole v in T.
const assert=require('node:assert/strict');
const probe=require('./k1-y-t-rotate-reserve.cjs');
const reserve=require('./k1-y-t-rotate-reserve-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const afterReserve=[['K','×'],['Сx'],['K','Сx'],['K','8']];
function check(r) {
  same(r.options.afterReserve,afterReserve);
  const prefix=reserve.check(r,'rotate/tail-0');
  checks.protectedFields(r,[0],['U','V','W','Q']);
  const v=r.before.V.slice(2),u=r.before.U.slice(2),q=r.before.Q.slice(2);
  const last=checks.boundary(r,'rotate/tail-3'),end=checks.boundary(r,'done');
  same(['X1','X','Y','Z','T','U','V','W'].map(n=>raw(last.ring[n])),
    [q,'000000000000','25'+q.slice(2),'9990FFFFFFF0',v,'000000000000',u,q]);
  const copies=ring=>[...snapshotFromRing(ring).words,...['X1','X','Y','Z','T'].map(n=>raw(ring[n]))];
  same(copies(last.ring).filter(x=>x===v),[v],'v remains only in T before the final operation');
  const es=r.traced.events.filter(e=>e.stage==='rotate/tail-3');
  const request=es.find(e=>e.ip===0xA3);assert.ok(request);same(request.slot,'T');
  const before=ringAt(r,request.command),expected=structuredClone(before);
  same(raw(before.T),v);same(copies(before).filter(x=>x===v),[v]);
  const values=[parseInt(u[2],16),5,3];[28,31,34].forEach((n,i)=>{expected.T[n]=values[i];});
  same(ringAt(r,request.command+1),expected,'only the three T request tetras change, all 630 checked');
  same(r.traced.writes.filter(w=>w.command===request.command).map(w=>[w.chip,w.slot,w.nibble,w.value]),
    [28,31,34].map((n,i)=>[3,'T',n,values[i]]));
  same(copies(expected).includes(v),false,'last stored/visible copy of v is lost at the request');
  const rows=repack.boundaryLosses(r);
  same(rows.filter(x=>x.missing.length).map(x=>[x.stage,x.missing]),[['done',[v]]]);
  same(['U','V','W','Q'].map(n=>raw(end.ring[n])),['000000000000','000000000000',q,r.beforeRegisters[0]]);
  same(raw(end.ring.X1),u);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),['Z','marker']);
  return {prefix,boundaries:rows.length,request:request.command,requestSlot:'T',lostOriginal:'Ms V',
    other14OrdinaryUpper4ProgramAndServicesHeld:true,newVMarker:false,
    rejectedCandidate:true,notGeneralImpossibility:true};
}
if(require.main===module) {
  const o={...probe.defaults,afterReserve};const r=probe.run(o);
  console.log('PASS exact factory negative:',JSON.stringify(check(r)));
  if(process.env.K1_ROTATE_FACTORY_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={afterReserve,check};
