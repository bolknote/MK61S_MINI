#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {run,runPrepared,finish}=require('./probe_ms_classic_uv.cjs');
const {prepare}=require('./probe_ms_classic_v.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {digest}=require('./check_c8_keyboard.cjs');

function check(r) {
  assert.equal(r.afterRegisters[9],r.before.U.slice(2));
  assert.equal(r.afterRegisters[2],r.before.V.slice(2));
  assert.deepEqual(r.after,r.before);assert.deepEqual(r.afterProgram,r.beforeProgram);
  for(let i=0;i<15;i++) if(i!==2&&i!==9) assert.equal(r.afterRegisters[i],r.beforeRegisters[i]);
  assert.deepEqual(r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&
    w.nibble%3===1&&w.before!==w.value),[]);
  assert.ok(r.traced.events.every(e=>e.ip!==0xC9));assert.deepEqual(r.traced.primitives,[]);
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.equal(r.calc.displayText(),'5,');aligned(r.calc);
  assert.deepEqual(fullMsPages(r.calc),r.before);assert.deepEqual(registers(r.calc),r.afterRegisters);
  assert.deepEqual(program(r.calc),r.beforeProgram);
}

function main() {
  const negative=['111','222','-1E-99','-1.2345678E-42'];
  const extreme=['-1.2345678E-42','-9.8765432E99','9.8765432E99','-1E-99'];
  const cases=[...[0,1,2].map(phaseOffset=>({values:negative,phaseOffset})),
    ...[0,1,2].map(phaseOffset=>({values:extreme,phaseOffset,order:['v','u']})),
    {values:['111','222','-9.8765432E99','9.8765432E99'],stress:true}];
  let firstDigest;
  for(const options of cases) {
    const r=run(options);firstDigest??=digest(r.calc);check(r);
    console.log('PASS:',JSON.stringify(options),'U -> P9 and V -> P2; no changed Ms tetra; no synchronization between the readers.');
  }
  const plain=prepare(cases[0]);finish(plain,cases[0]);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);
  console.log('PASS: observed/unobserved composed state:',firstDigest);
  for(let i=0;i<2;i++) {const r=runPrepared(plain,{order:i?['v','u']:['u','v'],phaseOffset:i});check(r);
    console.log('PASS: repeated composed read',i+1,'without reset/reinitialization.');}
  const old=require('./probe_a8_ms_readout_zero.cjs');
  const seeded=old.run();old.runPrepared(seeded.calc);
  const r=runPrepared(seeded.calc);assert.notEqual(r.before.P7,'00000000000000');
  assert.notEqual(r.before.P8,'00000000000000');check(r);
  console.log('PASS: composed read preserves native nonzero Ms P7/P8.');
  console.log('NOT K1: two nondestructive reads; an eight-word reverse exchange is still missing.');
}
if(require.main===module)main();
module.exports={check};
