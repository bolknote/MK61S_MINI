#!/usr/bin/env node
'use strict';
// Native verification of the NEW writer preparation, not of a new reader.
// The established reader is just a fixed-key prefix. No fixture U/order is
// consulted by the protocol; the log/integer prototype is deliberately narrow.
const assert=require('node:assert/strict');
const plan=require('./k1-u-header-marker-plan.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const uv=require('./k1-zero-uv-retained-reader.cjs');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
const {snapshot,hash}=require('./k1-zq-header-collision.cjs');
const {peek}=require('./k1-frame-boundary-probe.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const stop='marker-exponent',actions=plan.actions.slice(0,plan.actions.findIndex(a=>a[0]===stop)+1);
function operation(c,o,record=()=>{}){
  uv.operation(c,o,record);
  for(const [stage,keys] of actions){record(stage);c.pressSequence(keys).runFrames(8);}
}
function run(file){
  const expected=plan.run(file,{stop,includeCore:true}),o=expected.d.metadata.options,
    c=cap.prepare(o),plain=cap.prepare(o),original=snapshotFromRing(peek(c));
  assert.deepEqual(snapshot(c),snapshot(plain));assert.equal(new Set(original.words).size,23);
  let proxy;
  proxy=new Proxy(c,{get(target,k){
    assert.ok(['pressSequence','runFrames'].includes(k),'private protocol read '+String(k));
    return(...args)=>{target[k](...args);return proxy;};
  },set(){throw Error('protocol mutation forbidden');}});
  const checkpoints=[];
  operation(proxy,o,stage=>{
    if(['marker-fraction','marker-exponent'].includes(stage)){
      const ring=peek(c);checkpoints.push({stage,
        visible:Object.fromEntries(['X','Y','Z','T','X1'].map(w=>[w,raw(ring[w])]))});
    }
  });
  operation(plain,o);
  assert.deepEqual(snapshot(c),snapshot(plain),'complete native observer-free mirror');
  assert.equal(c.ir2a.tickIndex,expected.core.phase);
  for(const name of m.names){
    const native=c[name],model=expected.core.chips[name];
    assert.deepEqual(native.memory,model.m,name+'/all native memory');
    for(const [a,b] of [['tickIndex','tick'],['input','input'],['output','output']])assert.equal(native[a],model[b],name+'/'+a);
    if(name.startsWith('ik')){
      assert.deepEqual(native.r,model.r,name+'/all R');assert.deepEqual(native.stack,model.st,name+'/all ST');
      for(const k of ['s','s1','l','t','carry','keyX','keyY'])assert.equal(native[k],model[k],name+'/'+k);
    }
  }
  const ring=peek(c),after=snapshotFromRing(ring),visible=Object.fromEntries(['X','Y','Z','T','X1'].map(w=>[w,raw(ring[w])])),
    stored=[...after.words,...Object.values(visible)];
  assert.ok(original.words.every(w=>stored.includes(w)),'all 23 original full words remain represented');
  assert.deepEqual(after.words.slice(1),original.words.slice(1),'other 22 bank words held');
  assert.deepEqual(after.program,original.program);assert.deepEqual(after.services,original.services);
  assert.equal(visible.X,expected.expected,'selected positive U order encoded in the marker');
  assert.equal(visible.Y,original.words[0]);assert.equal(visible.Z,original.words[16]);
  assert.equal(visible.T,'9990'+visible.X.slice(4),'fraction formatter creates the additional T marker');
  assert.equal(expected.firstProtectedChange,null);
  assert.equal(expected.firstOtherBankChange,null,'other 22 bank cells held during the complete new preparation');
  return{options:o,newWriterPreparationALL5Words:expected.words,protectedEmittedCells:expected.protectedEmittedCells,checkpoints,visible,
    all23OriginalWordsStillStored:true,other22BanksHeld:true,programServicesHeld:true,
    entireFiveChipEndpointMatched:true,nativeUnobservedMirror:true,sha256:hash(snapshot(c)),
    boundary:'selected positive-order automatic reserve; extra T marker blocks old writer entry; no reverse Ms write or universal exponent extraction'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={operation,run,actions};
