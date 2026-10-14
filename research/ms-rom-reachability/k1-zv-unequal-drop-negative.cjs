#!/usr/bin/env node
'use strict';
// Narrow negative control: fine-clear, safe swap, then unequal subtraction.
// A primary request in control does not guarantee a safe secondary output.
// Missing full numeric words are NOT claimed to be a whole-state collision.
const assert=require('node:assert/strict');
const probe=require('./k1-zv-clear-timing.cjs');
const release=require('./k1-zv-clear-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const deep=require('./k1-z-backed-deep-entry-check.cjs');
const same=assert.deepEqual;
const options={...probe.defaults,commandOffsets:[3],afterClear:[['↔'],['-']],afterClearPhases:[1,2]};
function check(r) {
  same(r.options.afterClear,options.afterClear);same(r.options.afterClearPhases,options.afterClearPhases);
  const prefix=release.check(prefixView(r,'clear-tail/phase-0',{afterClear:[],afterClearPhases:[]}));
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);
  const u=r.before.U.slice(2),v=r.before.V.slice(2),a=r.before.P7.slice(2),p=r.beforeRegisters[0],q=r.before.Q.slice(2);
  const start=checks.boundary(r,'clear-tail/0'),mid=checks.boundary(r,'clear-tail/phase-1');
  const want=structuredClone(start.ring);
  for(const [slot,value] of [['U',a],['X',u],['Y',a],['V',a]])deep.word(want,slot,value);
  [28,31,34].forEach((n,i)=>{want.control[n]=[parseInt(a[2],16),15,1][i];});
  same(mid.ring,want,'safe swap all 630 endpoint tetras');
  const rows=repack.boundaryLosses(prefixView(r,'clear-tail/1'));same(rows.filter(e=>e.missing.length),[]);
  const stage='clear-tail/1',at=checks.boundary(r,stage),end=checks.boundary(r,'done');
  const es=r.traced.events.filter(e=>e.stage===stage),ww=r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command);
  const reqs=es.filter(e=>e.ip===0xA3);same(reqs.length,1);const req=reqs[0];same(req.slot,'control');
  const old=ringAt(r,req.command),expected=structuredClone(old);
  [28,31,34].forEach((n,i)=>{expected.control[n]=[parseInt(u[2],16),1,1][i];});same(ringAt(r,req.command+1),expected);
  same(raw(old.X),u);same(raw(old.Y),a);assert.notEqual(u,a);
  const secondary=ww.filter(w=>w.chip===4),acks=secondary.filter(w=>w.ip===0x27),out=secondary.filter(w=>w.ip!==0x27);
  same(acks.slice(0,2).map(w=>[w.slot,w.nibble,w.value]),[['T',31,15],['T',31,15]]);
  const first=out[0].command,block=out.filter(w=>w.command<first+4);
  same(block.map(w=>[w.command-first,w.ip,w.slot,w.nibble]),['V','W','Q','P7'].flatMap((slot,i)=>
    Array.from({length:12},(_,j)=>[i,i===3?0x2A:0x3A,slot,1+3*j])));
  const s=snapshotFromRing(end.ring),live=[...s.words,...['X1','X','Y','Z','T'].map(n=>raw(end.ring[n]))];
  same([p,v,q].filter(value=>!live.includes(value)),[p,v,q]);
  same(raw(end.ring.T),'9F3'+v.slice(3));
  same(r.afterProgram,r.beforeProgram);
  return {prefix,primaryRequest:{command:req.command,slot:req.slot},firstSecondaryAck:acks[0].command,
    wrongSecondaryAckSlot:'T',firstSecondaryOutput:first,wrongOutputSlots:['V','W','Q','P7'],
    missingWholeWords:['p','v','q'],fullMachineCollisionProved:false,fullK1ImpossibilityProved:false};
}
if(require.main===module)console.log('PASS narrow negative:',JSON.stringify(check(probe.traced(options))));
module.exports={options,check};
