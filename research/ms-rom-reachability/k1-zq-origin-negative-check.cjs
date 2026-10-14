#!/usr/bin/env node
'use strict';
// Whole fresh keyboard prefixes, but frame evidence only for these failures.
// Absence from complete numeric words is not whole-machine irreversibility.
const assert=require('node:assert/strict');
const probe=require('./k1-zq-origin-entry.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
function check(r,kind) {
  const initial=snapshotFromRing(r.initial),source=kind==='swap'?'Q':'P8',lost=r.before[source].slice(2);
  assert.equal(new Set(initial.words).size,23);
  const losses=[];
  for(const row of r.rows) {
    const s=snapshotFromRing(row.ring),live=[...s.words,...Object.values(row.values)];
    const missing=initial.words.filter(x=>!live.includes(x));
    if(missing.length)losses.push([row.stage,missing]);
    assert.deepEqual(s.words.slice(1,15),initial.words.slice(1,15));
    assert.deepEqual(s.program,initial.program);assert.deepEqual(s.services,initial.services);
  }
  assert.deepEqual(losses,[['immediate',[lost]],['done',[lost]]]);
  for(const e of r.rows.filter(x=>['immediate','done'].includes(x.stage))) {
    assert.equal(e.values.marker,r.before.P10.slice(2));
    if(kind==='swap')assert.equal(e.values.P7,'14'+r.before.P8.slice(4,5)+lost.slice(3));
    else assert.equal(e.values.P9,r.beforeRegisters[0]);
  }
  return {kind,lostSource:source,lost,displacedP10StillPresent:true,frameEvidenceOnly:true,
    wholeMachineImpossibility:false};
}
if(require.main===module) {
  const which=process.env.K1_ZQ_NEGATIVE;
  if(!which||which==='swap')console.log('PASS direct swap loses q:',JSON.stringify(check(probe.run({
    afterW:[...probe.defaults.afterW,['↔']],afterWPhases:[0,0,0]}),'swap')));
  if(!which||which==='long')console.log('PASS long p loses b:',JSON.stringify(check(probe.run({
    incoming:'1.2345678E42'}),'long')));
}
module.exports={check};
