#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {run,runPrepared}=require('./probe_a8_ms_readout_zero.cjs');
const {recover,registers,program}=require('./probe_a8_ms_readout.cjs');
const {prepare,finish}=require('./probe_a8_marker_route.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const A=e=>Array.from({length:12},(_,i)=>e.r[3*i]);
const raw=m=>Array.from({length:12},(_,i)=>m[34-3*i].toString(16).toUpperCase()).join('');
const ms=ring=>Object.fromEntries(['U','V','W','Q','P7','P8','P9','P10'].map(s=>
  [s,Array.from({length:14},(_,i)=>ring[s][40-3*i].toString(16).toUpperCase()).join('')]));
const negative=['111','222','333','-1.2345678E-42'];
const minimum=['1','-9.8765432E99','9.8765432E99','-1E-99'];
const cases=[{},...[0,1,2].map(phaseOffset=>({values:negative,phaseOffset})),
  {values:negative,settleFrames:12},
  ...[0,1,2].map(phaseOffset=>({values:minimum,phaseOffset})),
  {values:['-1.2345678E-42','-8.7654321E-17','-9.8765432E-99','9.8765432E99']},
  {values:['111','222','-1.2345678E-42','1.2345678E-42']},
  {values:['111','222','0','0']},
  {values:['111','222','-8.7654321E17','12345678']}];
let firstDigest,firstOptions;const seenInitialReadSlots=new Set(),seenGuards=new Set();
for(const options of cases) {
  const r=run(options),es=r.traced.events;
  firstDigest??=digest(r.calc);firstOptions??=r.options;
  assert.equal(r.beforeRegisters[3],'000000000000','P3 is the explicit zero source');
  assert.equal(r.afterRegisters[9],r.before.U.slice(2),'complete U -> P9');
  assert.equal(r.afterRegisters[2],r.before.V.slice(2),'complete V -> P2');
  for(let i=0;i<15;i++) if(i!==2&&i!==9) assert.equal(r.afterRegisters[i],r.beforeRegisters[i]);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.deepEqual(r.traced.primitives,[]);
  assert.equal(es.filter(e=>e.ip===0xC9).length,0,'not even a temporary program-lane swap');

  const liftStart=es.find(e=>e.stage==='lift-marker-1'),afterLift=es.find(e=>e.stage==='recall');
  assert.deepEqual(ms(afterLift.ring),r.before,'ALL 112 Ms tetras unchanged by the new preparation');
  assert.deepEqual(['X','Y','Z','T'].map(s=>raw(afterLift.ring[s])),
    ['000000000000','9990FFFFFFF0','000000000000','000000000000']);
  const liftStage=r.stages.find(s=>s.label==='lift-marker-1');
  assert.deepEqual([liftStage.pc,liftStage.st35,liftStage.r23],[0xE0,7,0]);
  const eeAt=es.findIndex(e=>e.stage==='lift-marker-1'&&e.ip===0xEE);
  seenInitialReadSlots.add(es[eeAt].slot);
  for(const g of es.filter(e=>e.stage==='lift-marker-1'&&e.ip===0x9C))
    seenGuards.add(g.slot+':'+g.nextIp.toString(16));
  const d6At=es.findIndex((e,i)=>i>eeAt&&e.stage==='lift-marker-1'&&e.ip===0xD6);
  assert.ok(d6At>=0);assert.equal(es[d6At].slot,'Q');
  assert.deepEqual(Array.from({length:12},(_,i)=>es[d6At].m[3*i]),Array(12).fill(0),
    'D6 reads the P3 M1 lane, not the arbitrary earlier M2 word');
  assert.deepEqual(A(es[d6At+1]),Array(12).fill(0));assert.equal(es[d6At+1].ip,0xA7);
  const liftAt=es.findIndex((e,i)=>i>d6At&&e.ip===0xE7);
  const lifted=checkSwapBlock(r,liftAt,4);
  assert.deepEqual(lifted.body.map(e=>e.slot),['X','Y','Z','T']);
  assert.deepEqual(A(lifted.body[0]),Array(12).fill(0));
  assert.deepEqual(ms(lifted.after.ring),ms(liftStart.ring));

  const uAt=es.findIndex(e=>e.stage==='recall'&&e.ip===0xE7&&e.slot==='U'&&e.s1===7);
  assert.ok(uAt>=0);assert.equal(es[uAt].raw,r.before.U.slice(2));
  checkSwapBlock(r,uAt,1);
  const uLiftAt=es.findIndex((e,i)=>i>uAt&&e.ip===0xE7&&e.slot==='X'&&e.s1===8);
  const uLift=checkSwapBlock(r,uLiftAt,4);
  assert.equal(raw(uLift.after.ring.X),r.before.U.slice(2));
  const vAt=es.findIndex(e=>e.stage==='read-v-remove-marker'&&e.ip===0xEE&&e.slot==='V');
  assert.ok(vAt>=0);assert.equal(es[vAt].raw,r.before.V.slice(2));
  const vLiftAt=es.findIndex((e,i)=>i>vAt&&e.ip===0xE7&&e.slot==='X'&&e.s1===8);
  const vLift=checkSwapBlock(r,vLiftAt,4);
  assert.equal(raw(vLift.after.ring.X),r.before.V.slice(2));
  assert.equal(raw(vLift.after.ring.Y),r.before.U.slice(2));
  for(const s of ['X','Y','Z','T']) assert.notEqual(vLift.after.ring[s][22],15);
  const saveV=es.find(e=>e.stage==='save-v'),done=es.find(e=>e.stage==='done');
  assert.deepEqual(ms(done.ring),ms(saveV.ring));
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.equal(r.calc.displayText(),'5,');aligned(r.calc);
  assert.deepEqual(registers(r.calc),r.afterRegisters);
  assert.deepEqual(program(r.calc),r.beforeProgram);
  assert.deepEqual(fullMsPages(r.calc),r.after);
  console.log('PASS:',JSON.stringify(options),'zero lift preserves Ms; U/V full readout; four swap blocks checked on all 630 tetras; program/registers/arithmetic intact.');
}
assert.ok(seenInitialReadSlots.has('X')&&seenInitialReadSlots.has('W'));
assert.ok(seenGuards.has('U:9e')&&seenGuards.has('control:9e'));
console.log('PASS: actual false-control acceptance and ordinary control both converge to the same zero lift.');
const plain=prepare(firstOptions);finish(plain,firstOptions);recover(plain,firstOptions);plain.runFrames(3);aligned(plain);
assert.equal(digest(plain),firstDigest);
console.log('PASS: observed/unobserved full reference states agree:',firstDigest);

// Reuse the same calculator and constants after normal arithmetic. Later
// iterations have nonzero P7/P8 in Ms, unlike a fresh four-word fixture.
for(let iteration=0;iteration<4;iteration++) {
  plain.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.equal(plain.displayText(),'5,');aligned(plain);
  const repeated=runPrepared(plain,{phaseOffset:iteration%3});
  assert.equal(repeated.afterRegisters[9],repeated.before.U.slice(2));
  assert.equal(repeated.afterRegisters[2],repeated.before.V.slice(2));
  assert.deepEqual(repeated.afterProgram,repeated.beforeProgram);
  assert.ok(repeated.traced.events.every(e=>e.ip!==0xC9));
  for(let i=0;i<15;i++) if(i!==2&&i!==9)
    assert.equal(repeated.afterRegisters[i],repeated.beforeRegisters[i],'unrelated reused register '+i);
  console.log('PASS: repeat',iteration+1,'without setup/reset/import; previous Ms P7/P8:',
    repeated.before.P7,repeated.before.P8);
}

const oldEnter=run({values:negative,markerLift:'enter'});
assert.notEqual(oldEnter.afterRegisters[9],oldEnter.before.U.slice(2));
const oldLastX=run({values:negative,markerLift:'last-x',phaseOffset:1});
assert.equal(oldLastX.afterRegisters[9],oldLastX.before.U.slice(2));
assert.equal(oldLastX.afterRegisters[2],oldLastX.before.U.slice(2));
assert.notEqual(oldLastX.afterRegisters[2],oldLastX.before.V.slice(2),
  'the failed last-X preparation duplicates U instead of reading V');
console.log('PASS: neither ordinary ENTER nor last-X alone fixes all three initial phases.');
const redundantAuto=run({values:minimum,autoRecovery:true});
const firstC9=redundantAuto.traced.events.find(e=>e.ip===0xC9);
assert.ok(firstC9);assert.equal(firstC9.stage,'auto-readout');
assert.equal(redundantAuto.stages.find(s=>s.label==='recall').display,'-1,       -99');
assert.notDeepEqual(redundantAuto.afterProgram,redundantAuto.beforeProgram);
console.log('PASS: redundant old F AVT recovery damages the program AFTER U=-1E-99 was already correctly read.');
console.log('NOT K1: two-word readout, not a reversible eight-word exchange; U is cleared and a later block shifts other Ms words.');
