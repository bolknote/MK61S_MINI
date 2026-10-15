#!/usr/bin/env node
'use strict';
// Independent negative-domain control. Stop at the FIXED prefix just before
// the first SWAP; the protocol neither reads these observations nor branches.
// Input evidence is an archived reader endpoint for plain detached ALL5 only.
const assert=require('node:assert/strict');
const path=require('node:path');
const high=require('./k1-u-header-high-carrier.cjs');
const {create}=require('./k1-writer-replay.cjs');
const reader=require('./k1-zero-uv-retained-reader.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const model=require('./cache-bc-head93-numeric-all5-model.cjs');
const {snapshot,hash}=require('./k1-zq-header-collision.cjs');
const {peek}=require('./k1-frame-boundary-probe.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');

const prefix=[...high.maker,...high.writer.slice(0,-1)];
function operation(c,o,record=()=>{}){
  reader.operation(c,o);
  for(const [stage,keys] of prefix){c.pressSequence(keys).runFrames(8);record(stage);}
}
function run(file=path.join(__dirname,'evidence/k1-zero-uv-reader-j3UTuh/native-proof.json')){
  const s=create(file);
  for(const a of prefix)s.advance(a,a[0]==='lastx-v');
  const r=s.result(),o=s.d.metadata.options,c=cap.prepare(o),plain=cap.prepare(o),rows=[];
  const before=snapshotFromRing(peek(c));
  assert.equal(new Set(before.words).size,23);
  let proxy;
  proxy=new Proxy(c,{get(t,k){assert.ok(['pressSequence','runFrames'].includes(k));
    return(...args)=>{t[k](...args);return proxy;};},set(){throw Error('private protocol mutation');}});
  operation(proxy,o,stage=>{
    const ring=peek(c),b=snapshotFromRing(ring);
    rows.push({stage,phase:c.ir2a.tickIndex,banks:b.words,
      visible:Object.fromEntries(['X','Y','Z','T','X1'].map(n=>[n,raw(ring[n])]))});
  });
  operation(plain,o);
  assert.deepEqual(snapshot(c),snapshot(plain),'fresh full observer-free mirror');
  for(const n of model.names){
    const a=c[n],b=s.core.chips[n];
    assert.deepEqual(a.memory,b.m,n+'/M');
    for(const [x,y] of [['tickIndex','tick'],['input','input'],['output','output']])assert.equal(a[x],b[y],n+'/'+x);
    if(n.startsWith('ik')){
      assert.deepEqual(a.r,b.r,n+'/R');assert.deepEqual(a.stack,b.st,n+'/ST');
      for(const k of ['s','s1','l','t','carry','keyX','keyY'])assert.equal(a[k],b[k],n+'/'+k);
    }
  }
  assert.equal(r.firstProtectedChange,null);
  const after=snapshotFromRing(peek(c));
  assert.deepEqual(after.program,before.program);assert.deepEqual(after.services,before.services);
  assert.deepEqual(after.words.slice(1,15),before.words.slice(1,15));
  assert.notDeepEqual(after.words.slice(15),before.words.slice(15),'negative domain control must change Ms before first SWAP');
  for(let i=0;i<rows.length;i++){
    assert.deepEqual(rows[i].banks,r.stages[i].end.banks,rows[i].stage+'/all23');
    assert.deepEqual(rows[i].visible,r.stages[i].end.visible,rows[i].stage+'/visible');
  }
  const firstMsChange=rows.find(x=>x.banks.slice(15).some((w,i)=>w!==before.words[i+15]));
  const firstUOverwrite=r.changes.find(x=>x.area==='Ms'&&x.owner==='U');
  assert.equal(firstUOverwrite.ip,'e7');
  assert.equal(firstUOverwrite.a,before.words[16],'late E7 writes old V into U');
  return{options:o,newALL5Words:r.words,protectedEmittedCells:r.protectedEmittedCells,
    firstMsChange,preFirstSwap:rows.at(-1),all5NativeEndpointMatched:true,nativeUnobservedMirror:true,
    firstUOverwrite,lastxVPrimaryPaths:r.paths.filter(x=>['9c','ee','e7','a8'].includes(x.ip)),
    programServicesHeld:true,sha256:hash(snapshot(c)),
    absentOriginalFullWords:r.absentOriginalsFromStoredWords,
    boundary:'negative long signed p/v domain control before first SWAP; not irreversible full-state loss or universal impossibility'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={run,operation,prefix};
