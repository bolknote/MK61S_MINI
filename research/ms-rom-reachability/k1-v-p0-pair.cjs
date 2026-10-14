#!/usr/bin/env node
'use strict';
// Conditional native pair. This is not an eight-word K1 or a universal
// numeric/timing contract. The fixed initial phase and numeric fixtures
// must be reported with successful tests.
const assert=require('node:assert/strict');
const candidate=require('./k1-p0-carrier-exchange.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing,MS_SLOTS,M1_SLOTS}=require('./k1-permutation-oracle.cjs');
const carrierWord='0040F0000000';
const options=o=>({...o,phaseOffset:o.phaseOffset??2,carrierWord,markerActions:[['ВП'],['4']],indirectKey:','});
const finish=(c,o={},record=()=>{})=>candidate.finish(c,options(o),record);
const run=(o={})=>capture.run(options(o),finish);
function check(r) {
  const result=candidate.check(r),es=r.traced.events,ww=r.traced.writes;
  const stores=es.filter(e=>e.stage==='indirect-p'&&e.ip===0xD4);
  assert.equal(stores.length,2);
  for(const [i,e] of stores.entries()) {
    const expected=ringAt(r,e.command),value=i?r.beforeRegisters[0]:'0070000F0000';
    [...value].reverse().forEach((digit,j)=>{expected.U[3*j]=parseInt(digit,16);});
    assert.deepEqual(ringAt(r,e.command+1),expected,'exact P0 carrier write among all 630 tetras');
    assert.deepEqual(ww.filter(w=>w.command===e.command).map(w=>[w.chip,w.slot,w.nibble]),
      Array.from({length:12},(_,j)=>[3,'U',3*j]));
  }
  const beforeWrite=es.find(e=>e.stage==='write-v'&&e.ring);assert.ok(beforeWrite);
  assert.deepEqual(snapshotFromRing(beforeWrite.ring).words,
    [...r.beforeRegisters,...MS_SLOTS.map(n=>r.before[n].slice(2))],
    'all 23 original words are back in their banks before the final Ms write');
  const writers=es.filter(e=>e.stage==='write-v'&&e.ip===0xE9&&e.slot==='V');
  assert.equal(writers.length,1);const e=writers[0],expected=ringAt(r,e.command);
  [...r.beforeRegisters[0]].reverse().forEach((digit,j)=>{expected.V[1+3*j]=parseInt(digit,16);});
  assert.deepEqual(ringAt(r,e.command+1),expected,'E9 writes exactly old P0 to V, all 630 tetras');
  assert.deepEqual(ww.filter(w=>w.command===e.command).map(w=>[w.chip,w.slot,w.nibble]),
    Array.from({length:12},(_,j)=>[3,'V',1+3*j]));
  const end=es.find(e=>e.stage==='done'&&e.ring);assert.ok(end);
  assert.deepEqual(Object.keys(end.ring).filter(n=>end.ring[n][22]===15),['marker']);
  return {...result,carrierStores:stores.map(e=>e.command),writeV:e.command,extraMarkersRemoved:true};
}
function roundTripFinish(c,o={},record=()=>{}) {
  finish(c,o,s=>record('cycle0/'+s));
  // The 450-frame key body is divisible by the three-frame ring period.
  // No diagnostic alignment/getter is inserted between the two calls.
  finish(c,{...o,phaseOffset:0},s=>record('cycle1/'+s));
  if(o.verifyExit) {
    record('post/manual');c.pressSequence(['Сx','2','В↑','3','+']).runFrames(8);
    record('post/zero');c.press('Сx').runFrames(8);
    record('post/program');c.pressSequence(['В/О','С/П']).runFrames(12);
  }
}
const runRoundTrip=(o={})=>capture.run(options(o),roundTripFinish);
function cycleView(r,index) {
  const prefix='cycle'+index+'/',es=r.traced.events;
  const first=es.find(e=>e.stage.startsWith(prefix)&&e.ring);
  assert.ok(first,'cycle start snapshot is required');
  const end=es.find(e=>e.command>first.command&&e.ring&&
    (index===0?e.stage.startsWith('cycle1/'):e.stage==='post/manual'||e.stage==='done'));
  assert.ok(first&&end);
  const before=snapshotFromRing(first.ring),after=snapshotFromRing(end.ring);
  return {...r,options:{...r.options,phaseOffset:index===0?r.options.phaseOffset:0},
    before:Object.fromEntries(MS_SLOTS.map(n=>[n,raw(first.ring[n],1,14)])),
    beforeRegisters:M1_SLOTS.map(n=>raw(first.ring[n],0)),beforeProgram:before.program,
    after:Object.fromEntries(MS_SLOTS.map(n=>[n,raw(end.ring[n],1,14)])),
    afterRegisters:M1_SLOTS.map(n=>raw(end.ring[n],0)),afterProgram:after.program,
    traced:{...r.traced,events:[...es.filter(e=>e.command>=first.command&&e.command<end.command)
      .map(e=>({...e,stage:e.stage.startsWith(prefix)?e.stage.slice(prefix.length):e.stage})),{...end,stage:'done'}],
      writes:r.traced.writes.filter(w=>w.command>=first.command&&w.command<end.command)}};
}
function checkRoundTrip(r) {
  const first=check(cycleView(r,0)),second=check(cycleView(r,1));
  assert.deepEqual(r.after,r.before);assert.deepEqual(r.afterRegisters,r.beforeRegisters);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  if(r.options.verifyExit) {
    assert.deepEqual(r.beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50],'declared saved-program test');
    const stage=name=>r.traced.events.find(e=>e.stage===name&&e.ring);
    assert.equal(raw(stage('post/zero').ring.X),'000050000000','manual 2+3 gives five');
    assert.equal(raw(stage('post/program').ring.X),'000000000000','clear sentinel before running the saved program');
    assert.equal(raw(stage('done').ring.X),'000050000000','the saved program independently gives five');
  }
  return {first,second,all23Restored:true,programHeld:true,workingExitChecked:!!r.options.verifyExit};
}
if(require.main===module) {
  const o=JSON.parse(process.argv[2]||'{}'),r=o.roundTrip?runRoundTrip(o):run(o);
  console.log('PASS conditional pair:',JSON.stringify(o.roundTrip?checkRoundTrip(r):check(r)));
  r.traced.events.length=r.traced.writes.length=0;
}
module.exports={carrierWord,options,finish,run,check,roundTripFinish,runRoundTrip,cycleView,checkRoundTrip};
