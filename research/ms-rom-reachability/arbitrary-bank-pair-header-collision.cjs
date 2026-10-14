#!/usr/bin/env node
'use strict';
// Fresh native public-key runs only. Complete snapshots are read-only evidence;
// no snapshot is imported into a calculator. This disqualifies post-hoc repair
// of the existing conditional pair body, not all original-ROM K1 routes.
const assert=require('node:assert/strict');
const pair=require('./k1-v-p0-pair.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {snapshot,differences,hash}=require('./k1-zq-header-collision.cjs');

function run(u) {
  const options={phaseOffset:2,incoming:'201',p3:'777',
    values:['811','822','833',u],fullUpper:['9011','9022','9033','9044']};
  const c=cap.prepare(options),initial=fullMsPages(c),m1=registers(c),code=program(c);
  const words=[...m1,...Object.values(initial).map(w=>w.slice(2))];
  assert.equal(new Set(words).size,23,'all incoming bank words are independent and distinct');
  aligned(c);
  const checkpoints=[];
  pair.finish(c,options,stage=>checkpoints.push({stage,state:snapshot(c)}));
  checkpoints.push({stage:'immediate-end',state:snapshot(c)});
  c.runFrames(3);
  const after=snapshot(c);
  return {u,initial,m1,code,checkpoints,after};
}

function check(a,b) {
  assert.deepEqual(differences(a.initial,b.initial),[['U',a.initial.U,b.initial.U]],
    'only the intended incoming U differs');
  assert.deepEqual(a.m1,b.m1);assert.deepEqual(a.code,b.code);
  assert.notEqual(a.initial.U,b.initial.U);
  assert.deepEqual(a.checkpoints.map(v=>v.stage),b.checkpoints.map(v=>v.stage));
  const stages=a.checkpoints.map((v,i)=>({stage:v.stage,
    differences:differences(v.state,b.checkpoints[i].state)}));
  const writer=stages.find(v=>v.stage==='write-v');
  assert.ok(writer.differences.length,'original U is still distinguishable before write-v');
  const end=stages.find(v=>v.stage==='immediate-end');
  assert.deepEqual(end.differences,[],'complete states collide before the diagnostic wait');
  assert.deepEqual(differences(a.after,b.after),[],'complete collision survives three ordinary frames');
  return {inputs:[a.u,b.u],incomingU:[a.initial.U,b.initial.U],distinctIncomingWords:23,
    beforeWriteDifferences:writer.differences,
    firstIndistinguishableAction:stages.findIndex(v=>v.differences.length===0),
    firstIndistinguishableStage:stages.find(v=>v.differences.length===0)?.stage,
    immediatelyAfterWrite:stages[stages.findIndex(v=>v.stage==='write-v')+1],
    completeFinalStatesEqual:true,sha256:[hash(a.after),hash(b.after)],
    implication:'No deterministic key-only continuation from this completed body can restore arbitrary original U.',
    boundary:'This is a collision for the existing conditional pair body, not a whole-ROM K1 impossibility theorem.'};
}

if(require.main===module) {
  const a=run('4.44E12'),b=run('4.44E22');
  console.log('PASS native conditional-pair header collision:',JSON.stringify(check(a,b),null,2));
}
module.exports={run,check};
