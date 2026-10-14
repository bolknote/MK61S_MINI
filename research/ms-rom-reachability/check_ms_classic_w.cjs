#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const w=require('./probe_ms_classic_w.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const raw=m=>Array.from({length:12},(_,i)=>m[34-3*i].toString(16).toUpperCase()).join('');

function check(r) {
  const es=r.traced.events,destination=r.options.destination??1;
  assert.equal(r.afterRegisters[destination],r.before.W.slice(2));
  assert.deepEqual(r.after,r.before);assert.deepEqual(r.afterProgram,r.beforeProgram);
  for(let i=0;i<15;i++) if(i!==destination)assert.equal(r.afterRegisters[i],r.beforeRegisters[i]);
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  assert.deepEqual(r.traced.writes.filter(x=>Object.hasOwn(r.before,x.slot)&&x.nibble%3===1&&x.before!==x.value),[]);
  const start=es.find(e=>e.stage==='save-v-direct');
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(start.ring[n])),
    ['000000000000','000000000000','000000000000','0000F0000000']);
  const at=es.findIndex(e=>e.stage==='save-v-direct'&&e.ip===0xEE);
  assert.ok(at>=0);const source=es[at];assert.equal(source.slot,'W');
  assert.equal(source.raw,r.before.W.slice(2));
  assert.deepEqual(es.slice(at-4,at+4).map(e=>[e.ip,e.slot]),
    [[0xE5,'Z'],[0xE5,'T'],[0xE6,'U'],[0xED,'V'],[0xEE,'W'],[0xAB,'Q'],[0xAD,'P7'],[0xA4,'P8']]);
  assert.deepEqual(es[at+1].r.filter((_,i)=>i%3===0).slice(0,12),
    Array.from({length:12},(_,i)=>source.m[1+3*i]));
  const writers=es.filter(e=>e.stage==='save-v-direct'&&e.ip===0xD4);
  assert.equal(writers.length,1);
  if(destination===1)assert.equal(writers[0].slot,'V');
  for(const stage of ['lift-marker-1','lift-marker-2','lift-marker-3','remove-marker-1']) {
    const pos=es.findIndex(e=>e.stage===stage&&e.ip===0xE7&&e.s1===8&&e.sp[0]===0xA8);
    const block=checkSwapBlock(r,pos,4);
    assert.deepEqual(block.body.map(e=>e.slot),['X','Y','Z','T']);
    assert.deepEqual(Array.from({length:12},(_,i)=>block.body[0].r[3*i]),Array(12).fill(0));
  }
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.equal(r.calc.displayText(),'5,');aligned(r.calc);
  assert.deepEqual(fullMsPages(r.calc),r.before);assert.deepEqual(registers(r.calc),r.afterRegisters);
  assert.deepEqual(program(r.calc),r.beforeProgram);
}
function main() {
  const negative=['111','-1.2345678E-42','-9.8765432E99','12345678'];
  const extreme=['-1.2345678E-42','-9.8765432E99','-1E-99','9.8765432E99'];
  const cases=[{},...[0,1,2].map(phaseOffset=>({values:negative,phaseOffset})),
    ...[0,1,2].map(phaseOffset=>({values:extreme,phaseOffset})),
    {values:negative,settleFrames:12,markerFrames:8},
    {values:['111','0','-1E-99','0']},
    {values:['111','12345678','-1E-99','444']},
    {values:['111','9.8765432E99','-9.8765432E99','9.8765432E99'],stress:true}];
  let firstDigest;
  for(const options of cases) {const r=w.run(options);firstDigest??=digest(r.calc);check(r);
    console.log('PASS:',JSON.stringify(options),'W -> P1, no changed Ms tetra, program/other registers preserved.');}
  const plain=w.prepare();w.finish(plain);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);console.log('PASS: observed/unobserved W reader:',firstDigest);
  for(let i=0;i<3;i++) {check(w.runPrepared(plain,{phaseOffset:i}));
    console.log('PASS: W repeat',i+1,'after arithmetic without initialization.');}
  plain.pressSequence(['В/О','С/П']).runFrames(12);aligned(plain);
  assert.equal(plain.displayText(),'5,');assert.equal(plain.programCounter(),'05');
  console.log('PASS: preserved user program runs and returns 5.');
  const old=require('./probe_a8_ms_readout_zero.cjs');const seeded=old.run();old.runPrepared(seeded.calc);
  const enriched=w.runPrepared(seeded.calc);assert.notEqual(enriched.before.P7,'00000000000000');
  assert.notEqual(enriched.before.P8,'00000000000000');check(enriched);
  console.log('PASS: W reader preserves native nonzero Ms P7/P8.');
  for(const stores of [1,2]) {
    const failed=w.run({values:['111','-1.2345678E-42','-9.8765432E99','-1E-99'],phaseOffset:2,stores});
    assert.equal(failed.afterRegisters[1],'000000000000');
    assert.notEqual(failed.afterRegisters[1],failed.before.W.slice(2));
    assert.deepEqual(failed.after,failed.before);assert.deepEqual(failed.afterProgram,failed.beforeProgram);
    const source=failed.traced.events.find(e=>e.stage==='save-v-direct'&&e.ip===0xEE);
    assert.equal(source.slot,'X');
    assert.ok(failed.traced.events.some(e=>e.stage==='save-v-direct'&&e.ip===0x9C&&e.slot==='U'&&e.nextIp===0x9E));
    console.log('PASS: negative control,',stores,'store(s): U with negative exponent redirects source to X, not W.');
  }
  const shifted=require('./probe_ms_shifted_swap.cjs');
  const failedSwap=shifted.run({values:['111','-1.2345678E-42','-9.8765432E99','-1E-99'],
    postSwap:[['П→X','3'],['П→X','3'],['F',',']]});
  assert.equal(failedSwap.afterRegisters[9],failedSwap.before.W.slice(2));
  assert.deepEqual(failedSwap.after,{...failedSwap.before,V:failedSwap.before.W});
  assert.deepEqual(failedSwap.afterProgram,failedSwap.beforeProgram);
  assert.ok(failedSwap.traced.events.some(e=>e.stage==='shifted-swap'&&e.ip===0xE7&&e.slot==='V'));
  console.log('PASS: negative control: IK1303 reads W correctly, but its following formatter overwrites V before cleanup.');
  console.log('CONDITIONAL W reader: tested U with nonnegative exponent; NOT a general third read or K1.');
}
if(require.main===module)main();
module.exports={check};
