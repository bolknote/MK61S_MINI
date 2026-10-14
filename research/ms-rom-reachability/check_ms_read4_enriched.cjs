#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const old=require('./probe_a8_ms_readout_zero.cjs');
const push=require('./probe_ms_p9_push.cjs');
const p=require('./probe_ms_wq_repair.cjs');
const {check}=require('./check_ms_wq_repair.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
// The old fixture gives nonzero P7/P8, but also noncanonical 600 headers in
// W/Q. Replace only the first four words using the separately tested writer.
const seeded=old.run();old.runPrepared(seeded.calc);const c=seeded.calc;
const before=fullMsPages(c);
const values=['444','333','-1.2345678E-42','-1E-99'];
for(let i=0;i<4;i++){inputLiteral(c,values[i]);c.pressSequence(['X→П',String(4+i)]);}
push.fill4FromRegisters(c);aligned(c);
assert.equal(fullMsPages(c).P7,before.P7);assert.equal(fullMsPages(c).P8,before.P8);
// The output registers must not already contain the answers.
for(const n of [4,5,6,7,9]){inputLiteral(c,String(101+n));c.pressSequence(['X→П',String(n)]);}
aligned(c);
const r=p.runPrepared(c,{restore:true});
assert.notEqual(r.before.P7,'00000000000000');assert.notEqual(r.before.P8,'00000000000000');
assert.ok([4,5,6,7].every((n,i)=>r.beforeRegisters[n]!==r.before[['U','V','W','Q'][i]].slice(2)));
check(r);
console.log('PASS: four-word readout restores all Ms with native nonzero P7/P8; output registers did not contain the answers beforehand.');
