#!/usr/bin/env node
'use strict';
// A separate, fixed-key header factory hypothesis. +100 before K7 avoids
// truncating a negative logarithm toward zero. The 1.9 OR mask deliberately
// packs h modulo 100, NOT the full signed exponent; it is not universal U
// restoration. Both shifted and negative-floor variants demonstrably fail
// U=9.9999999E-12: F89 instead of F88. The zero native control gives F00;
// that observed outcome is not a mathematical lg(0) argument.
const assert=require('node:assert/strict');
const high=require('./k1-u-header-high-carrier.cjs');
const {create}=require('./k1-writer-replay.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const {snapshot,hash}=require('./k1-zq-header-collision.cjs');
const {peek}=require('./k1-frame-boundary-probe.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const source=high.maker.slice(0,5);
const suffix=high.maker.slice(high.maker.findIndex(a=>a[0]==='scale-constant'))
  .map(([s,k])=>[s,s==='mask-constant'?['1',',','9']:k]);
const actions=[...source,['drop-zero-early',['+']],['abs-u',['K','4']],['lg-u',['F','2']],
  ['positive-offset',[...'100']],['offset-log',['+']],['floor-offset',['K','7']],
  ['remove-offset',[...'100']],['signed-order',['-']],...suffix];
// For a fixed negative-logarithm domain, floor(z)=trunc(z)+sign(frac(z)).
// This removes the +100 addition, but the native upper-boundary control still
// fails because lg itself can already have rounded away its fraction.
// It is deliberately a different FIXED body, not a fixture-dependent branch.
const negativeActions=[...source,['drop-zero-early',['+']],['abs-u',['K','4']],['lg-u',['F','2']],
  ['copy-log',['В↑']],['truncate-log',['K','7']],['restore-log',['↔']],
  ['log-fraction',['K','8']],['fraction-sign',['K','5']],['negative-floor',['+']],...suffix];
const wrapActions=high.maker.map(([s,k])=>[s,s==='mask-constant'?['1',',','9']:k]);
const choose=factory=>factory==='negative'?negativeActions:factory==='wrap'?wrapActions:actions;
function operation(c,o,record=()=>{}){
  require('./k1-zero-uv-retained-reader.cjs').operation(c,o,record);
  for(const [stage,keys] of choose(o.factory)){record(stage);c.pressSequence(keys).runFrames(8);}
}
function detached(file,factory='shifted'){
  const s=create(file);for(const a of choose(factory))s.advance(a,false);
  const r=s.result();assert.equal(r.firstProtectedChange,null);
  assert.deepEqual(r.end.banks.slice(1),s.d.metadata.originalWords.slice(1));
  assert.equal(r.end.visible.Y,s.d.metadata.originalWords[0]);
  assert.equal(r.end.visible.Z,s.d.metadata.originalWords[16]);
  assert.equal(r.end.visible.T,s.d.metadata.originalWords[16]);
  return{words:r.words,end:r.end,expected:'0040F'+s.d.metadata.originalWords[15].slice(1,3)+'00000',
    protectedEmittedCells:r.protectedEmittedCells,all23BanksExceptScratchP0Held:true};
}
function detachedReady(file,factory='wrap'){
  const s=create(file);for(const a of choose(factory))s.advance(a,false);
  for(const a of [...high.writer,...require('./k1-high-carrier-ready-retry.cjs').retry])s.advance(a,true);
  const r=s.result();return{factory,words:r.words,protectedEmittedCells:r.protectedEmittedCells,
    firstProtectedChange:r.firstProtectedChange,end:r.end,bankChanges:r.bankChanges,
    absentOriginalsFromStoredWords:r.absentOriginalsFromStoredWords,
    boundary:'detached hypothesis only; wrong reserved digits on negative U can be harmless only while full U itself remains untouched'};
}
const base={phaseOffset:2,incoming:'201',p3:'777',values:['811','822','833','4.44E12'],fullUpper:['9011','9022','9033','9044']};
function native(value,factory='shifted'){
  const o={...base,factory,values:['811','822','833',value]},c=cap.prepare(o),plain=cap.prepare(o),before=snapshotFromRing(peek(c));
  let proxy;proxy=new Proxy(c,{get(t,k){assert.ok(['pressSequence','runFrames'].includes(k),'private read '+String(k));
    return(...args)=>{t[k](...args);return proxy;};},set(){throw Error('native assignment forbidden');}});
  operation(proxy,o);operation(plain,o);assert.deepEqual(snapshot(c),snapshot(plain));
  const ring=peek(c),after=snapshotFromRing(ring),visible=Object.fromEntries(['X','Y','Z','T','X1'].map(n=>[n,raw(ring[n])]));
  assert.deepEqual(after.program,before.program);assert.deepEqual(after.services,before.services);
  assert.deepEqual(after.words.slice(1),before.words.slice(1));
  assert.equal(visible.Y,before.words[0]);assert.equal(visible.Z,before.words[16]);assert.equal(visible.T,before.words[16]);
  const stored=[...after.words,...Object.values(visible)];
  assert.ok(before.words.every(w=>stored.includes(w)),'all 23 original words represented');
  const expected='0040F'+before.words[15].slice(1,3)+'00000';
  return{value,factory,originalU:before.words[15],expected,headerDigitsCorrect:visible.X===expected,
    visible,all23OriginalWordsRepresented:true,programmeServicesHeld:true,
    nativeObserverFreeMirror:true,sha256:hash(snapshot(c)),
    boundary:'maker only; h modulo 100 loses exponent sign unless another retained source distinguishes it; zero is outside lg domain'};
}
if(require.main===module){
  if(process.argv[2]==='detached')console.log(JSON.stringify(detached(process.argv[3],process.argv[4])));
  else if(process.argv[2]==='ready')console.log(JSON.stringify(detachedReady(process.argv[3],process.argv[4])));
  else if(process.argv[2]==='negative')for(const v of process.argv.slice(3))console.log(JSON.stringify(native(v,'negative')));
  else if(process.argv[2]==='wrap')for(const v of process.argv.slice(3))console.log(JSON.stringify(native(v,'wrap')));
  else for(const v of process.argv.slice(2))console.log(JSON.stringify(native(v)));
}
module.exports={actions,negativeActions,wrapActions,operation,detached,detachedReady,native};
