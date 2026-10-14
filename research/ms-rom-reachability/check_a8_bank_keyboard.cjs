#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {run}=require('./probe_a8_bank_keyboard.cjs');
const {MK61,aligned}=require('./probe_ee_ring_source.cjs');
const {prepareCombined,finishCombined}=require('./check_ac_signature_keyboard.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const word=page=>page.slice(1,36).filter((_,i)=>i%3===0);
const cases=[
  {},
  {values:['111','222','333','444']},
  {values:['-1.2345678E-42','8.7654321E17','-23456789','34567891']},
  {phaseOffset:1},
  {phaseOffset:2},
  {settleFrames:10},
];
let first;
for(const options of cases) {
  const result=run(options);first??=result;
  const entries=result.report.entries.filter(e=>e.complete);
  assert.ok(entries.length>=2,'observe repeated complete eight-swap blocks');
  assert.deepEqual(entries[0].body.filter(e=>e.ip===0xA8).map(e=>e.slot),
    ['W','Q','P7','P8','P9','P10','marker','control']);
  assert.deepEqual(entries[1].body.filter(e=>e.ip===0xA8).map(e=>e.slot),
    ['U','V','W','Q','P7','P8','P9','P10']);
  const begin=result.traced.events.find(e=>e.command===entries[0].gate.command+1);
  const end=result.traced.events.find(e=>e.command===begin.command+8);
  assert.deepEqual(word(end.ring.P7),word(begin.ring.Q),
    'an entire former Q word reaches P7, beyond the established four-word writer');
  const writes=result.traced.writes.filter(w=>
    w.command>=begin.command&&w.command<end.command);
  assert.equal(writes.length,96,'exactly eight times twelve physical ring writes');
  assert.ok(writes.every(w=>w.chip===3&&w.ip===0xA8&&w.nibble%3===1&&w.nibble<37));
  console.log('PASS:',JSON.stringify(options),entries.length,
    'complete A8 blocks; all 630 ring tetras checked per block; Q -> P7 exact.');
}
const plain=new MK61();
for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
  plain[name]=()=>{throw new Error('Forbidden state setter: '+name);};
prepareCombined({calc:plain,counter:1,lowDigit:1});finishCombined(plain);aligned(plain);
assert.equal(digest(plain),digest(first.calc),'observers must not change full calculator state');
console.log('PASS: instrumented and uninstrumented states agree:',digest(plain));
console.log('NOT K1: first block overwrites marker/control, later blocks continue, no safe return claimed.');
