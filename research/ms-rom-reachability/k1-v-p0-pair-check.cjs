#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const pair=require('./k1-v-p0-pair.cjs');
const {analyzeTrace}=require('./k1-permutation-oracle.cjs');
const {compareUnobserved}=require('./k1-v-p0-pair-keyboard-check.cjs');
const cases=[{phaseOffset:2,verifyExit:true},
  {phaseOffset:2,verifyExit:true,incoming:'201',values:['811','822','833','-1.2345678E-42'],
    fullUpper:['9011','9022','9033','9044']}];
const expectedMapping=Array.from({length:23},(_,i)=>i===0?16:i===16?0:i);
function distinctPermutation(r) {
  const reports=[];
  for(const i of [0,1]) {
    const view=pair.cycleView(r,i),es=view.traced.events;
    const report=analyzeTrace({beforeEvent:es.find(e=>e.ring),afterEvent:es.find(e=>e.stage==='done'),
      writes:view.traced.writes,expectedMapping});
    assert.equal(report.status,'PERMUTATION_INSTANCE_ONLY');
    assert.equal(report.transientProtection.changes.length,0);
    reports.push({distinct:report.fixture.distinct,cycles:report.data.cycles,fixedMapping:report.fixedMapping.status});
  }
  return reports;
}
if(require.main===module) {
  const chosen=process.env.K1_PAIR_CASE===undefined?cases: [cases[Number(process.env.K1_PAIR_CASE)]];
  assert.ok(chosen.every(Boolean));
  for(const o of chosen) {
    const r=pair.runRoundTrip(o);console.log('PASS native inverse and exit:',JSON.stringify(pair.checkRoundTrip(r)));
    if(o.fullUpper)console.log('PASS 23 distinct words:',JSON.stringify(distinctPermutation(r)));
    const expected=JSON.parse(JSON.stringify(r.calc));r.traced.events.length=r.traced.writes.length=0;
    if(process.env.K1_PAIR_UNOBSERVED)console.log('PASS observer-free state:',compareUnobserved(expected,o,pair.roundTripFinish));
  }
  console.log('LIMIT: conditional V/P0 only; the other seven K1 pairs and universal numeric/timing entry remain unproved.');
}
module.exports={cases,expectedMapping,distinctPermutation};
