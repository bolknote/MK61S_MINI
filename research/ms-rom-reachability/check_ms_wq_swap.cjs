#!/usr/bin/env node
'use strict';
// A genuine native W/Q exchange, with an explicitly checked U-header clobber.
// It is a useful ROM fragment, NOT an intact-Ms permutation or a full K1.
const assert=require('node:assert/strict');
const p=require('./probe_ms_shifted_swap.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const A=c=>Array.from({length:12},(_,i)=>c.r[i*3]);
const numeric=c=>Array.from({length:12},(_,i)=>c.m[1+i*3]);
const optionsFor=o=>({...o,lifts:3,save:false});

function check(r) {
  const es=r.traced.events;
  const request=es.find(e=>e.stage==='shifted-swap'&&e.ip===0xA2&&e.slot==='T');
  assert.ok(request);assert.deepEqual([request.r[32],request.r[35]],[4,1]);
  const expectedU=r.before.U.slice(0,2)+'1F'+request.r[27].toString(16).toUpperCase()+r.before.U.slice(5);
  assert.deepEqual(r.after,{...r.before,U:expectedU,W:r.before.Q,Q:r.before.W});
  assert.deepEqual(r.afterRegisters,r.beforeRegisters);assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  const msWrites=r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.ok(msWrites.every(w=>(w.slot==='U'&&[28,31,34].includes(w.nibble))||
    (['W','Q'].includes(w.slot)&&w.nibble<=34)));
  const writerAt=es.findIndex(e=>e.stage==='shifted-swap'&&e.otherChips?.[4].ip===0x4E&&e.otherChips[4].slot==='W');
  assert.ok(writerAt>=0);const writer=es[writerAt].otherChips[4];
  const sourceAt=es.findLastIndex((e,i)=>i<writerAt&&e.otherChips?.[4].ip===0x53);
  const source=es[sourceAt].otherChips[4];assert.equal(source.slot,'Q');
  assert.equal(p.raw(source.m),r.before.Q.slice(2));
  assert.deepEqual([source.l,source.s1,...[32,35,41].map(i=>source.r[i])],[1,6,5,0,5]);
  const prefix=es.slice(sourceAt-4,sourceAt).map(e=>e.otherChips[4]);
  assert.deepEqual(prefix.map(c=>[c.ip,c.slot]),[[0x6E,'T'],[0x5E,'U'],[0x50,'V'],[0x52,'W']]);
  assert.equal(prefix[0].r[29],0);assert.equal(prefix[0].m[22],15);
  assert.deepEqual([prefix[1].m[34],prefix[1].m[31]],[1,4]);
  assert.deepEqual(A(writer),numeric(source));assert.equal(p.raw(writer.m),r.before.W.slice(2));
  const pair=es.slice(writerAt,writerAt+3);
  assert.deepEqual(pair.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),[[0x4E,'W'],[0x2A,'Q'],[0x39,'P7']]);
  const expectedRing=Object.fromEntries(Object.entries(pair[0].ring).map(([n,m])=>[n,m.slice()]));
  for(let i=0;i<12;i++){expectedRing.W[1+3*i]=source.m[1+3*i];expectedRing.Q[1+3*i]=writer.m[1+3*i];}
  assert.deepEqual(pair[2].ring,expectedRing,'all 630 ring tetras after the W/Q pair');
  const writes=r.traced.writes.filter(w=>w.command>=pair[0].command&&w.command<pair[2].command);
  assert.equal(writes.length,24);assert.ok(writes.every(w=>w.chip===4&&w.nibble%3===1&&w.nibble<=34&&
    ((w.ip===0x4E&&w.slot==='W')||(w.ip===0x2A&&w.slot==='Q'))));
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.equal(r.calc.displayText(),'5,');aligned(r.calc);
  assert.deepEqual(fullMsPages(r.calc),r.after);assert.deepEqual(registers(r.calc),r.afterRegisters);
  assert.deepEqual(program(r.calc),r.beforeProgram);
}
function main() {
  const ordinary=['111','222','333','444'];
  const cases=[...[0,1,2].map(phaseOffset=>({values:ordinary,phaseOffset})),
    ...[0,1,2].map(phaseOffset=>({values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],phaseOffset})),
    {values:['0','12345678','-1E-99','9.8765432E99'],stress:true},
    {values:['-9.8765432E99','0','-1.2345678E-42','12345678'],settleFrames:12,markerFrames:8},
    {values:['111','222','333','-1.2345678E-42']}];
  let firstDigest,firstMs;
  for(const o of cases){const r=p.run(optionsFor(o));firstDigest??=digest(r.calc);firstMs??=r.before;check(r);
    console.log('PASS:',JSON.stringify(o),'W/Q exchanged; ONLY three upper U tetras may be clobbered; program/registers preserved.');}
  const plain=p.prepare({values:ordinary});p.finish(plain,optionsFor({}));plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);console.log('PASS: observed/unobserved W/Q exchange:',firstDigest);
  const second=p.runPrepared(plain,optionsFor({}));check(second);
  assert.deepEqual([second.after.W,second.after.Q],[firstMs.W,firstMs.Q]);
  console.log('PASS: second exchange restores W/Q, but NOT the original U header.');
  plain.pressSequence(['В/О','С/П']).runFrames(12);aligned(plain);
  assert.equal(plain.displayText(),'5,');assert.equal(plain.programCounter(),'05');
  console.log('PASS: preserved user program runs and returns 5.');
  const failed=p.run(optionsFor({phaseOffset:1}));
  assert.deepEqual(failed.after,{...failed.before,V:'00000000000000'});
  assert.deepEqual(failed.afterProgram,failed.beforeProgram);
  assert.ok(!failed.traced.events.some(e=>e.stage==='shifted-swap'&&e.ip===0xA2&&e.slot==='T'));
  assert.ok(failed.traced.events.some(e=>e.stage==='shifted-swap'&&e.ip===0xA3&&e.slot==='control'));
  assert.ok(failed.traced.writes.some(w=>w.ip===0xE9&&w.slot==='V'&&w.before!==w.value));
  console.log('PASS: negative control: negative-exponent U on phase 1 diverts the request to real control and clears V; no W/Q exchange.');
  console.log('NOT K1 and NOT nondestructive: the U-header clobber still needs a restoring writer.');
}
if(require.main===module)main();
module.exports={check,optionsFor};
