#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-puhov-ring-probe.cjs');
const retained=require('./k1-q-retained-probe.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing,analyzeTrace}=require('./k1-permutation-oracle.cjs');
const marker='9990FFFFFFF0';
function boundary(r,name) {
  const e=r.traced.events.find(e=>e.stage===name&&e.ring);assert.ok(e,name);return e;
}
function protectedFields(r,ordinaryExceptions=[],msExceptions=[]) {
  const ww=r.traced.writes,ordinary=['U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T'];
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.ok(ww.filter(w=>w.nibble%3===2||[36,37,39,40].includes(w.nibble)).every(w=>w.before===w.value),
    'program and all M1/M2 service tetras held even transiently');
  for(let i=0;i<15;i++)if(!ordinaryExceptions.includes(i)) {
    assert.equal(r.afterRegisters[i],r.beforeRegisters[i]);
    assert.ok(ww.filter(w=>w.slot===ordinary[i]&&w.nibble%3===0&&w.nibble<36).every(w=>w.before===w.value));
  }
  for(const n of Object.keys(r.before))if(!msExceptions.includes(n)) {
    assert.equal(r.after[n],r.before[n]);
    assert.ok(ww.filter(w=>w.slot===n&&w.nibble%3===1).every(w=>w.before===w.value));
  }
  assert.deepEqual(r.traced.primitives,[]);assert.ok(r.traced.events.every(e=>e.ip!==0xC9));
}
function exactPush(r,stage,targets) {
  const es=r.traced.events,first=es.find(e=>e.stage===stage&&e.ip===0xE7&&e.slot===targets[0]);assert.ok(first);
  const expected=ringAt(r,first.command),initial=structuredClone(expected);
  let carried=Array.from({length:12},(_,j)=>first.r[3*j]);
  for(const [i,n] of targets.entries()) {
    const e=es.find(e=>e.command===first.command+i);assert.ok(e);
    assert.deepEqual([e.ip,e.slot],[i?0xA8:0xE7,n]);
    assert.deepEqual(Array.from({length:12},(_,j)=>e.r[3*j]),carried);
    const old=Array.from({length:12},(_,j)=>expected[n][1+3*j]);
    carried.forEach((v,j)=>{expected[n][1+3*j]=v;});carried=old;
  }
  assert.deepEqual(ringAt(r,first.command+targets.length),expected,'exact push among all 630 tetras');
  const next=es.find(e=>e.command===first.command+targets.length);assert.ok(next);
  assert.deepEqual(Array.from({length:12},(_,j)=>next.r[3*j]),carried,'displaced last word at A9 entry');
  assert.deepEqual(r.traced.writes.filter(w=>w.command>=first.command&&w.command<next.command)
    .map(w=>[w.chip,w.slot,w.nibble]),targets.flatMap(n=>Array.from({length:12},(_,j)=>[3,n,1+3*j])));
  return {command:first.command,targets,displaced:raw(initial[targets.at(-1)])};
}
function checkRead(r) {
  assert.equal(r.options.rotate,undefined);
  protectedFields(r);
  const end=boundary(r,'done'),start=r.traced.events.find(e=>e.ring);
  assert.equal(raw(end.ring.X),r.before.W.slice(2));
  assert.deepEqual(Object.keys(end.ring).filter(n=>end.ring[n][22]===15),['marker']);
  const oracle=analyzeTrace({beforeEvent:start,afterEvent:end,writes:r.traced.writes,
    expectedMapping:Array.from({length:23},(_,i)=>i)});
  assert.equal(oracle.fixture.distinct,true);assert.equal(oracle.fixedMapping.status,'matches_this_fixture');
  return {read:'W',all23StoredWordsHeld:true,allMarkersRemoved:true};
}
function checkFifoLoss(r) {
  assert.equal(r.options.rotate,true);
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2));
  protectedFields(r,[9],['U','V','W','Q']);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((x,i)=>i===9?w:x));
  for(const [n,value] of Object.entries({U:w,V:u,W:v,Q:w}))assert.equal(r.after[n],r.before[n].slice(0,2)+value);
  const e=boundary(r,'done'),oracle=analyzeTrace({beforeEvent:r.traced.events.find(e=>e.ring),afterEvent:e,writes:r.traced.writes});
  assert.equal(oracle.fixture.distinct,true);assert.equal(oracle.status,'DATA_LOSS_OR_DUPLICATION');
  assert.deepEqual(oracle.data.missing.flatMap(x=>x.sourcePlaces),['reg.9','ms.Q']);
  const push=exactPush(r,'write-oldest/2',['U','V','W','Q']);assert.equal(push.displaced,q);
  return {oldThreeRotate:true,lost:['old ordinary P9','old Ms Q'],push,notA23WordPermutation:true};
}
function checkRetainedQ(r) {
  assert.equal(r.options.saveQ,true);assert.equal(r.options.retainMsV,undefined);
  assert.equal(r.options.retainKey,undefined);assert.equal(r.options.tail,undefined);
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const visibleMarker=r.options.neutralMarker?'0000FFFFFFF0':marker;
  protectedFields(r,[0],['U','V','W']);
  const start=boundary(r,'q-load');
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(start.ring[n])),[visibleMarker,w,p,marker]);
  for(const n of Object.keys(r.before))assert.equal(raw(start.ring[n],1,14),r.before[n]);
  const push=exactPush(r,'q-load',['T','U','V','W']);assert.equal(push.displaced,w);
  const end=boundary(r,'done');
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[q,visibleMarker,w,p]);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((x,i)=>i===0?q:x));
  assert.deepEqual(r.after,{...r.before,U:r.before.U.slice(0,2)+marker,
    V:r.before.V.slice(0,2)+u,W:r.before.W.slice(0,2)+v});
  const original=[...r.beforeRegisters,...Object.keys(r.before).map(n=>r.before[n].slice(2))];
  assert.equal(new Set(original).size,23);
  const extended=[...snapshotFromRing(end.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(end.ring[n]))];
  assert.ok(original.every(word=>extended.includes(word)),'all 23 old words still exist, some only in the visible stack');
  assert.deepEqual(Object.keys(end.ring).filter(n=>end.ring[n][22]===15),['marker','U','Y']);
  return {q:r.afterRegisters[0],oldW:raw(end.ring.Z),oldP0:raw(end.ring.T),all23StillLive:true,
    push,ordinary14Held:true,programHeld:true,completeExchange:false,cleanupPending:true};
}
function checkLastXLoss(r) {
  assert.equal(r.options.saveQ,true);assert.deepEqual(r.options.tail,[['F'],['В↑']]);
  protectedFields(r,[0],['U','V','W']);
  const p=r.beforeRegisters[0],q=r.before.Q.slice(2),w=r.before.W.slice(2),es=r.traced.events;
  const reads=es.filter(e=>e.stage==='q-tail-1'&&e.ip===0xEE);
  assert.deepEqual(reads.map(e=>[e.slot,e.raw]),[['T',p],['Q',q]]);
  const push=exactPush(r,'q-tail-1',['X','Y','Z','T']);
  const replace=es.find(e=>e.stage==='q-tail-1'&&e.command>reads[1].command&&e.ip===0xE7);
  assert.ok(replace);assert.equal(replace.slot,'X');assert.equal(raw(replace.m),p);assert.equal(raw(replace.r,0),q);
  const expected=ringAt(r,replace.command);
  [...q].reverse().forEach((v,j)=>{expected.X[1+3*j]=parseInt(v,16);});
  assert.deepEqual(ringAt(r,replace.command+1),expected,'late formatter destroys the only visible old P0 copy');
  const end=boundary(r,'done');
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[q,q,marker,w]);
  const available=[...snapshotFromRing(end.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(end.ring[n]))];
  assert.ok(!available.includes(p));
  return {oldP0Read:reads[0].command,visiblePush:push.command,overwritten:replace.command,
    oldP0AbsentFromStoredAndVisibleWords:true,validExit:false};
}
function checkNegativeU(r) {
  assert.equal(r.options.retainMsV,true);assert.deepEqual(r.options.values,['811','822','833','-1.2E-42']);
  assert.deepEqual(r.options.tail,[['↔']]);
  const start=boundary(r,'q-enter'),end=boundary(r,'q-tail-0');
  const [a,b]=['P7','P8'].map(n=>r.before[n].slice(2)),q=r.before.Q.slice(2),v=r.before.V.slice(2);
  assert.deepEqual(['W','Q','P7','P8'].map(n=>raw(start.ring[n])),[v,q,a,b]);
  const push=exactPush(r,'q-enter',['W','Q','P7','P8']);assert.equal(push.displaced,b);
  assert.deepEqual(['W','Q','P7','P8'].map(n=>raw(end.ring[n])),[marker,v,q,a]);
  assert.ok(![...snapshotFromRing(end.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(end.ring[n]))].includes(b));
  assert.deepEqual(r.afterRegisters,r.beforeRegisters);assert.deepEqual(r.afterProgram,r.beforeProgram);
  return {negativeUChangesQEntry:true,push,oldSixthMsAbsentBeforeProposedRepair:true,validCapture:false};
}
if(require.main===module) {
  const cases=[['read',()=>probe.run({}),checkRead],['fifo-loss',()=>probe.run({rotate:true}),checkFifoLoss],
    ['retained-q',()=>retained.run({saveQ:true}),checkRetainedQ],
    ['lastx-loss',()=>retained.run({saveQ:true,tail:[['F'],['В↑']]}),checkLastXLoss],
    ['negative-u',()=>retained.run({retainMsV:true,values:['811','822','833','-1.2E-42'],tail:[['↔']]}),checkNegativeU]];
  for(const [name,run,check] of cases)if(!process.env.K1_PUHOV_CASE||process.env.K1_PUHOV_CASE===name) {
    const r=run();console.log('PASS '+name+':',JSON.stringify(check(r)));
    r.traced.events.length=r.traced.writes.length=0;
  }
}
module.exports={boundary,protectedFields,exactPush,checkRead,checkFifoLoss,checkRetainedQ,checkLastXLoss,checkNegativeU};
