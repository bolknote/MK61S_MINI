#!/usr/bin/env node
'use strict';
// Frame-boundary assessment, not a transient-write/full-state proof.
const assert=require('node:assert/strict');
const probe=require('./k1-vw-nop-restored-repeat.cjs');
const {snapshotFromRing,PLACES}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const mapping=Array.from({length:23},(_,i)=>i);
mapping[0]=17;mapping[16]=18;mapping[17]=16;mapping[18]=0;
function check(r) {
  const initial=snapshotFromRing(r.initial),original=initial.words;
  assert.equal(new Set(original).size,23,'all original stored words distinct');
  let expected=original;
  const rounds=[];
  for(let i=0;i<2;i++) {
    expected=mapping.map(n=>expected[n]);
    const row=r.rows.find(x=>x.stage==='repeat/'+i+'/end');
    if(!row){rounds.push({round:i+1,completed:false});continue;}
    const snap=snapshotFromRing(row.ring);
    rounds.push({round:i+1,completed:true,phase:row.phase,
      expectedMappingMatches:equal(snap.words,expected),
      mappingMismatches:snap.words.flatMap((value,n)=>value===expected[n]?[]:
        [{place:PLACES[n],expected:expected[n],actual:value}]),
      all23Stored:original.every(x=>snap.words.includes(x)),
      extraMarkers:Object.keys(row.ring).filter(n=>n!=='marker'&&row.ring[n][22]===15),
      realMarker:raw(row.ring.marker),values:row.values,registers:row.registers});
  }
  const firstIndex=r.rows.findIndex(x=>x.missing.length);
  let firstLoss=null;
  if(firstIndex>=0) {
    const row=r.rows[firstIndex],previous=r.rows[firstIndex-1];
    firstLoss={boundary:row.stage,phase:row.phase,missing:row.missing,
      origins:row.missing.map(word=>({word,places:PLACES.filter((_,i)=>original[i]===word)})),
      previousBoundary:previous?.stage,
      // Labels are taken before keyboard actions, so the interval begins
      // with previousBoundary and ends at boundary; no exact ROM writer
      // is inferred from these frame observations.
      previousValues:previous?.values,values:row.values,
      changedTetras:previous?Object.entries(previous.ring).flatMap(([slot,arr])=>
        arr.flatMap((v,nibble)=>v===row.ring[slot][nibble]?[]:
          [{slot,nibble,before:v,after:row.ring[slot][nibble]}])):null};
  }
  const fieldDamage=r.rows.flatMap(row=>{
    const snap=snapshotFromRing(row.ring);
    return equal(initial.program,snap.program)&&equal(initial.services,snap.services)?[]:
      [{boundary:row.stage,programHeld:equal(initial.program,snap.program),
        servicesHeld:equal(initial.services,snap.services)}];
  });
  const success=!r.failure&&!firstLoss&&fieldDamage.length===0&&
    rounds.every(x=>x.completed&&x.expectedMappingMatches&&x.all23Stored&&
      x.extraMarkers.length===0&&x.realMarker==='000FFFFFFFFF');
  return {status:success?'TWO_CONTINUOUS_INSTANCES_AT_FRAME_BOUNDARIES':'CONTINUOUS_REPETITION_NOT_ESTABLISHED',
    failure:r.failure,boundaries:r.rows.length,rounds,firstLoss,fieldDamage,
    all23HeldAtObservedBoundaries:!firstLoss,
    noResetOrExtraWaitBetweenInvocations:true,manualProgramDemosBetweenInvocations:false,
    transientWritesChecked:false,wholeNumericDomainProved:false,fullK1:false};
}
if(require.main===module) {
  const o=JSON.parse(process.env.K1_RESTORED_REPEAT_OPTIONS||'{}');
  console.log(JSON.stringify(check(probe.run(o)),null,2));
}
module.exports={check,mapping};
