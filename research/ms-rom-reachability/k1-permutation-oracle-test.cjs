#!/usr/bin/env node
'use strict';
// Synthetic unit tests only. This file must not import/run a calculator.
const assert=require('node:assert/strict');
const o=require('./k1-permutation-oracle.cjs');
const originalWords=Array.from({length:23},(_,i)=>(i+1).toString(16).toUpperCase().padStart(12,'0'));
const identity=Array.from({length:23},(_,i)=>i);
const swap=(a,b)=>{const p=identity.slice();[p[a],p[b]]=[p[b],p[a]];return p;};
const fixture=()=>({words:originalWords.slice(),program:Array.from({length:105},(_,i)=>(i*17)%256),
  services:{m1:Array.from({length:30},(_,i)=>i%16),m2:Array.from({length:30},(_,i)=>(15-i+32)%16)}});
const clone=structuredClone;
let tests=0;
function test(name,fn){fn();tests++;console.log('PASS:',name);}
function analyze(before,after,extra={}){return o.analyzeSnapshots({before,after,...extra});}
function deepFreeze(v){Object.freeze(v);for(const x of Object.values(v))if(x&&typeof x==='object')deepFreeze(x);return v;}

test('identity is only an instance, with no useful cross-bank edge',()=>{
  const b=fixture(),r=analyze(b,clone(b));
  assert.equal(r.status,'PERMUTATION_INSTANCE_ONLY');assert.equal(r.data.bijection,true);
  assert.deepEqual(r.data.destinationToSource,identity);assert.deepEqual(r.data.cycles,[]);
  assert.equal(r.data.hasOrdinaryToMsEdge,false);assert.equal(r.suitableForComposition,false);
  assert.equal(r.fullK1,false);assert.equal(r.operational.workingExit,'not_checked');
  assert.equal(r.operational.repeatability,'not_checked');
});
test('exact V/P0 pair and fixed mapping; inputs remain untouched',()=>{
  const b=fixture(),p=swap(0,16),a={...clone(b),words:p.map(i=>b.words[i])};
  deepFreeze(b);deepFreeze(a);Object.freeze(p);
  const r=analyze(b,a,{expectedMapping:p});
  assert.equal(r.data.bijection,true);assert.equal(r.fixedMapping.status,'matches_this_fixture');
  assert.deepEqual(r.data.cycles,[['reg.0','ms.V']]);assert.equal(r.data.hasOrdinaryToMsEdge,true);
  assert.equal(r.fullK1,false);assert.deepEqual(r.data.sourceToDestination,p);
});
test('capture V duplicated in P0/V does not count X/Y as a saved bank value',()=>{
  const b=fixture(),a=clone(b);a.words[0]=b.words[16];
  a.visible={X:b.words[0],Y:b.words[0]};
  const r=analyze(b,a);assert.equal(r.status,'DATA_LOSS_OR_DUPLICATION');
  assert.deepEqual(r.data.missing.map(x=>x.sourcePlaces),[['reg.0']]);
  assert.deepEqual(r.data.duplicates[0].destinationPlaces,['reg.0','ms.V']);
  assert.equal(r.data.destinationToSource,null);
});
test('foreign marker is reported independently of missing originals',()=>{
  const b=fixture(),a=clone(b);a.words[17]='0000F0000000';
  const r=analyze(b,a);assert.equal(r.data.foreign[0].word,'0000F0000000');
  assert.deepEqual(r.data.foreign[0].destinationPlaces,['ms.W']);
  assert.equal(r.data.missing[0].sourcePlaces[0],'ms.W');
});
test('coincident zeros are not identifiable, even if a fixed mapping matches',()=>{
  const b=fixture();b.words[19]=b.words[20]='000000000000';
  const r=analyze(b,clone(b),{expectedMapping:swap(19,20)});
  assert.equal(r.status,'NON_DISTINCT_FIXTURE');assert.equal(r.data.sameMultiset,true);
  assert.equal(r.data.bijection,false);assert.equal(r.data.destinationToSource,null);
  assert.equal(r.fixedMapping.status,'matches_this_fixture');
  assert.equal(r.fixedMapping.originIdentifiable,false);
  assert.deepEqual(r.fixture.collisions[0].sourcePlaces,['ms.P7','ms.P8']);
});
test('multiplicity deficits remain visible in an already colliding fixture',()=>{
  const b=fixture();b.words[19]=b.words[20];const a=clone(b);a.words[20]=b.words[21];
  const r=analyze(b,a);assert.equal(r.data.sameMultiset,false);
  assert.equal(r.data.missing[0].missingCount,1);assert.equal(r.data.duplicates[0].extraCount,1);
});
test('different permutation is not silently relearned',()=>{
  const b=fixture(),p=swap(0,16),a={...clone(b),words:swap(0,17).map(i=>b.words[i])};
  const r=analyze(b,a,{expectedMapping:p});assert.equal(r.data.bijection,true);
  assert.equal(r.status,'FIXED_MAPPING_MISMATCH');assert.equal(r.fixedMapping.status,'mismatch');
  assert.deepEqual(r.fixedMapping.mismatches.map(x=>x.destination),['reg.0','ms.V','ms.W']);
});
test('non-involutive cycles have explicit source-to-destination orientation',()=>{
  const b=fixture(),pi=identity.slice();pi[1]=0;pi[16]=1;pi[0]=16;
  const r=analyze(b,{...clone(b),words:pi.map(i=>b.words[i])});
  assert.deepEqual(r.data.cycles,[['reg.0','reg.1','ms.V']]);
  assert.equal(r.data.sourceToDestination[0],1);assert.equal(r.data.destinationToSource[0],16);
});
test('all 60 service fields are checked, including pages outside Ms',()=>{
  for(const lane of ['m1','m2'])for(let i=0;i<30;i++) {
    const b=fixture(),a=clone(b);a.services[lane][i]^=1;const r=analyze(b,a);
    assert.equal(r.status,'PROTECTED_FIELD_DAMAGE');
    assert.equal(r.protection[lane==='m1'?'m1Service':'m2Service'].changes[0].index,i);
  }
});
test('all 105 program bytes are protected, not just exchanged-page prefixes',()=>{
  for(let i=0;i<105;i++) {
    const b=fixture(),a=clone(b);a.program[i]^=1;
    const r=analyze(b,a);assert.equal(r.status,'PROTECTED_FIELD_DAMAGE');
    assert.equal(r.protection.program.changes[0].index,i);
  }
});
test('missing protection is unverified rather than silently preserved',()=>{
  const b={words:originalWords.slice()},r=analyze(b,clone(b));
  assert.equal(r.status,'PERMUTATION_WITH_UNVERIFIED_PROTECTION');
  assert.equal(r.protection.program.status,'unverified_missing_snapshot');
  assert.equal(r.protection.m1Service.status,'unverified_missing_snapshot');
});
test('changed-and-restored service writes are distinct from endpoint damage',()=>{
  const b=fixture(),writes=[{slot:'X',nibble:37,before:0,value:2,command:1,chip:4},
    {slot:'X',nibble:37,before:2,value:0,command:2,chip:5},
    {slot:'V',nibble:1,before:0,value:2,command:3,chip:3}];
  const r=analyze(b,clone(b),{writes});assert.equal(r.status,'PERMUTATION_INSTANCE_ONLY');
  assert.equal(r.transientProtection.status,'changes_observed');
  assert.equal(r.transientProtection.changes.length,2);assert.equal(r.transientProtection.coverage,'unverified');
});
test('malformed words, mappings, snapshots and writes fail explicitly',()=>{
  const b=fixture();assert.throws(()=>analyze(b,{...b,words:b.words.slice(1)}),TypeError);
  const a=clone(b);a.words[0]='123';assert.throws(()=>analyze(b,a),TypeError);
  assert.throws(()=>analyze(b,b,{expectedMapping:Array(23).fill(0)}),TypeError);
  assert.throws(()=>analyze(b,{...b,program:Array(105).fill(256)}),TypeError);
  assert.throws(()=>analyze({...b,words:Array(23)},b),TypeError);
  assert.throws(()=>analyze(b,{...b,program:Array(105)}),TypeError);
  assert.throws(()=>analyze(b,b,{expectedMapping:Array(23)}),TypeError);
  assert.throws(()=>analyze(b,b,{writes:[{slot:'V',nibble:42,before:0,value:1}]}),TypeError);
});

// Independent construction: explicitly list the native physical-to-logical map.
function ringFixture() {
  const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
  const ordinary=['U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T'];
  const ms=['U','V','W','Q','P7','P8','P9','P10'],s=fixture();
  const ring=Object.fromEntries(slots.map(n=>[n,Array(42).fill(0)]));
  for(let i=0;i<23;i++) {
    const page=ring[i<15?ordinary[i]:ms[i-15]],lane=i<15?0:1;
    const digits=[...s.words[i]].map(x=>parseInt(x,16)).reverse();
    for(let d=0;d<12;d++)page[d*3+lane]=digits[d];
  }
  for(let i=0;i<15;i++) {
    const page=ring[ordinary[i]];
    const lowPositions=[38,2,8,14,20,26,32];
    for(let j=0;j<7;j++){const byte=s.program[i*7+j],lo=lowPositions[j];page[lo]=byte&15;page[lo+3]=byte>>4;}
  }
  for(let i=0;i<15;i++)for(const [lane,positions] of [['m1',[36,39]],['m2',[37,40]]])
    for(let j=0;j<2;j++)ring[slots[i]][positions[j]]=s.services[lane][i*2+j];
  return {ring,snapshot:s};
}
test('ring extraction agrees with explicit M1/M2/M3 layout and does not mutate',()=>{
  const {ring,snapshot}=ringFixture();deepFreeze(ring);
  assert.deepEqual(o.snapshotFromRing(ring),snapshot);
  assert.throws(()=>o.snapshotFromRing({...ring,X:Array(41).fill(0)}),TypeError);
});
test('trace boundaries are explicit, writes are start-inclusive/end-exclusive',()=>{
  const {ring}=ringFixture(),beforeEvent={command:10,ring},afterEvent={command:20,ring};
  const writes=[9,10,19,20].map(command=>({command,slot:'V',nibble:40,before:0,value:1,chip:3}));
  const r=o.analyzeTrace({beforeEvent,afterEvent,writes,expectedMapping:identity});
  assert.deepEqual(r.transientProtection.changes.map(w=>w.command),[10,19]);
  assert.equal(r.boundaries.beforeCommand,10);assert.equal(r.boundaries.afterCommand,20);
  assert.throws(()=>o.analyzeTrace({beforeEvent:afterEvent,afterEvent:beforeEvent}),TypeError);
  assert.throws(()=>o.analyzeTrace({beforeEvent:{ring},afterEvent}),TypeError);
});
test('even the exact full K1 permutation does not imply a usable command',()=>{
  const b=fixture(),pi=identity.slice();for(let i=0;i<8;i++)[pi[i],pi[15+i]]=[pi[15+i],pi[i]];
  const r=analyze(b,{...clone(b),words:pi.map(i=>b.words[i])},{expectedMapping:pi});
  assert.equal(r.data.cycles.length,8);assert.equal(r.fixedMapping.status,'matches_this_fixture');
  assert.equal(r.status,'PERMUTATION_INSTANCE_ONLY');assert.equal(r.fullK1,false);
});
console.log(`PASS: ${tests} pure synthetic oracle test groups; no native execution or K1 completion claim.`);
