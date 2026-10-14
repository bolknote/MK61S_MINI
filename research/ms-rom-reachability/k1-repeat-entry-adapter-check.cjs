#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-repeat-entry-adapter.cjs');
const {snapshotFromRing,PLACES}=require('./k1-permutation-oracle.cjs');
const prior=require('./k1-stack-close-repeat-check.cjs');
const mapping=Array.from({length:23},(_,i)=>i);
for(const [d,s] of [[0,15],[15,0],[16,18],[18,20],[19,16],[20,19]])mapping[d]=s;
const same=(a,b)=>assert.deepEqual(a,b);
function check(r) {
  const original=snapshotFromRing(r.initial),at=s=>r.rows.find(x=>x.stage===s);
  assert.equal(new Set(original.words).size,23);
  same(r.options.adapterPhase,2);same(r.options.adapterActions,probe.closedDefaults.adapterActions);
  same(r.options.exitActions,probe.closedDefaults.exitActions);assert.equal(r.options.lowerPush,true);
  const first=snapshotFromRing(at('between').ring);
  same(first.words,prior.mapping.map(i=>original.words[i]));
  same(r.rows.filter(x=>x.missing.length).map(x=>({stage:x.stage,missing:x.missing})),[]);
  for(const row of r.rows) {
    const s=snapshotFromRing(row.ring);
    same(s.program,original.program);same(s.services,original.services);
    same(s.words.slice(1,15),original.words.slice(1,15));
  }
  const end=at(r.options.verifyExit?'post/manual':'done'),last=at('done');
  same(snapshotFromRing(end.ring).words,mapping.map(i=>original.words[i]));
  for(const e of [end,last]) {
    same(Object.keys(e.ring).filter(n=>e.ring[n][22]===15),['marker']);
    same(e.values.marker,'000FFFFFFFFF');
  }
  if(r.options.verifyExit) {
    same(at('post/zero').values.X,'000050000000');
    same(at('post/program').values.X,'000000000000');
    same(last.values.X,'000050000000');
    same(snapshotFromRing(last.ring).words,snapshotFromRing(end.ring).words);
  }
  return {boundaries:r.rows.length,all23LiveAtEveryBoundary:true,
    all23BackInStoredWords:true,allExtraMarkersRemoved:true,
    mapping:PLACES.map((p,i)=>[p,PLACES[mapping[i]]]).filter(([a,b])=>a!==b),
    firstAndDifferentSecondEntryWithoutReset:true,
    workingExitTested:!!r.options.verifyExit,transientWritesChecked:false,
    notTwoIdenticalInvocations:true,repeatabilityProved:false,numericDomainProved:false,fullK1:false};
}
function negative(r) {
  same(r.options.adapterPhase,0);same(r.options.adapterActions,[]);
  same(r.options.exitActions,[]);same(r.options.lowerPush,false);
  same(r.options.stopAt,'entry/tail-1');same(r.options.verifyExit,false);
  const initial=snapshotFromRing(r.initial),first=r.rows.find(x=>x.stage==='between');
  same(snapshotFromRing(first.ring).words,prior.mapping.map(i=>initial.words[i]));
  const lost=r.rows.find(x=>x.missing.length),q=r.before.Q.slice(2);
  same(lost.stage,'second/entry/tail-1');same(lost.missing,[q]);
  same(r.rows.at(-1).missing,[q]);
  for(const row of r.rows) {
    const s=snapshotFromRing(row.ring);same(s.program,initial.program);same(s.services,initial.services);
  }
  return {rejected:'no extra hidden rotation',firstCallStillPasses:true,
    firstLoss:lost.stage,lostOriginal:'Ms.Q',nativeCauseAuditedBy:'k1-stack-close-repeat-audit.cjs',
    transientWritesChecked:false,notGeneralImpossibility:true};
}
if(require.main===module) {
  const o={...probe.closedDefaults,verifyExit:true,...JSON.parse(process.env.K1_REPEAT_ADAPTER_OPTIONS||'{}')};
  const rejected=!!process.env.K1_REPEAT_ADAPTER_NEGATIVE;
  if(rejected)Object.assign(o,{adapterPhase:0,adapterActions:[],exitActions:[],lowerPush:false,
    stopAt:'entry/tail-1',verifyExit:false});
  console.log('PASS '+(rejected?'negative control':'adapted second entry, frame boundaries')+':',
    JSON.stringify((rejected?negative:check)(probe.run(o))));
}
module.exports={mapping,check,negative};
