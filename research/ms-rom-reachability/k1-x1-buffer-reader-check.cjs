#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-x1-buffer-reader.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const z='000000000000',m=probe.marker;
const same=(a,b)=>assert.deepEqual(a,b);
function check(r) {
  assert.equal(r.options.bufferTail,undefined,'extension needs its own contract');
  checks.protectedFields(r,[0]);
  const at=s=>checks.boundary(r,s),words=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
  const p=r.beforeRegisters[0],w=r.before.W.slice(2);
  same(words(at('buffer-zero-0')),[p,m,p,p,z]);
  same(words(at('buffer-read-W')),[p,z,z,z,m]);
  const ready=at(r.options.restore?'buffer-recall-original':'done');
  same(words(ready),[p,w,z,z,z]);
  same(raw(ready.ring.U,0),m);
  const start=r.traced.events.find(e=>e.ring),initial=snapshotFromRing(start.ring);
  assert.equal(new Set(initial.words).size,23,'all 23 original values must be distinct');
  const expected=initial.words.slice();expected[0]=m;
  same(snapshotFromRing(ready.ring).words,expected);
  same(Object.keys(ready.ring).filter(n=>ready.ring[n][22]===15),['marker']);
  const read=r.traced.events.find(e=>e.stage==='buffer-read-W'&&e.ip===0xEE);
  same([read.slot,read.raw,read.sp[0]],['W',w,0xE0]);
  const push=checks.exactPush(r,'buffer-read-W',['X','Y','Z','T']);same(push.displaced,m);
  const save=at('buffer-recall-marker');
  assert.ok(r.traced.writes.filter(x=>x.command>=save.command&&x.slot==='X1'&&x.nibble%3===1)
    .every(x=>x.before===x.value),'X1 held even transiently after saving the original');
  const end=at('done');
  if(r.options.restore) {
    same(r.afterRegisters,r.beforeRegisters);
    same(snapshotFromRing(end.ring).words,initial.words);
    same(words(end),[p,p,w,z,z]);
    const readBack=r.traced.events.find(e=>e.stage==='buffer-recall-original'&&e.ip===0xEE);
    same([readBack.slot,readBack.raw,readBack.sp[0]],['X1',p,0xF0]);
  } else same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i===0?m:x));
  return {phaseOffset:r.options.phaseOffset??0,originalP0:p,readW:w,
    all23StillLive:true,originalRecovered:!!r.options.restore,
    msAndOther14RegistersHeld:true,programAndServicesHeld:true,push,
    fullK1:false,phaseUniversal:false};
}
function surface() {
  const result=[];
  for(const restore of [false,true]) {
    const o={restore},a=keyboard.record(o,probe.finish);
    same(a,keyboard.record({...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
    const keys=a.filter(x=>x[0]==='key').length;
    const frames=keys*2+a.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
    same([keys,frames],restore?[38,286]:[34,262]);
    result.push({restore,keys,frames,noHiddenReads:true});
  }
  return result;
}
function negativeScanner(r) {
  assert.equal(r.options.phaseOffset,1);
  assert.equal(r.options.restore,undefined);
  const stage='buffer-read-W',es=r.traced.events;
  const scanner=es.find(e=>e.stage===stage&&e.ip===0x9C);
  same([scanner.slot,scanner.raw[0],scanner.nextIp],['U','9',0x9E]);
  const read=es.find(e=>e.stage===stage&&e.ip===0xEE);
  same([read.slot,read.raw],['X',z]);
  const push=checks.exactPush(r,stage,['W','Q','P7','P8']);
  checks.protectedFields(r,[0],['W','Q','P7','P8']);
  const expected={...r.before};
  for(const [n,value] of Object.entries({W:z,Q:r.before.W.slice(2),P7:r.before.Q.slice(2),P8:r.before.P7.slice(2)}))
    expected[n]=r.before[n].slice(0,2)+value;
  same(r.after,expected);
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i===0?m:x));
  const end=checks.boundary(r,'done');same(raw(end.ring.X1),r.beforeRegisters[0]);
  const live=[...snapshotFromRing(end.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(end.ring[n]))];
  assert.ok(!live.includes(r.before.P8.slice(2)),'sixth Ms origin missing, despite intact X1 buffer');
  return {expectedFailure:true,bufferRetained:true,validReader:false,phaseProblemSolved:false,push};
}
if(require.main===module) {
  console.log('PASS keyboard surface:',JSON.stringify(surface()));
  const o={incoming:'-6.5432109E65',values:['811','12345678','-9.8765432E99','-1E-99'],
    ...JSON.parse(process.env.K1_X1_OPTIONS||'{}')};
  if(process.env.K1_X1_NEGATIVE) {
    const r=probe.run({...o,phaseOffset:1});
    console.log('PASS rejected X1-buffer scanner phase:',JSON.stringify(negativeScanner(r)));process.exit(0);
  }
  const r=probe.run(o);
  console.log('PASS conditional X1 buffer:',JSON.stringify(check(r)));
  if(process.env.K1_X1_UNOBSERVED)console.log('PASS observer-free full state:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={check,surface,negativeScanner};
