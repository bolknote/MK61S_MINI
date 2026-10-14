#!/usr/bin/env node
'use strict';
// Frame-boundary evidence for G; C^2; B. The exact native audit is separate.
const assert=require('node:assert/strict');
const probe=require('./k1-adapted-third-entry.cjs');
const {snapshotFromRing,PLACES}=require('./k1-permutation-oracle.cjs');
const previous=require('./k1-repeat-entry-adapter-check.cjs');
const same=(a,b)=>assert.deepEqual(a,b);
const rotate=(words,indices)=>{
  const old=indices.map(i=>words[i]);
  indices.forEach((i,j)=>{words[i]=old[(j+indices.length-1)%indices.length];});
};
const lowerMappings=[previous.mapping.slice()];
for(let i=0;i<2;i++) {
  const next=lowerMappings.at(-1).slice();rotate(next,[0,15,16,17]);lowerMappings.push(next);
}
const mapping=lowerMappings.at(-1).slice();
rotate(mapping,[0,17,15]);rotate(mapping,[18,20,19]);
const wanted=Array.from({length:23},(_,i)=>i);rotate(wanted,[0,15,16,18,17]);same(mapping,wanted);

function check(r) {
  const original=snapshotFromRing(r.initial),at=s=>{
    const row=r.rows.find(x=>x.stage===s);assert.ok(row,s);return row;
  };
  same(r.options.lowerRounds,2);same(r.options.thirdPhase,0);
  same(r.options.adapterPhase,probe.defaults.adapterPhase);
  same(r.options.adapterActions,probe.defaults.adapterActions);
  same(r.options.exitActions,probe.defaults.exitActions);same(r.options.lowerPush,true);
  same(new Set(original.words).size,23);
  same(r.rows.filter(x=>x.missing.length).map(x=>({stage:x.stage,missing:x.missing})),[]);
  for(const row of r.rows) {
    const s=snapshotFromRing(row.ring);
    same(s.program,original.program);same(s.services,original.services);
    same(s.words.slice(1,15),original.words.slice(1,15));
    same(s.words.slice(21),original.words.slice(21));
  }
  for(const [i,stage] of ['lower/0/start','lower/1/start','third/phase'].entries()) {
    const row=at(stage);same(snapshotFromRing(row.ring).words,lowerMappings[i].map(j=>original.words[j]));
    same(Object.keys(row.ring).filter(n=>row.ring[n][22]===15),['marker']);
    same(row.phase,84);
  }
  const end=at(r.options.verifyExit?'post/manual':'immediate'),done=at('done');
  for(const row of [end,done]) {
    same(snapshotFromRing(row.ring).words,mapping.map(i=>original.words[i]));
    same(Object.keys(row.ring).filter(n=>row.ring[n][22]===15),['marker']);
    same(row.values.marker,'000FFFFFFFFF');
  }
  if(r.options.verifyExit) {
    same(at('post/zero').values.X,'000050000000');
    same(at('post/program').values.X,'000000000000');
    same(done.values.X,'000050000000');
  }
  return {boundaries:r.rows.length,all23LiveAtEveryBoundary:true,all23StoredAtExit:true,
    allExtraMarkersRemoved:true,allFourUpperWordsRestored:true,
    mapping:PLACES.map((p,i)=>[p,PLACES[mapping[i]]]).filter(([a,b])=>a!==b),
    uninterruptedThirdEntry:true,workingExitTested:!!r.options.verifyExit,
    transientWritesChecked:false,unboundedRepetitionProved:false,wholeNumericDomainProved:false,fullK1:false};
}
if(require.main===module) {
  const o={verifyExit:true,...JSON.parse(process.env.K1_THIRD_ENTRY_OPTIONS||'{}')};
  console.log('PASS third entry, frame boundaries:',JSON.stringify(check(probe.run(o))));
}
module.exports={rotate,lowerMappings,mapping,check};
