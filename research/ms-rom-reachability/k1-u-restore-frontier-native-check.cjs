#!/usr/bin/env node
'use strict';
// Fresh fixed-key native validation of the positive mH-to-Y restoration
// frontier. U is still NOT restored; V is now a backup of Ubad, not final p.
const assert=require('node:assert/strict');
const unpack=require('./u-restore-ready-unpack-route.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const model=require('./cache-bc-head93-numeric-all5-model.cjs');
const {snapshot,hash}=require('./k1-zq-header-collision.cjs');
const {peek}=require('./k1-frame-boundary-probe.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
function run(file){
  const r=unpack.run(file,'marker-to-Y',true),o=r.d.metadata.options;
  assert.equal(r.stopped,null);assert.equal(r.firstProtectedChange,null);
  const c=cap.prepare(o),plain=cap.prepare(o),before=snapshotFromRing(peek(c));
  assert.equal(new Set(before.words).size,23);assert.deepEqual(snapshot(c),snapshot(plain));
  const planned=new Map(r.stages.map(s=>[s.stage,s.start])),checkpoints=[];let proxy;
  proxy=new Proxy(c,{get(t,k){assert.ok(['pressSequence','runFrames'].includes(k),'private protocol read '+String(k));
    return(...args)=>{t[k](...args);return proxy;};},set(){throw Error('native assignment forbidden');}});
  unpack.operation(proxy,o,stage=>{
    if(!planned.has(stage))return;
    const expected=planned.get(stage),ring=peek(c),banks=snapshotFromRing(ring).words,
      visible=Object.fromEntries(['X','Y','Z','T','X1'].map(n=>[n,raw(ring[n])]));
    assert.deepEqual(banks,expected.banks,stage+'/all23');
    assert.deepEqual(visible,expected.visible,stage+'/visible');
    assert.equal(c.ir2a.tickIndex,expected.phase,stage+'/phase');
    checkpoints.push(stage);
  });
  unpack.operation(plain,o);assert.deepEqual(snapshot(c),snapshot(plain),'fresh full observer-free mirror');
  assert.equal(c.ir2a.tickIndex,r.core.phase);
  for(const name of model.names){const n=c[name],p=r.core.chips[name];
    assert.deepEqual(n.memory,p.m,name+'/all memory');
    for(const [a,b] of [['tickIndex','tick'],['input','input'],['output','output']])assert.equal(n[a],p[b],name+'/'+a);
    if(name.startsWith('ik')){
      assert.deepEqual(n.r,p.r,name+'/all R');assert.deepEqual(n.stack,p.st,name+'/all ST');
      for(const k of ['s','s1','l','t','carry','keyX','keyY'])assert.equal(n[k],p[k],name+'/'+k);
    }
  }
  const ring=peek(c),after=snapshotFromRing(ring),visible=Object.fromEntries(['X','Y','Z','T','X1'].map(n=>[n,raw(ring[n])])),
    carrier='0040F'+before.words[15].slice(1,3)+'00000',decoded='0'+visible.Y.slice(5,7)+visible.Z.slice(3);
  assert.deepEqual(after.program,before.program);assert.deepEqual(after.services,before.services);
  assert.deepEqual(after.words.slice(0,15),before.words.slice(0,15));
  assert.deepEqual(after.words.slice(19),before.words.slice(19));
  assert.equal(visible.X,before.words[16]);assert.equal(visible.Y,carrier);
  assert.equal(visible.Z,after.words[16],'full Ubad backup in V');assert.equal(decoded,before.words[15]);
  assert.equal(after.words[17],before.words[18]);assert.equal(after.words[18],before.words[17]);
  assert.ok(before.words.every(w=>[...after.words,...Object.values(visible),decoded].includes(w)));
  assert.deepEqual(r.end.markers,['marker','Y']);
  return{newRestorationSuffixWords:r.newSuffixWords,totalNewALL5Words:r.words,
    protectedEmittedCells:r.protectedEmittedCells,checkpoints:checkpoints.length,
    visible,banks:after.words,all23ExplicitInformationRetained:true,UPhysicallyRestored:false,
    nativeObserverFreeMirror:true,all5NativeEndpointMatched:true,programServicesHeld:true,
    sha256:hash(snapshot(c)),
    boundary:'native selected-domain mH-to-Y frontier only; U and V remain scratch, no clean exchange or full K1'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={run};
