#!/usr/bin/env node
'use strict';
// Additional fresh, independent 23-word native fixtures, fixed keyboard body.
// One ALL5-checked baseline lives in k1-high-carrier-native-check.cjs; this
// corpus claims native mirrors, not ALL5 recalculation for every fixture.
const assert=require('node:assert/strict');
const high=require('./k1-u-header-high-carrier.cjs'),ready=require('./k1-high-carrier-ready-retry.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const {snapshot,hash}=require('./k1-zq-header-collision.cjs');
const {peek}=require('./k1-frame-boundary-probe.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const base={phaseOffset:2,incoming:'201',p3:'777',values:['811','822','833','4.44E12'],fullUpper:['9011','9022','9033','9044']};
function runCase(overrides={},mode='ready',expectHeader=true){
  assert.ok(['maker','ready'].includes(mode),'known test mode');
  const o={...base,...overrides,stop:mode==='maker'?'maker':'writer'},body=mode==='maker'?high:ready,
    c=cap.prepare(o),plain=cap.prepare(o),before=snapshotFromRing(peek(c));
  assert.equal(new Set(before.words).size,23);assert.deepEqual(snapshot(c),snapshot(plain));
  let proxy,packed=null;
  proxy=new Proxy(c,{get(t,k){assert.ok(['pressSequence','runFrames'].includes(k),'private read '+String(k));
    return(...args)=>{t[k](...args);return proxy;};},set(){throw Error('native state mutation forbidden');}});
  body.operation(proxy,o,stage=>{
    if(stage==='save-carrier'){
      const ring=peek(c);packed=raw(ring.X);
      assert.equal(raw(ring.T),before.words[16],'no fraction T duplicate');
    }
    if(stage==='write-v')assert.deepEqual(snapshotFromRing(peek(c)).words,before.words,'all23 banks held before first write');
  });
  body.operation(plain,o);assert.deepEqual(snapshot(c),snapshot(plain),'complete fresh observer-free mirror');
  const ring=peek(c),after=snapshotFromRing(ring),v=Object.fromEntries(['X','Y','Z','T','X1'].map(n=>[n,raw(ring[n])])),
    expected='0040F'+before.words[15].slice(1,3)+'00000',actual=mode==='maker'?v.X:packed;
  assert.deepEqual(after.program,before.program);assert.deepEqual(after.services,before.services);
  assert.deepEqual(after.words.slice(1,15),before.words.slice(1,15));
  assert.equal(actual===expected,expectHeader,'selected exponent extraction contract');
  let decoded=null;
  if(mode==='ready'){
    assert.equal(after.words[0],before.words[0]);assert.equal(after.words[16],before.words[0],'real reverse V write');
    assert.equal(v.Z,before.words[16]);assert.equal(v.T,expected);
    assert.equal(after.words[17],before.words[18]);assert.equal(after.words[18],before.words[17]);
    assert.deepEqual(after.words.slice(19),before.words.slice(19));
    decoded='0'+v.T.slice(5,7)+after.words[15].slice(3);assert.equal(decoded,before.words[15]);
    assert.ok(before.words.every(w=>[...after.words,...Object.values(v),decoded].includes(w)));
  }else {
    assert.deepEqual(after.words.slice(1),before.words.slice(1));
    assert.equal(v.Y,before.words[0],'original P0 retained in Y');
    assert.equal(v.Z,before.words[16],'original V retained in Z');
    assert.equal(v.T,before.words[16],'no extra marker in T');
    assert.ok(before.words.every(w=>[...after.words,...Object.values(v)].includes(w)),
      'all 23 incoming words remain represented');
  }
  return{options:o,mode,marker:actual,expectedMarker:expected,headerCorrect:actual===expected,
    actualOriginalP0InV:mode==='ready',all23OriginalInformationRetained:mode==='ready'||mode==='maker',
    UPhysicallyRestored:after.words[15]===before.words[15],decodedU:decoded,programServicesHeld:true,
    nativeUnobservedMirror:true,sha256:hash(snapshot(c)),
    boundary:mode==='ready'?'native selected-domain write, U still requires restoration; not full K1':
      'native maker-only domain control, no writer attempted'};
}
if(require.main===module){
  for(const o of [
    {incoming:'307',values:['811','822','644','4.44E22']},
    {values:['811','822','833','-1.2345678E42']},
    {values:['811','822','833','1.23']}
  ])console.log(JSON.stringify(runCase(o)));
  console.log(JSON.stringify(runCase({values:['811','822','833','9.9999999E42']},'maker',true)));
  console.log(JSON.stringify(runCase({values:['811','822','833','4.44E-12']},'maker',false)));
}
module.exports={runCase,base};
