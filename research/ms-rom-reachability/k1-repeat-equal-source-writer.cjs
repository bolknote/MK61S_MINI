#!/usr/bin/env node
'use strict';
// A NEW native writer test: repeat SWAP before removing the T marker while
// X=Y=p. Older rejected repeated-SWAP tests had X!=Y and lost the late source.
// This test does NOT assume a U-header reserve or call this a complete K1.
const assert=require('node:assert/strict');
const pair=require('./k1-v-p0-pair.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshot,hash}=require('./k1-zq-header-collision.cjs');
const {peek}=require('./k1-frame-boundary-probe.cjs');
const {MS_SLOTS,snapshotFromRing}=require('./k1-permutation-oracle.cjs');
function finish(c,o={},record=()=>{}){
  pair.finish(c,o,stage=>{
    if(stage==='drop-marker'){
      record('write-v-second');c.pressSequence(['↔']).runFrames(8);
    }
    record(stage);
  });
}
function run(u='4.44E12'){
  const options={phaseOffset:2,incoming:'201',p3:'777',
    values:['811','822','833',u],fullUpper:['9011','9022','9033','9044']};
  const c=cap.prepare(options),plain=cap.prepare(options),beforeRing=peek(c);
  const protectedBefore=snapshotFromRing(beforeRing);
  assert.deepEqual(snapshot(c),snapshot(plain));
  const initial=Object.fromEntries(MS_SLOTS.map(w=>[w,raw(beforeRing[w])])),
    initialRegisters=['U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T'].map(w=>raw(beforeRing[w],0));
  assert.equal(new Set([...initialRegisters,...Object.values(initial)]).size,23);
  const checkpoints=[];
  finish(c,options,stage=>{
    if(['write-v','write-v-second','drop-marker'].includes(stage)){
      const ring=peek(c);checkpoints.push({stage,
        visible:Object.fromEntries(['X','Y','Z','T','X1'].map(w=>[w,raw(ring[w])])),
        Ms:Object.fromEntries(MS_SLOTS.map(w=>[w,raw(ring[w])])),
        stateHash:hash(snapshot(c))});
    }
  });
  finish(plain,options);
  assert.deepEqual(snapshot(c),snapshot(plain),'entire observer-free native mirror');
  const endRing=peek(c),after=Object.fromEntries(MS_SLOTS.map(w=>[w,raw(endRing[w])])),
    registers=['U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T'].map(w=>raw(endRing[w],0));
  const protectedAfter=snapshotFromRing(endRing);
  assert.deepEqual(protectedAfter.program,protectedBefore.program);
  assert.deepEqual(protectedAfter.services,protectedBefore.services);
  assert.deepEqual(registers.slice(1),initialRegisters.slice(1));
  return{u,initial,initialRegisters,checkpoints,after,
    MsChanges:MS_SLOTS.flatMap(w=>after[w]===initial[w]?[]:[{word:w,before:initial[w],after:after[w]}]),
    registerChanges:registers.flatMap((w,i)=>w===initialRegisters[i]?[]:[{index:i,before:initialRegisters[i],after:w}]),
    MsVHasOldP0:after.V===initialRegisters[0],nativeUnobservedMirror:true,programServicesHeld:true,
    boundary:'fixed repeated writer with X=Y=p; header repair and all-23-word restoration are not assumed'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={finish,run};
