#!/usr/bin/env node
'use strict';
// Two independent fresh keyboard runs. No state import, cached resume, or
// changed emulator/ROM; compare every serializable native field.
const assert=require('node:assert/strict');
const probe=require('./k1-zq-origin-entry.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const {snapshot,differences,hash}=require('./k1-zq-header-collision.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {peek}=require('./k1-frame-boundary-probe.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');

function run(v) {
  const o={...probe.defaults,values:probe.defaults.values.slice()};o.values[2]=v;
  const c=cap.prepare(o),initial=fullMsPages(c);registers(c);program(c);aligned(c);
  probe.finish(c,o);
  const before=snapshot(c),beforeRing=peek(c);
  assert.equal(raw(beforeRing.T),initial.V.slice(2));
  c.runFrames(1);
  stack.act(c,()=>{},'swap',['↔']);
  const immediate=snapshot(c),immediateRing=peek(c);
  c.runFrames(3);
  return {v,initial,before,beforeRing,immediate,immediateRing,after:snapshot(c),afterRing:peek(c)};
}

function check(a,b) {
  assert.notEqual(a.initial.V,b.initial.V);
  assert.deepEqual(differences(a.initial,b.initial),[['V',a.initial.V,b.initial.V]]);
  const before=differences(a.before,b.before),beforeRing=differences(a.beforeRing,b.beforeRing);
  const immediate=differences(a.immediate,b.immediate),after=differences(a.after,b.after);
  assert.deepEqual(before,[['ir2a.memory.154',3,2],['ik1306.r.27',3,2],['ik1306.r.28',3,2]],
    'only the ring exponent tetra and its two cached copies differ');
  assert.deepEqual(beforeRing,[['T.28',3,2]]);
  assert.deepEqual(immediate,[],'complete native states coincide immediately after the phase-1 swap');
  assert.deepEqual(after,[],'complete native states remain equal after three frames');
  assert.equal(hash(a.after),hash(b.after));
  assert.equal(hash(a.after),'2a59030939777734dd71ab1a14115149308aa4971b4a52f5ec21ad5d7b37aed5');
  return {inputs:[a.v,b.v],beforeDifferences:before,beforeRingDifferences:beforeRing,
    immediateDifferences:immediate,afterDifferences:after,
    hashes:[hash(a.after),hash(b.after)],identicalCompleteFinalState:true,
    claim:'this exact phase-1 continuation cannot recover both v orders without a prior reserve',
    fullK1Impossibility:false};
}
if(require.main===module) {
  const a=run('-9.8765432E-17');console.log('FIRST complete',hash(a.after));
  const b=run('-9.8765432E-18');
  console.log('PASS full v-cache collision:',JSON.stringify(check(a,b),null,2));
}
module.exports={run,check};
