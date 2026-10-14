#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {run,runPrepared,finish}=require('./probe_ms_direct_v.cjs');
const {prepare}=require('./probe_a8_marker_route.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const raw=m=>Array.from({length:12},(_,i)=>m[34-3*i].toString(16).toUpperCase()).join('');
const negative=['111','222','-1.2345678E-42','-8.7654321E-17'];
const extreme=['-1.2345678E-42','-9.8765432E99','-1E-99','9.8765432E99'];
const cases=[{},...[0,1,2].map(phaseOffset=>({values:negative,phaseOffset})),
  ...[0,1,2].map(phaseOffset=>({values:extreme,phaseOffset})),
  {values:negative,settleFrames:12},{values:['111','222','0','0']},
  {values:['111','222','12345678','-1E-99']},
  {values:['111','222','9.8765432E99','-9.8765432E99']}];

function check(r) {
  const es=r.traced.events;
  assert.equal(r.beforeRegisters[3],'000000000000','explicit zero P3 prerequisite');
  assert.equal(r.afterRegisters[2],r.before.V.slice(2),'all 12 V tetras -> P2');
  assert.deepEqual(r.after,r.before,'all 112 Ms tetras remain unchanged');
  for(let i=0;i<15;i++) if(i!==2) assert.equal(r.afterRegisters[i],r.beforeRegisters[i]);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.deepEqual(r.traced.primitives,[]);
  assert.ok(es.every(e=>e.ip!==0xC9),'no temporary program-lane swap');
  assert.deepEqual(r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&
    w.nibble%3===1&&w.before!==w.value),[],
    'not even an intermediate changed write to any Ms numeric/service tetra');
  const save=es.find(e=>e.stage==='save-v-direct');
  assert.deepEqual(['X','Y','Z','T'].map(s=>raw(save.ring[s])),
    ['000000000000','000000000000','9990FFFFFFF0','000000000000']);
  const eeAt=es.findIndex(e=>e.stage==='save-v-direct'&&e.ip===0xEE);
  assert.equal(es[eeAt].slot,'V');assert.equal(es[eeAt].raw,r.before.V.slice(2));
  assert.equal(es[eeAt+1].ip,0xAB);
  const d4=es.find((e,i)=>i>eeAt&&e.stage==='save-v-direct'&&e.ip===0xD4);
  assert.ok(d4);assert.equal(d4.slot,'W','P2 is in the M1 lane of W');
  for(const stage of ['lift-marker-1','lift-marker-2','remove-marker-1','remove-marker-2']) {
    const at=es.findIndex(e=>e.stage===stage&&e.ip===0xE7);
    const b=checkSwapBlock(r,at,4);
    assert.deepEqual(b.body.map(e=>e.slot),['X','Y','Z','T']);
    assert.deepEqual(Array.from({length:12},(_,i)=>b.body[0].r[3*i]),Array(12).fill(0));
  }
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.equal(r.calc.displayText(),'5,');aligned(r.calc);
  assert.deepEqual(fullMsPages(r.calc),r.before);
  assert.deepEqual(registers(r.calc),r.afterRegisters);
  assert.deepEqual(program(r.calc),r.beforeProgram);
}

let firstDigest,firstOptions;
for(const options of cases) {
  const r=run(options);firstDigest??=digest(r.calc);firstOptions??=r.options;
  check(r);
  console.log('PASS:',JSON.stringify(options),
    'full V -> P2; no changed Ms tetra at any time; other registers/program/arithmetic intact.');
}

const plain=prepare(firstOptions);finish(plain,firstOptions);plain.runFrames(3);aligned(plain);
assert.equal(digest(plain),firstDigest);
console.log('PASS: observed/unobserved whole reference state agrees:',firstDigest);
for(let iteration=0;iteration<3;iteration++) {
  const r=runPrepared(plain,{phaseOffset:iteration});check(r);
  console.log('PASS: repeat',iteration+1,'without setup/reset/import, P2 already nonzero.');
}

// The direct-store search starts at Z, not Y: one zero lift is insufficient.
const tooEarly=run({markerLifts:1});
const source=tooEarly.traced.events.find(e=>e.stage==='save-v-direct'&&e.ip===0xEE);
assert.equal(source.slot,'X');assert.equal(tooEarly.afterRegisters[2],'000000000000');
assert.notEqual(tooEarly.afterRegisters[2],tooEarly.before.V.slice(2));
console.log('PASS: negative control: a marker in Y reads X, not V.');
console.log('NOT K1: this is one nondestructive numeric-word read, not an eight-word exchange.');
