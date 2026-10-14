#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {run,runPrepared,prepare,finish}=require('./probe_ms_classic_v.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const raw=m=>Array.from({length:12},(_,i)=>m[34-3*i].toString(16).toUpperCase()).join('');
const negative=['111','222','-1.2345678E-42','-1E-99'];
const extreme=['-1.2345678E-42','-9.8765432E99','-1E-99','9.8765432E99'];
const cases=[{},...[0,1,2].map(phaseOffset=>({values:negative,phaseOffset})),
  ...[0,1,2].map(phaseOffset=>({values:extreme,phaseOffset})),
  {values:negative,settleFrames:12,markerFrames:8},
  {values:['111','222','0','0']},{values:['111','222','12345678','-1E-99']},
  {values:['111','222','9.8765432E99','-9.8765432E99'],stress:true}];

function check(r) {
  const es=r.traced.events;
  assert.equal(r.afterRegisters[2],r.before.V.slice(2));
  assert.deepEqual(r.after,r.before,'ALL 112 Ms tetras unchanged, including marker construction');
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  for(let i=0;i<15;i++) if(i!==2) assert.equal(r.afterRegisters[i],r.beforeRegisters[i]);
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  assert.deepEqual(r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&
    w.nibble%3===1&&w.before!==w.value),[],
    'no changed Ms numeric/service tetra at ANY point of the reading operation');
  const at=es.find(e=>e.stage==='save-v-direct');
  assert.deepEqual(['X','Y','Z','T'].map(s=>raw(at.ring[s])),
    ['000000000000','000000000000','0000F0000000','000000000000']);
  const source=es.find(e=>e.stage==='save-v-direct'&&e.ip===0xEE);
  assert.equal(source.slot,'V');assert.equal(source.raw,r.before.V.slice(2));
  const writes=es.filter(e=>e.stage==='save-v-direct'&&e.ip===0xD4);
  assert.equal(writes.length,1);assert.equal(writes[0].slot,'W');
  for(const stage of ['lift-marker-1','lift-marker-2','remove-marker-1','remove-marker-2']) {
    const pos=es.findIndex(e=>e.stage===stage&&e.ip===0xE7&&e.s1===8&&e.sp[0]===0xA8);
    const block=checkSwapBlock(r,pos,4);
    assert.deepEqual(block.body.map(e=>e.slot),['X','Y','Z','T']);
    assert.deepEqual(Array.from({length:12},(_,i)=>block.body[0].r[3*i]),Array(12).fill(0));
  }
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.equal(r.calc.displayText(),'5,');aligned(r.calc);
  assert.deepEqual(fullMsPages(r.calc),r.before);
  assert.deepEqual(registers(r.calc),r.afterRegisters);
  assert.deepEqual(program(r.calc),r.beforeProgram);
}

function checkEnrichedMs() {
  const old=require('./probe_a8_ms_readout_zero.cjs');
  const first=old.run(),second=old.runPrepared(first.calc);
  assert.notEqual(second.after.P7,'00000000000000');
  assert.notEqual(second.after.P8,'00000000000000');
  const r=runPrepared(second.calc);check(r);
  console.log('PASS: existing calculator with native nonzero Ms P7/P8 and old setup constants: all Ms unchanged.');
}

function main() {
let firstDigest,firstOptions;
for(const options of cases) {
  const r=run(options);firstDigest??=digest(r.calc);firstOptions??=options;check(r);
  if(options.stress) assert.ok(r.beforeRegisters.every((v,i)=>i===3||v!=='000000000000'));
  console.log('PASS:',JSON.stringify(options),
    'standalone V -> P2; all Ms and other registers/program preserved, arithmetic 5.');
}
const plain=prepare(firstOptions);finish(plain,firstOptions);plain.runFrames(3);aligned(plain);
assert.equal(digest(plain),firstDigest);
console.log('PASS: full observed/unobserved states agree:',firstDigest);
for(let i=0;i<3;i++) {const r=runPrepared(plain,{phaseOffset:i});check(r);
  console.log('PASS: standalone repeat',i+1,'after arithmetic, without initialization or saved-state import.');}
// The preserved user program is executable, not merely byte-identical.
plain.pressSequence(['В/О','С/П']).runFrames(12);aligned(plain);
assert.equal(plain.displayText(),'5,');assert.equal(plain.programCounter(),'05');
assert.deepEqual(fullMsPages(plain),fullMsPages(prepare(firstOptions)));
console.log('PASS: preserved nonempty program runs and returns 5.');

const early=run({lifts:1});
assert.equal(early.traced.events.find(e=>e.stage==='save-v-direct'&&e.ip===0xEE).slot,'X');
assert.notEqual(early.afterRegisters[2],early.before.V.slice(2));
console.log('PASS: negative control: one lift leaves marker Y, so direct store reads zero X.');
checkEnrichedMs();
console.log('NOT K1: nondestructive V read only; U/W and an eight-word reversible exchange are separate problems.');
}
if(require.main===module)main();
module.exports={check,checkEnrichedMs};
