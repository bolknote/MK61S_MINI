#!/usr/bin/env node
'use strict';
// Exact collision for two fresh keyboard runs; no snapshots are imported.
// ROLL destroys the E42/E43 distinction in T and both IK1306 R reserves.
const assert=require('node:assert/strict');
const {snapshot,differences,hash}=require('./k1-zq-header-collision.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const zeroCapture=require('./arbitrary-bank-pair-zero-capture.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {peek}=require('./k1-frame-boundary-probe.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const base={phaseOffset:2,p3:'777',values:['811','822','-9.8765432E23','4.44E12'],
  fullUpper:['9011','9022','9033','9044']};
const zero='000000000000',marker='0000F0000000';

function run(incoming) {
  const options={...base,incoming},c=cap.prepare(options);
  // Diagnostic calendar matches cap.run, before the fixed key body begins.
  fullMsPages(c);registers(c);program(c);aligned(c);
  const initial=snapshotFromRing(peek(c));
  assert.equal(new Set(initial.words).size,23,'each fixture needs 23 distinct bank words');
  zeroCapture.operation(c,options);
  const before=snapshot(c),beforeRing=peek(c);
  // No extra frames, alignment or state-dependent choices at this boundary.
  c.pressSequence(['F',',']).runFrames(8);
  const immediate=snapshot(c);
  c.runFrames(3);aligned(c);
  return {incoming,initial,before,beforeRing,immediate,after:snapshot(c),afterRing:peek(c)};
}

function check(a,b) {
  assert.deepEqual([a.incoming,b.incoming],['-1.2345678E42','-1.2345678E43']);
  assert.deepEqual(differences(a.initial.words,b.initial.words),
    [['0','042912345678','043912345678']],'only the original P0 bank word differs');
  assert.deepEqual(differences(a.initial.program,b.initial.program),[]);
  assert.deepEqual(differences(a.initial.services,b.initial.services),[]);
  const before=differences(a.before,b.before),immediate=differences(a.immediate,b.immediate);
  const after=differences(a.after,b.after);
  assert.deepEqual(before,[['ir2a.memory.154',2,3],['ik1306.r.27',2,3],['ik1306.r.28',2,3]]);
  assert.deepEqual(differences(a.beforeRing,b.beforeRing),[['T.28',2,3]]);
  assert.deepEqual(immediate,[],'complete validated states collide after the ROLL action');
  assert.deepEqual(after,[],'complete collision persists through three frames and final alignment');
  assert.deepEqual(differences(a.afterRing,b.afterRing),[]);
  for(const r of [a,b]) {
    const visible=ring=>['X','Y','Z','T'].map(n=>raw(ring[n]));
    const final=snapshotFromRing(r.afterRing),v=r.initial.words[16],u=r.initial.words[15];
    assert.deepEqual(visible(r.beforeRing),[zero,zero,marker,r.initial.words[0]]);
    assert.deepEqual(visible(r.afterRing),[zero,'25'+v[2]+'912345678',v,u]);
    assert.deepEqual(final.words,[v,...r.initial.words.slice(1)]);
    assert.deepEqual(final.program,r.initial.program);assert.deepEqual(final.services,r.initial.services);
    assert.equal(hash(r.after),'c6db8c777ffb6cc235be44195d2da4bf727c88fcc3217f4bee7b5e5292e8201d');
  }
  return {inputs:[a.incoming,b.incoming],beforeDifferences:before,
    immediateDifferences:immediate,finalDifferences:after,identicalCompleteFinalState:true,
    hashes:[hash(a.after),hash(b.after)],other22InputsIdentical:true,eachInput23Distinct:true,
    programAndServiceHeld:true,
    limitation:'One fixed ROLL continuation erases the E42/E43 distinction; not a general K1 impossibility.'};
}

if(require.main===module) {
  const a=run('-1.2345678E42'),b=run('-1.2345678E43');
  console.log('PASS zero-capture ROLL complete-machine collision',JSON.stringify(check(a,b),null,2));
}
module.exports={run,check};
