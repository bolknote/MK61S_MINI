#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const reader=require('./k1-zero-nop-reader.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const same=(a,b)=>assert.deepEqual(a,b);
const m='0000F0000000',z='000000000000';
function check(r) {
  checks.protectedFields(r);
  const at=s=>checks.boundary(r,s);
  const words=e=>['X','Y','Z','T'].map(n=>raw(e.ring[n]));
  same(words(at('reader-zero-0')),[m,z,z,z]);
  for(let i=0;i<3;i++) {
    const expected=[z,z,z,z];expected[i+1]=m;
    same(words(at('reader-nop-'+i)),expected);
  }
  same(words(at('reader-read-W')),[z,z,z,m]);
  const w=r.before.W.slice(2),end=at('done');
  same(words(end),[w,z,z,z]);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15),['marker']);
  same(snapshotFromRing(end.ring).words,snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words);
  const read=r.traced.events.find(e=>e.stage==='reader-read-W'&&e.ip===0xEE);
  same([read.slot,read.raw,read.sp[0]],['W',w,0xE0]);
  const push=checks.exactPush(r,'reader-read-W',['X','Y','Z','T']);
  same(push.displaced,m);
  return {phase:r.options.phaseOffset??0,readW:w,allStoredWordsHeld:true,
    noOrdinaryScratch:true,programAndServiceHeld:true,extraMarkersRemoved:true,push};
}
function surface() {
  const a=keyboard.record({},reader.finish);
  same(a,keyboard.record({incoming:'not read',p3:'not read',values:['not read'],fullUpper:['not read']},reader.finish));
  const keys=a.filter(a=>a[0]==='key').length;
  const frames=keys*2+a.filter(a=>a[0]==='wait').reduce((n,a)=>n+a[1],0);
  same([keys,frames],[21,179]);return {keys,frames,noHiddenReads:true};
}
function negativeScanner(r) {
  assert.equal(r.options.phaseOffset,1);
  const es=r.traced.events,stage='reader-read-W';
  const scanner=es.find(e=>e.stage===stage&&e.ip===0x9C);
  same(scanner.slot,'U');assert.equal(scanner.raw[0],'9');
  const read=es.find(e=>e.stage===stage&&e.ip===0xEE);
  same([read.slot,read.raw],['X',z]);
  const push=checks.exactPush(r,stage,['W','Q','P7','P8']);
  const expected={...r.before};
  for(const [n,value] of Object.entries({W:z,Q:r.before.W.slice(2),P7:r.before.Q.slice(2),P8:r.before.P7.slice(2)}))
    expected[n]=r.before[n].slice(0,2)+value;
  same(r.after,expected);same(r.afterRegisters,r.beforeRegisters);
  checks.protectedFields(r,[],['W','Q','P7','P8']);
  const end=checks.boundary(r,'done');
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15),['marker','T']);
  const live=[...snapshotFromRing(end.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(end.ring[n]))];
  assert.ok(!live.includes(r.before.P8.slice(2)),'original sixth Ms word is lost');
  return {expectedFailure:true,validReader:false,scanner:scanner.command,read:read.command,push,
    missingStoredOrigin:'Ms P8 (sixth word)',notANumericFormatterFailure:true};
}
if(require.main===module) {
  console.log('PASS keyboard surface:',JSON.stringify(surface()));
  if(process.env.K1_READER_NEGATIVE) {
    const r=reader.run({phaseOffset:1,values:['811','12345678','-9.8765432E99','-1E-99'],p3:'-6.5432109E65'});
    console.log('PASS rejected scanner phase:',JSON.stringify(negativeScanner(r)));process.exit(0);
  }
  const r=reader.run(JSON.parse(process.env.K1_READER_OPTIONS||'{}'));
  console.log('PASS exact W reader:',JSON.stringify(check(r)));
  if(process.env.K1_READER_UNOBSERVED)console.log('PASS observer-free full state:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,reader.finish));
}
module.exports={check,surface,negativeScanner};
