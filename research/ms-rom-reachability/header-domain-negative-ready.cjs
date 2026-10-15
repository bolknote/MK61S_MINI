#!/usr/bin/env node
'use strict';
// Selected negative-order U hypothesis: 9xx is an already-ready 9C control.
// Fixed public keys only; no reserve maker is needed if U is never clobbered.
const assert=require('node:assert/strict');
const {create}=require('./k1-writer-replay.cjs');
const old=require('./k1-uv-reader-reverse-writer-plan.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const model=require('./cache-bc-head93-numeric-all5-model.cjs');
const {snapshot,hash}=require('./k1-zq-header-collision.cjs');
const {peek}=require('./k1-frame-boundary-probe.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
function actions(stop='writer'){
  const n=old.writerTail.findIndex(a=>a[0]==='write-v');
  return[...old.recipes['payload-tail'],...old.writerTail.slice(0,stop==='exit'?undefined:n+1)];
}
function detached(file,stop='writer'){
  const s=create(file);for(const a of actions(stop))s.advance(a,true);
  const r=s.result();return{replay:s,...r};
}
function operation(c,o,record=()=>{}){
  require('./k1-zero-uv-retained-reader.cjs').operation(c,o,record);
  for(const [stage,keys,frames=8] of actions(o.stop)){record(stage);c.pressSequence(keys).runFrames(frames);}
}
function native(file,stop='writer'){
  const sim=detached(file,stop),s=sim.replay,o={...s.d.metadata.options,stop},c=cap.prepare(o),plain=cap.prepare(o);
  const before=snapshotFromRing(peek(c));let proxy;
  assert.equal(before.words[15][0],'9','selected negative-order U fixture required');
  proxy=new Proxy(c,{get(t,k){assert.ok(['pressSequence','runFrames'].includes(k),'private read '+String(k));
    return(...args)=>{t[k](...args);return proxy;};},set(){throw Error('native assignment forbidden');}});
  operation(proxy,o);operation(plain,o);assert.deepEqual(snapshot(c),snapshot(plain));
  assert.equal(c.ir2a.tickIndex,s.core.phase);
  for(const name of model.names){const n=c[name],p=s.core.chips[name];
    assert.deepEqual(n.memory,p.m,name+'/memory');
    for(const [a,b] of [['tickIndex','tick'],['input','input'],['output','output']])assert.equal(n[a],p[b],name+'/'+a);
    if(name.startsWith('ik')){
      assert.deepEqual(n.r,p.r,name+'/R');assert.deepEqual(n.stack,p.st,name+'/ST');
      for(const k of ['s','s1','l','t','carry','keyX','keyY'])assert.equal(n[k],p[k],name+'/'+k);
    }
  }
  const ring=peek(c),after=snapshotFromRing(ring),visible=Object.fromEntries(['X','Y','Z','T','X1'].map(n=>[n,raw(ring[n])]));
  assert.deepEqual(after.program,before.program);assert.deepEqual(after.services,before.services);
  assert.equal(sim.firstProtectedChange,null);
  const expected=before.words.slice();expected[16]=before.words[0];
  if(stop==='exit')expected[0]=before.words[16];
  assert.deepEqual(after.words,expected,'only selected P0/V exchange effects allowed');
  assert.ok(before.words.every(w=>[...after.words,...Object.values(visible)].includes(w)));
  if(stop==='exit')assert.deepEqual(sim.end.markers,['marker'],'canonical marker only after exit');
  return{stop,words:sim.words,protectedEmittedCells:sim.protectedEmittedCells,firstProtectedChange:sim.firstProtectedChange,
    bankChanges:sim.bankChanges,visible,all23FullWordsRepresented:before.words.every(w=>[...after.words,...Object.values(visible)].includes(w)),
    all5NativeEndpointMatched:true,observerFreeNativeMirror:true,sha256:hash(snapshot(c)),
    boundary:'selected negative-order hypothesis; only exact effects asserted, not full K1'};
}
if(require.main===module){
  const [mode,file,stop]=process.argv.slice(2);
  if(mode==='native')console.log(JSON.stringify(native(file,stop)));
  else {const r=detached(file,stop);delete r.replay;console.log(JSON.stringify({...r,
    stages:r.stages.map(x=>({stage:x.stage,start:x.start,end:x.end})),
    paths:r.paths.filter(p=>[0x9C,0xE9,0xA3].includes(parseInt(p.ip,16)))}));}
}
module.exports={actions,detached,operation,native};
