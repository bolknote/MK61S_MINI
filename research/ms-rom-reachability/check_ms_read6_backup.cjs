#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_read6_backup.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const marker='0000F0000000';
const outputs=[[4,'U'],[10,'V'],[6,'W'],[7,'Q'],[0,'P7'],[1,'P8']];
function check(r,{upperP8=r.before.P7.slice(2)}={}) {
  const es=r.traced.events;
  const expected=r.beforeRegisters.slice();
  for(const [n,word] of outputs)expected[n]=r.before[word].slice(2);
  expected[5]='007000000001';expected[8]='000000000000';expected[9]=marker;expected[12]='000010000000';
  assert.deepEqual(r.afterRegisters,expected,'all six original words and only declared output/scratch registers');
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  assert.ok(es.every(e=>e.ip!==0xC9));
  const handoff=es.find(e=>e.stage==='prepare-zero-p8');
  assert.ok(handoff?.ring);
  for(const word of Object.keys(r.before))
    assert.equal(raw(handoff.ring[word],1,14),r.before[word],'lower backup restored Ms before upper entry: '+word);
  for(const [slot,word] of [['P7','U'],['X1','V'],['P9','W'],['P10','Q']])
    assert.equal(raw(handoff.ring[slot],0),r.before[word].slice(2));
  assert.equal(raw(handoff.ring.P8,0),'000010000000');
  assert.equal(raw(handoff.ring.Y,0),'000010000000');
  const request=es.find(e=>e.stage==='upper-swap'&&e.ip===0xA2&&e.slot==='V');
  assert.ok(request);
  assert.deepEqual(r.after,{...r.before,
    U:r.before.U.slice(0,2)+'000000000000',V:r.before.V.slice(0,2)+marker,
    W:r.before.W.slice(0,2)+'1F'+request.r[27].toString(16).toUpperCase()+r.before.U.slice(5),
    Q:r.before.Q.slice(0,2)+r.before.V.slice(2),
    P7:r.before.P7.slice(0,2)+r.before.P8.slice(2),P8:r.before.P8.slice(0,2)+upperP8});
  for(const [stage,word,slot] of [['read-0','P7','U'],['upper-after-0','P8','V']]) {
    const source=es.find(e=>e.stage===stage&&e.ip===0xEE&&e.slot==='P7');
    assert.ok(source);assert.equal(source.raw,r.before[word].slice(2));
    const store=es.find(e=>e.stage===stage&&e.command>source.command&&e.ip===0xD4&&e.slot===slot);
    assert.ok(store);
    const writes=r.traced.writes.filter(w=>w.command===store.command);
    assert.equal(writes.length,12);
    assert.ok(writes.every(w=>w.chip===3&&w.slot===slot&&w.nibble%3===0&&w.nibble<36));
    for(const w of writes)assert.equal(w.value,source.m[w.nibble+1]);
  }
  const changed=r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.ok(changed.every(w=>!['P9','P10'].includes(w.slot)&&w.nibble<=34),
    'the last two Ms words and all service fields stay intact throughout');
}
function main() {
  const cases=[...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true})),
    ...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true,
      values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
      upperValues:['-1E-99','-8.7654321E-17','333','444']})),
    {settleFrames:12,markerFrames:8,stress:true},
    {phaseOffset:2,stress:true,values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
      upperValues:['6.5432109E-23','-8.7654321E-17','333','444']}];
  let firstDigest;
  for(const o of cases) {
    const r=p.run(o);check(r);firstDigest??=digest(r.calc);
    console.log('PASS:',JSON.stringify(o),'six exact Ms backups in one uninterrupted keyboard run; program preserved.');
  }
  const plain=p.prepare(cases[0]);p.finish(plain,cases[0]);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);
  console.log('PASS: observed/unobserved full core state:',firstDigest);
  console.log('CONDITIONAL: original U exponent nonnegative; P3=0. Ms is NOT restored; no safe exit/full K1 claimed.');
}
if(require.main===module)main();
module.exports={check};
