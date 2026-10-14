#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_writer_single_pointer.cjs');
const {checkUpperPush}=require('./check_ms_upper_write.cjs');
const {checkExit}=require('./check_ms_zero_reuse.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {ordinaryChecks}=require('./check_ms_upper_read4.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const names=['U','V','W','Q','P7','P8','P9','P10'],upper=names.slice(4);
const zero='000000000000',guard='958912345678',marker='0000F0000000';
const rows=(r,label)=>r.traced.events.filter(e=>e.stage===label);
const at=(r,label)=>{const e=rows(r,label).find(e=>e.ring);assert.ok(e,label);return e;};
function checkStage(r,prefix,next,source,index,{keepP8=false,keepE=true}={}) {
  const start=at(r,prefix+'zero-p0'),begin=at(r,prefix+'prepare-zero-p8'),end=at(r,next);
  const seed=keepP8?raw(begin.ring.marker,0):zero;
  assert.deepEqual(upper.map(n=>raw(begin.ring[n],1,14)),upper.map(n=>raw(start.ring[n],1,14)));
  const lift=checkSwapBlock(r,r.traced.events.findIndex(e=>e.stage===prefix+'shift-0'&&e.ip===0xE7&&e.slot==='U'),4);
  assert.equal(raw(lift.body[0].r,0),seed);assert.equal(raw(lift.after.ring.V),marker);
  const push=checkUpperPush(r,prefix+'upper-after-0',source,{sourceIndex:index});
  assert.equal(push.entry,'P9','only the checked P6 pointer candidate is allowed');
  const exit=checkExit(r,prefix);assert.equal(exit.post,'U');assert.deepEqual(exit.zeros,['P8','P8','P8']);
  const markerRead=rows(r,prefix+'upper-after-4').find(e=>e.ip===0xD6);
  assert.equal(markerRead.slot,'P10','the marker reader must not consume the retained E payload');
  assert.deepEqual(upper.map(n=>raw(end.ring[n])),[source,...upper.slice(0,3).map(n=>raw(begin.ring[n]))]);
  assert.deepEqual(names.slice(0,4).map(n=>raw(end.ring[n])),[seed,guard,raw(begin.ring.U),raw(begin.ring.V)]);
  const kept=['V','Q','X1','X','Z',...(keepE?['T']:[]),...(keepP8?['marker']:[])];
  assert.ok(r.traced.writes.filter(w=>w.command>=start.command&&w.command<end.command&&kept.includes(w.slot)&&w.nibble%3===0&&w.nibble<=33)
    .every(w=>w.value===w.before),'ordinary payloads survive every scratch operation and ROM suffix');
  for(const n of ['Z',...(keepE?['T']:[])])assert.deepEqual(r.traced.writes.filter(w=>w.command>=start.command&&w.command<end.command&&w.slot===n&&w.nibble%3===0&&w.nibble<=33),[],
    'no write at all to retained ordinary '+n);
  assert.ok(r.traced.writes.filter(w=>w.command>=begin.command&&w.command<end.command&&upper.includes(w.slot)&&w.nibble%3===1&&w.value!==w.before)
    .every(w=>w.command>=push.start&&w.command<push.end));
  return {push:push.entry,marker:markerRead.slot,...exit};
}
function check(r) {
  const index=r.options.sourceIndex??10,source=r.beforeRegisters[index];
  const path=checkStage(r,'','done',source,index,r.options);
  const seed=r.options.keepP8?r.beforeRegisters[8]:zero;
  const expected=[seed,guard,r.before.U.slice(2),r.before.V.slice(2),source,...upper.slice(0,3).map(n=>r.before[n].slice(2))];
  assert.deepEqual(r.after,Object.fromEntries(names.map((n,i)=>[n,r.before[n].slice(0,2)+expected[i]])));
  assert.deepEqual(r.afterRegisters,[zero,r.beforeRegisters[1],marker,r.beforeRegisters[3],guard,'007000000007',
    '007'+String(index-8).padStart(9,'0'),'007000000009',seed,marker,r.beforeRegisters[10],r.beforeRegisters[11],
    '007000000000',r.beforeRegisters[13],r.options.keepE?r.beforeRegisters[14]:'000020000000']);
  ordinaryChecks(r);return path;
}
function release(r){r.traced.events.length=0;r.traced.writes.length=0;}
const cases=[{keepE:true},{keepE:true,phaseOffset:1,sourceIndex:14},{keepE:true,phaseOffset:2,sourceIndex:8,keepP8:true,source:'-4.3210987E31'},
  {keepE:true,sourceIndex:14,source:'0',payloadD:'1.2345678E99',settleFrames:12,markerFrames:8}];
function main() {
  let first;
  for(const o of cases) {const r=p.run(o);first??=digest(r.calc);console.log('PASS',JSON.stringify(o),JSON.stringify(check(r)));release(r);}
  const plain=p.prepare(cases[0]);p.finish(plain,cases[0]);plain.runFrames(3);aligned(plain);assert.equal(digest(plain),first);
  console.log('PASS observed/unobserved',first);
  const repeat=p.runPrepared(plain,cases[0]);check(repeat);release(repeat);console.log('PASS repeat without resetting or preparing D/E.');
  console.log('LIMIT: native-tested one-sided writer entry; not arbitrary keyboard timing, whole Ms restoration or K1.');
}
if(require.main===module)main();
module.exports={checkStage,check,cases};
