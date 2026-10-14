#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_wq_repair.cjs');
const {check}=require('./check_ms_wq_repair.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const cases=[...[0,1,2].map(phaseOffset=>({phaseOffset})),
  ...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true,
    values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678']})),
  {values:['12345678','0','-1E-99','0']},
  {values:['0','-1E-99','12345678','-9.8765432E99']},
  {settleFrames:12,markerFrames:8}];
let firstDigest;
for(const o of cases) {
  const r=p.run({...o,restore:true});firstDigest??=digest(r.calc);check(r);
  assert.deepEqual([4,5,6,7].map(n=>r.afterRegisters[n]),['U','V','W','Q'].map(n=>r.before[n].slice(2)));
  console.log('PASS:',JSON.stringify(o),'U/V/W/Q -> P4/P5/P6/P7; ALL Ms restored; only P9 extra scratch.');
}
const plain=p.prepare(),before=fullMsPages(plain);
p.finish(plain,{restore:true});plain.runFrames(3);aligned(plain);
assert.equal(digest(plain),firstDigest);
console.log('PASS: observed/unobserved four-word readout:',firstDigest);
for(let i=0;i<2;i++) {
  const r=p.runPrepared(plain,{restore:true,phaseOffset:i});check(r);
  assert.deepEqual(r.after,before);console.log('PASS: repeated readout',i+1,'without reset.');
}
plain.pressSequence(['В/О','С/П']).runFrames(12);aligned(plain);
assert.equal(plain.displayText(),'5,');assert.equal(plain.programCounter(),'05');
assert.deepEqual(fullMsPages(plain),before);
console.log('PASS: retained program returns 5 and Ms still matches its original state.');
const failed=p.run({restore:true,phaseOffset:1,values:['111','222','333','-1.2345678E-42']});
assert.deepEqual(failed.after,{...failed.before,Q:failed.before.W});
assert.deepEqual(failed.afterProgram,failed.beforeProgram);
console.log('PASS: negative control: negative-exponent U can lose Q; this is NOT a general safe four-word readout.');
console.log('CONDITIONAL: U nonnegative exponent tested. Ms changes transiently and is restored; NOT the eight-word K1 exchange.');
