#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {run}=require('./probe_a8_single_keyboard.cjs');
const {MK61,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');

const direct=new MK61();
direct.pressSequence(['БП','В↑','0']);
assert.equal(direct.ik1302.r[31]+16*direct.ik1302.r[34],0xE0);
console.log('PASS: ordinary keys БП, В↑, 0 select raw PC E0. This alone is not a ROM invocation.');

// Each variation tests one proposed source of the saved value. These are
// negative concrete controls, not an exhaustive keyboard reachability proof.
const cases=[
  [{middle:'clear'},5],
  [{middle:'clear',lastDigit:7},5],
  [{middle:'clear',ending:'condition7'},5],
  [{middle:'clear',prefixNops:2},5],
  [{middle:'program7'},9],
  [{middle:'manual7'},5],
];
for(const [options,expectedSaved] of cases) {
  const result=run(options);
  const ac=result.traced.events.find(e=>e.ip===0xAC&&e.stage==='recall'&&e.pc===0xE0);
  assert.ok(ac,'native PC E0 and the subsequent AC must actually be reached');
  assert.equal(ac.st35,expectedSaved);
  assert.equal(result.singles.length,0,'the required saved 7 was not prepared');
  assert.deepEqual(result.traced.primitives,[]);
  aligned(result.calc);
  assert.ok(Object.values(fullMsPages(result.calc)).every(w=>w==='0'.repeat(14)),
    'these rejected preparations preserve every Ms tetra from reset');
  console.log('PASS:',JSON.stringify(options),'AC at E0, saved ST35='+expectedSaved+
    '; no single-A8 entry and Ms unchanged.');
}
console.log('No keyboard route to the short A8 exchange is claimed.');
