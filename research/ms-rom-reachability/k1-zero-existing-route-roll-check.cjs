#!/usr/bin/env node
'use strict';
// Two ROM-directed counterexamples at 0/0/F/p. No key search or state import.
// ROLL is native, but its primary request either corrupts p in T or clears U.
const assert=require('node:assert/strict');
const zeroCapture=require('./arbitrary-bank-pair-zero-capture.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const zero='000000000000',marker='0000F0000000';
const ms=['U','V','W','Q','P7','P8','P9','P10'];
const base={phaseOffset:2,p3:'777',values:['811','822','-9.8765432E23','4.44E12'],
  fullUpper:['9011','9022','9033','9044']};
const cases=[{incoming:'-1.2345678E42',kind:'request-overwrites-p'},
  {incoming:'-1.234E-42',kind:'reserve-overwrites-u'}];

function operation(c,o,record=()=>{}) {
  zeroCapture.operation(c,o,record);
  record('existing-roll');c.pressSequence(['F',',']).runFrames(8);
}

function check(r,kind) {
  const start=r.traced.events.find(e=>e.stage==='existing-roll'&&e.ring);
  const end=r.traced.events.find(e=>e.stage==='done'&&e.ring);
  assert.ok(start&&end);
  const p=r.beforeRegisters[0],u=r.before.U.slice(2),v=r.before.V.slice(2);
  const visible=e=>['X','Y','Z','T'].map(n=>raw(e.ring[n]));
  assert.deepEqual(visible(start),[zero,zero,marker,p]);
  const input=[...r.beforeRegisters,...ms.map(n=>r.before[n].slice(2))];
  assert.equal(new Set(input).size,23,'counterexample must use 23 distinct bank words');
  const before=snapshotFromRing(start.ring);
  assert.deepEqual(before.words,[v,...r.beforeRegisters.slice(1),...ms.map(n=>r.before[n].slice(2))]);
  const es=r.traced.events.filter(e=>e.stage==='existing-roll');
  const gates=es.filter(e=>e.ip===0x9C),reads=es.filter(e=>e.ip===0xEE);
  const saves=es.filter(e=>e.ip===0xE9),requests=es.filter(e=>e.ip===0xA3);
  assert.equal(saves.length,1);assert.equal(requests.length,1);
  const expectedWrite=ringAt(r,saves[0].command);
  const source=kind==='request-overwrites-p'?v:zero;
  const target=kind==='request-overwrites-p'?'X1':'U';
  [...source].reverse().forEach((digit,i)=>{expectedWrite[target][1+3*i]=parseInt(digit,16);});
  assert.deepEqual(ringAt(r,saves[0].command+1),expectedWrite,'E9 is one exact 12-tetra copy among all 630');
  const expectedRequest=ringAt(r,requests[0].command);
  const request=kind==='request-overwrites-p'?'T':'control';
  [28,31,34].forEach((n,i)=>{expectedRequest[request][n]=[parseInt(source[2],16),5,2][i];});
  assert.deepEqual(ringAt(r,requests[0].command+1),expectedRequest,'A3 changes exactly three request tetras');
  const live=[...snapshotFromRing(end.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(end.ring[n]))];
  const lost=input.filter(w=>!live.includes(w));
  if(kind==='request-overwrites-p') {
    assert.deepEqual(gates.map(e=>[e.slot,e.nextIp]),[['T',0x9D],['control',0x9E],['control',0x9E]]);
    assert.deepEqual(reads.map(e=>[e.slot,e.raw]),[['V',v],['X',zero]]);
    assert.deepEqual([saves[0].slot,raw(saves[0].r,0)],[target,v]);
    assert.equal(requests[0].slot,'T');
    assert.deepEqual(visible(end),[zero,'25'+v[2]+p.slice(3),v,u]);
    assert.deepEqual(r.after,r.before);assert.deepEqual(lost,[p]);
  } else {
    assert.deepEqual(gates.map(e=>[e.slot,e.nextIp]),[['T',0x9E],['T',0x9E]]);
    assert.deepEqual(reads.map(e=>[e.slot,e.raw]),[['X',zero],['X',zero]]);
    assert.deepEqual([saves[0].slot,raw(saves[0].r,0)],[target,zero]);
    assert.equal(requests[0].slot,'control');
    assert.deepEqual(visible(end),[zero,marker,p,zero]);
    assert.deepEqual(r.after,{...r.before,U:r.before.U.slice(0,2)+zero});
    assert.deepEqual(lost,[u]);
  }
  assert.deepEqual(r.afterRegisters,[v,...r.beforeRegisters.slice(1)]);
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  assert.ok(r.traced.writes.filter(w=>w.command>=start.command&&
    (w.nibble%3===0||w.nibble%3===2||[37,40].includes(w.nibble))).every(w=>w.before===w.value),
    'ROLL leaves every M1/program/service tetra unchanged');
  return {kind,p,u,lost,frontier:visible(start),result:visible(end),
    accepted9C:gates.find(e=>e.nextIp===0x9E).slot,E9:saves[0].slot,A3:requests[0].slot,
    programAndServiceHeld:true,wholeBankPreserved:false};
}

for(const test of cases) {
  const options={...base,incoming:test.incoming};
  const r=cap.run(options,operation,['existing-roll']),report=check(r,test.kind);
  const plain=cap.prepare(options);operation(plain,options);plain.runFrames(3);aligned(plain);
  assert.deepEqual(JSON.parse(JSON.stringify(plain)),JSON.parse(JSON.stringify(r.calc)),
    'fresh unobserved native run must equal the complete traced machine');
  console.log('PASS narrow native ROLL counterexample',JSON.stringify({...report,observerIndependent:true}));
  r.traced.events.length=r.traced.writes.length=0;
}
console.log('LIMIT: two fixed native continuations; no general impossibility, full pair, or arbitrary timing claim.');
