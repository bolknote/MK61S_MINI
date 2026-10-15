#!/usr/bin/env node
'use strict';
// Fresh public-key native runs and an observer-free mirror. A decoded U header
// is a DIAGNOSTIC ONLY, never a repair of a calculator or model state.
const assert=require('node:assert/strict');
const high=require('./k1-u-header-high-carrier.cjs');
const ready=require('./k1-high-carrier-ready-retry.cjs');
const {create}=require('./k1-writer-replay.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const model=require('./cache-bc-head93-numeric-all5-model.cjs');
const {snapshot,hash}=require('./k1-zq-header-collision.cjs');
const {peek}=require('./k1-frame-boundary-probe.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
function run(file,mode='ready'){
  assert.ok(['maker','ready'].includes(mode));
  const s=create(file);
  for(const a of high.maker)s.advance(a,false);
  if(mode==='ready')for(const a of [...high.writer,...ready.retry])s.advance(a,true);
  const simulated=s.result(),o={...s.d.metadata.options,stop:mode==='maker'?'maker':'writer'},
    body=mode==='maker'?high:ready,c=cap.prepare(o),plain=cap.prepare(o),original=snapshotFromRing(peek(c));
  assert.deepEqual(snapshot(c),snapshot(plain));assert.equal(new Set(original.words).size,23);
  const checkpoints=[];let proxy;
  proxy=new Proxy(c,{get(target,k){assert.ok(['pressSequence','runFrames'].includes(k),'private protocol read '+String(k));
    return(...args)=>{target[k](...args);return proxy;};},set(){throw Error('native protocol mutation forbidden');}});
  body.operation(proxy,o,stage=>{
    if(['save-carrier','write-v','write-v-ready'].includes(stage)){
      const ring=peek(c),b=snapshotFromRing(ring);
      if(stage==='save-carrier'){
        assert.equal(raw(ring.T),original.words[16],'short carrier does not create a T marker');
        assert.ok(original.words.every(w=>[...b.words,...['X','Y','Z','T','X1'].map(n=>raw(ring[n]))].includes(w)));
      }
      if(stage==='write-v')assert.deepEqual(b.words,original.words,'all 23 banks original before first writer');
      checkpoints.push({stage,phase:c.ir2a.tickIndex,visible:Object.fromEntries(['X','Y','Z','T','X1'].map(n=>[n,raw(ring[n])]))});
    }
  });
  body.operation(plain,o);
  assert.deepEqual(snapshot(c),snapshot(plain),'complete native observed/unobserved mirror');
  assert.equal(c.ir2a.tickIndex,s.core.phase);
  for(const name of model.names){const n=c[name],p=s.core.chips[name];
    assert.deepEqual(n.memory,p.m,name+'/all memory');
    for(const [a,b] of [['tickIndex','tick'],['input','input'],['output','output']])assert.equal(n[a],p[b],name+'/'+a);
    if(name.startsWith('ik')){
      assert.deepEqual(n.r,p.r,name+'/all R');assert.deepEqual(n.stack,p.st,name+'/all ST');
      for(const k of ['s','s1','l','t','carry','keyX','keyY'])assert.equal(n[k],p[k],name+'/'+k);
    }
  }
  const ring=peek(c),after=snapshotFromRing(ring),visible=Object.fromEntries(['X','Y','Z','T','X1'].map(n=>[n,raw(ring[n])])),
    expectedCarrier='0040F'+original.words[15].slice(1,3)+'00000';
  assert.equal(simulated.firstProtectedChange,null);
  assert.deepEqual(after.program,original.program);assert.deepEqual(after.services,original.services);
  assert.deepEqual(after.words.slice(1,15),original.words.slice(1,15));
  let reconstructedU=null;
  if(mode==='maker'){
    assert.equal(visible.X,expectedCarrier);assert.equal(visible.Y,original.words[0]);assert.equal(visible.Z,original.words[16]);
    assert.equal(visible.T,original.words[16]);assert.deepEqual(after.words.slice(1),original.words.slice(1));
  }else{
    assert.equal(visible.T,expectedCarrier);assert.equal(after.words[0],original.words[0]);
    assert.equal(after.words[16],original.words[0],'actual original P0 is now in Ms V');
    assert.equal(visible.Z,original.words[16],'old V is retained');
    assert.equal(after.words[17],original.words[18]);assert.equal(after.words[18],original.words[17]);
    assert.deepEqual(after.words.slice(19),original.words.slice(19));
    reconstructedU='0'+visible.T.slice(5,7)+after.words[15].slice(3);
    assert.equal(reconstructedU,original.words[15],'original U information survives in explicit carrier+U fields');
  }
  const stored=[...after.words,...Object.values(visible)],decoded=stored.concat(reconstructedU??[]);
  assert.ok(original.words.every(w=>decoded.includes(w)));
  return{mode,options:o,newALL5Words:simulated.words,protectedEmittedCells:simulated.protectedEmittedCells,checkpoints,visible,
    actualOriginalP0InMsV:mode==='ready',all23OriginalsRepresented:original.words.every(w=>decoded.includes(w)),
    UAlreadyRestored:after.words[15]===original.words[15],UReconstructibleFromExplicitReserve:reconstructedU!==null,
    originalFullWordsAbsentFromBanksAndStack:original.words.filter(w=>!stored.includes(w)),
    programServicesHeld:true,all5NativeEndpointMatched:true,nativeUnobservedMirror:true,sha256:hash(snapshot(c)),
    boundary:'selected-domain native reverse V write with an explicit U-order reserve and W/Q permutation; not restored U, clean exit, or full K1'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2],process.argv[3])));
module.exports={run};
