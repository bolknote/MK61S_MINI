#!/usr/bin/env node
'use strict';
// Regression for a rejected V/P0 permutation, not a completed exchange.
const assert=require('node:assert/strict');
const probe=require('./k1-lastx-v-exchange.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {swap}=require('./check_ms_quiet_upper.cjs');
const ms=['U','V','W','Q','P7','P8','P9','P10'];
const marker='0000F0000000';
const options={phaseOffset:0,values:['444','222','333','111'],
  afterLastX:[['↔'],['↔'],['F',','],['↔']]};
function check(r) {
  assert.deepEqual(r.options,options,'this is one exact native counterexample');
  const es=r.traced.events,ww=r.traced.writes;
  const at=i=>{const e=es.find(e=>e.stage==='lastx-tail-'+i&&e.ring);assert.ok(e);return e;};
  const done=es.find(e=>e.stage==='done'&&e.ring);assert.ok(done);
  const [u,v,w,q]=ms.slice(0,4).map(n=>r.before[n].slice(2));
  const p=r.beforeRegisters[0];assert.equal(new Set([p,u,v,w,q]).size,5);
  const visible=e=>['X','Y','Z','T'].map(n=>raw(e.ring[n]));
  const lower=e=>ms.slice(0,4).map(n=>raw(e.ring[n]));
  assert.deepEqual(visible(at(0)),[p,p,marker,'000000000000']);
  assert.deepEqual(lower(at(0)),[u,v,w,q]);
  assert.deepEqual(visible(at(1)),[u,p,p,marker]);
  assert.deepEqual(lower(at(1)),[u,v,w,q]);
  const reads=es.filter(e=>e.stage==='lastx-tail-0'&&e.ip===0xEE);
  assert.deepEqual(reads.map(e=>[e.slot,raw(e.m)]),[['U',u],['X',u]]);
  const lift=es.find(e=>e.stage==='lastx-tail-0'&&e.ip===0xE7);
  swap(r,lift.command,['X','Y','Z','T']);
  const firstSwap=es.filter(e=>e.stage==='lastx-tail-1');
  const x1=firstSwap.find(e=>e.ip===0xE9);
  assert.deepEqual([x1.slot,raw(x1.r,0)],['X1',w]);
  assert.deepEqual(visible(at(2)),[u,p,p,marker]);
  assert.deepEqual(lower(at(2)),['1F'+u.slice(2),v,q,w]);
  const secondSwap=es.filter(e=>e.stage==='lastx-tail-2');
  const vwrite=secondSwap.find(e=>e.ip===0xE9);
  assert.deepEqual([vwrite.slot,raw(vwrite.r,0)],['V',u]);
  const wanted=ringAt(r,vwrite.command);
  for(let j=0;j<12;j++)wanted.V[1+3*j]=vwrite.r[3*j];
  assert.deepEqual(ringAt(r,vwrite.command+1),wanted,'E9 writes exactly U to V, all 630 tetras');
  assert.deepEqual(ww.filter(w=>w.command===vwrite.command).map(w=>[w.chip,w.slot,w.nibble]),
    Array.from({length:12},(_,j)=>[3,'V',1+3*j]));
  const overwrite=secondSwap.find(e=>e.ip===0xE7);
  assert.deepEqual([overwrite.slot,raw(overwrite.m),raw(overwrite.r,0)],['X',p,u]);
  swap(r,overwrite.command,['X']);
  assert.deepEqual(visible(at(3)),[u,u,p,marker]);
  assert.deepEqual(lower(at(3)),['1F'+u.slice(2),u,q,w]);
  assert.deepEqual(visible(at(4)),[u,p,marker,u],
    'F comma rotates left; late formatting leaves the first X unchanged here');
  assert.deepEqual(visible(done),[q,q,marker,'14'+u.slice(2)]);
  assert.deepEqual(lower(done),['1F'+u.slice(2),u,q,w]);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((n,i)=>i===0?v:n));
  for(const n of ms.slice(4))assert.equal(r.after[n],r.before[n]);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.ok(ww.filter(w=>[36,37,39,40].includes(w.nibble)).every(w=>w.before===w.value));
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  const protectedWords=[...r.afterRegisters,...ms.map(n=>r.after[n].slice(2))];
  assert.ok(!protectedWords.includes(p),'original P0 is absent from all 23 protected output words');
  return {phase:0,readU:reads[0].command,writeUtoV:vwrite.command,
    transientPtoXOverwritten:overwrite.command,oldP0:p,
    protectedPermutation:false,other14RegistersHeld:true,upperMsHeld:true,programHeld:true};
}
if(require.main===module) {
  const r=probe.run(options);
  console.log('PASS rejected LastX permutation:',JSON.stringify(check(r)));
  r.traced.events.length=r.traced.writes.length=0;
}
module.exports={options,check};
