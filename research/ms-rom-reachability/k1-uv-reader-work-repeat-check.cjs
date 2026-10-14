#!/usr/bin/env node
'use strict';
// Read, use real normal arithmetic/program, read again: a native public-key
// continuity test, no reset/getter/alignment between the protocol operations.
const assert=require('node:assert/strict');
const candidate=require('./k1-zero-uv-retained-reader.cjs'),cap=require('./k1-bank-v-capture.cjs');
const {raw}=require('./probe_ms_two_markers.cjs'),{aligned}=require('./probe_ee_ring_source.cjs');
const {guarded}=require('./arbitrary-bank-pair-zero-capture-keyboard-check.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
function operation(c,o,record=()=>{}){
  candidate.operation(c,o,s=>record('first/'+s));
  const a=(s,k,n=8)=>{record(s);c.pressSequence(k).runFrames(n);};
  a('normal-sum',['Сx','2','В↑','3','+']);
  a('normal-lastx',['F','В↑']);
  a('program-clear',['Сx']);a('normal-program',['В/О','С/П'],12);
  candidate.operation(c,{...o,phaseOffset:0},s=>record('second/'+s));
}
function run(options={}){
  const o={...candidate.base,...options},r=cap.run(o,operation,['first/uv-read','second/uv-read']);
  const es=r.traced.events,at=s=>{const e=es.find(e=>e.stage===s&&e.ring);assert.ok(e,s);return e;};
  assert.equal(new Set(r.beforeRegisters.concat(Object.values(r.before).map(w=>w.slice(2)))).size,23);
  assert.equal(raw(at('normal-lastx').ring.X),'000050000000','normal 2+3 gives 5');
  assert.equal(raw(at('program-clear').ring.X),'000030000000','normal LastX gives 3');
  assert.equal(raw(at('normal-program').ring.X),'000000000000','program starts with cleared sentinel');
  assert.equal(raw(at('second/uv-clear').ring.X),'000050000000','saved nonempty program independently gives 5');
  const expected=['000000000000','25'+r.before.V.slice(4,5)+'000000000',r.before.V.slice(2),r.before.U.slice(2)];
  for(const s of ['normal-sum','done']){
    assert.deepEqual(['X','Y','Z','T'].map(w=>raw(at(s).ring[w])),expected,s+' U/V copied to Z/T');
    assert.deepEqual(Object.keys(at(s).ring).filter(w=>at(s).ring[w][22]===15),['marker']);
  }
  assert.deepEqual(r.afterRegisters,r.beforeRegisters);assert.deepEqual(r.after,r.before);assert.deepEqual(r.afterProgram,r.beforeProgram);
  for(const s of ['normal-sum','normal-program','second/uv-clear','done'])
    assert.deepEqual(snapshotFromRing(at(s).ring).program,r.beforeProgram,s+' complete 105-byte programme');
  assert.ok(r.traced.writes.filter(w=>(Object.hasOwn(r.before,w.slot)&&w.nibble%3===1)||
    w.nibble%3===0||[37,40].includes(w.nibble)).every(w=>w.before===w.value),
    'all incoming numerical banks and service fields held throughout both readers and ordinary work');
  // Normal user-program execution itself uses the original C9 fetch/cache
  // temporarily in the programme lane, then puts every byte back. This is
  // allowed ONLY for that explicit test stage, never in either reader.
  const fetchWrites=r.traced.writes.filter(w=>w.nibble%3===2&&w.before!==w.value);
  assert.ok(fetchWrites.length>0,'nonempty saved programme uses the real fetch path');
  assert.ok(fetchWrites.every(w=>w.ip===0xC9&&w.chip===3&&w.slot==='U'&&
    es.findLast(e=>e.command<=w.command)?.stage==='normal-program'),
    'programme writes must be only the native C9 fetch in the explicit normal-program stage');
  const plain=cap.prepare(o),g=guarded(plain);operation(g.proxy,o);plain.runFrames(3);aligned(plain);
  assert.deepEqual(JSON.parse(JSON.stringify(plain)),JSON.parse(JSON.stringify(r.calc)),'fresh full key-only native mirror');
  r.traced.events.length=r.traced.writes.length=0;
  return{options:o,normalSum:5,normalLastX:3,savedProgram:5,readers:2,all23BankWordsHeld:true,
    noResetOrAlignmentBetweenReaders:true,keys:g.counts.keys,bodyFrames:2*g.counts.keys+g.counts.extraFrames,
    programmeHeldAtBoundaries:true,temporaryNativeC9FetchWrites:fetchWrites.length,
    boundary:'two-word read-only working repetition, not an exchange or full K1'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2]?JSON.parse(process.argv[2]):{})));
module.exports={operation,run};
