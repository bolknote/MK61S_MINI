#!/usr/bin/env node
'use strict';
// Boundary diagnostic. Exact native write audits are kept separate.
const assert=require('node:assert/strict');
const probe=require('./k1-stack-close-repeat.cjs');
const {snapshotFromRing,PLACES}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const mapping=Array.from({length:23},(_,i)=>i);
for(const [dst,src] of [[0,17],[16,18],[17,0],[18,19],[19,20],[20,16]])mapping[dst]=src;
function check(r) {
  const initial=snapshotFromRing(r.initial),original=initial.words;
  assert.equal(new Set(original).size,23);
  const rounds=[];let expected=original;
  for(let i=0;i<r.options.rounds;i++) {
    expected=mapping.map(n=>expected[n]);
    const entry=r.rows.find(x=>x.stage==='repeat/'+i+'/start');
    const end=r.rows.find(x=>x.stage==='repeat/'+i+'/end');
    if(!end){rounds.push({round:i+1,completed:false,startPhase:entry?.phase});continue;}
    const snap=snapshotFromRing(end.ring);
    rounds.push({round:i+1,completed:true,startPhase:entry.phase,endPhase:end.phase,
      expectedMappingMatches:equal(snap.words,expected),
      mappingMismatches:snap.words.flatMap((value,n)=>value===expected[n]?[]:
        [{place:PLACES[n],expected:expected[n],actual:value}]),
      all23Stored:original.every(x=>snap.words.includes(x)),
      extraMarkers:Object.keys(end.ring).filter(n=>n!=='marker'&&end.ring[n][22]===15),
      realMarker:raw(end.ring.marker),values:end.values});
  }
  const lossIndex=r.rows.findIndex(x=>x.missing.length);
  const lost=lossIndex<0?null:r.rows[lossIndex],previous=lossIndex>0?r.rows[lossIndex-1]:null;
  const firstLoss=lost?{boundary:lost.stage,phase:lost.phase,missing:lost.missing,
    origins:lost.missing.map(word=>({word,places:PLACES.filter((_,i)=>original[i]===word)})),
    previousBoundary:previous?.stage,previousValues:previous?.values,values:lost.values}:null;
  const damage=r.rows.flatMap(row=>{
    const s=snapshotFromRing(row.ring);
    return equal(initial.program,s.program)&&equal(initial.services,s.services)?[]:
      [{boundary:row.stage,programHeld:equal(initial.program,s.program),servicesHeld:equal(initial.services,s.services)}];
  });
  return {status:!r.failure&&!firstLoss&&!damage.length&&rounds.every(x=>x.completed&&
    x.expectedMappingMatches&&x.all23Stored&&!x.extraMarkers.length&&x.realMarker==='000FFFFFFFFF')?
    'CONTINUOUS_INSTANCES_AT_FRAME_BOUNDARIES':'CONTINUOUS_REPETITION_NOT_ESTABLISHED',
    failure:r.failure,boundaries:r.rows.length,betweenFrames:r.options.betweenFrames,
    rounds,firstLoss,fieldDamage:damage,transientWritesChecked:false,
    noResetOrStateImport:true,wholeNumericDomainProved:false,fullK1:false};
}
function regression(r) {
  const result=check(r);assert.equal(r.options.rounds,2);assert.equal(r.failure,null);
  assert.deepEqual(result.fieldDamage,[]);
  assert.equal(result.rounds[0].expectedMappingMatches,true);assert.equal(result.rounds[0].all23Stored,true);
  assert.deepEqual(result.rounds[0].extraMarkers,[]);
  assert.equal(result.status,'CONTINUOUS_REPETITION_NOT_ESTABLISHED');
  const direct=r.options.betweenFrames===0;
  if(!direct)assert.equal(r.options.betweenFrames,1);
  if(r.options.longGuardBeforeRepeatRotate)assert.equal(direct,false);
  const origin=direct?'V':r.options.longGuardBeforeRepeatRotate?'W':'Q';
  assert.deepEqual(result.firstLoss.missing,[r.before[origin].slice(2)]);
  assert.equal(result.firstLoss.previousBoundary,'repeat/1/entry/'+(direct?'after-0':'tail-0'));
  assert.equal(result.firstLoss.boundary,'repeat/1/entry/'+(direct?'after-1':'tail-1'));
  assert.equal(result.rounds[1].expectedMappingMatches,false);
  return result;
}
if(require.main===module) {
  const r=probe.run(JSON.parse(process.env.K1_STACK_REPEAT_OPTIONS||'{}'));
  console.log(JSON.stringify((process.env.K1_STACK_REPEAT_REGRESSION?regression:check)(r),null,2));
}
module.exports={mapping,check,regression};
