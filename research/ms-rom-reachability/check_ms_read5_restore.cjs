#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_read5_restore.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const marker='0000F0000000',eraser='958912345678';
const m1Names=['U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T'];
function check(r) {
  assert.deepEqual(r.after,r.before,'all 112 Ms tetras restored at the end');
  const expected=r.beforeRegisters.slice();
  for(const [i,word] of [[0,'P7'],[4,'U'],[5,'V'],[6,'W'],[7,'Q'],[9,'U']]) expected[i]=r.before[word].slice(2);
  expected[2]=eraser;expected[8]='000000000000';
  assert.deepEqual(r.afterRegisters,expected,'five exact outputs and only the declared scratch registers');
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  const es=r.traced.events;assert.ok(es.every(e=>e.ip!==0xC9));
  assert.deepEqual(m1Names.map(n=>raw(es[0].ring[n],0)),r.beforeRegisters);
  const plantAt=es.findIndex(e=>e.stage==='fifth-word/plant-u'&&e.ip===0xE7&&e.slot==='U');
  const planted=checkSwapBlock(r,plantAt,4);
  assert.deepEqual(planted.body.map(e=>e.slot),['U','V','W','Q']);
  assert.equal(raw(planted.body[0].r,0),marker);
  const shiftAt=es.findIndex(e=>e.stage==='fifth-word/shift-0'&&e.ip===0xE7&&e.slot==='U');
  const shifted=checkSwapBlock(r,shiftAt,4);
  assert.equal(raw(shifted.body[0].r,0),'000000000000');
  assert.equal(raw(shifted.after.ring.V),marker);
  assert.equal(raw(shifted.after.ring.Y),marker,'the independently used visible marker survives');
  const loadAt=es.findLastIndex((e,i)=>i<shiftAt&&e.stage==='fifth-word/shift-0'&&e.ip===0xD6);
  assert.deepEqual(es.slice(loadAt,shiftAt+1).map(e=>[e.ip,e.slot]),
    [[0xD6,'marker'],[0xA7,'control'],[0xE5,'X1'],[0xE5,'X'],[0xE5,'Y'],[0xE6,'Z'],[0xE8,'T'],[0xE7,'U']]);
  const readAt=es.findIndex(e=>e.stage==='fifth-word/read-0'&&e.ip===0xEE);
  assert.equal(es[readAt].slot,'P7');assert.equal(es[readAt].raw,r.before.P7.slice(2));
  assert.deepEqual(es.slice(readAt-6,readAt+4).map(e=>[e.ip,e.slot]),
    [[0xE5,'Z'],[0xE5,'T'],[0xE5,'U'],[0xE5,'V'],[0xE6,'W'],[0xED,'Q'],
      [0xEE,'P7'],[0xAB,'P8'],[0xAD,'P9'],[0xA4,'P10']]);
  const storeAt=es.findIndex((e,i)=>i>readAt&&e.stage==='fifth-word/read-0'&&e.ip===0xD4);
  const store=es[storeAt],stored=es[storeAt+1];
  assert.equal(store.slot,'U');assert.equal(stored.ip,0xA5);
  const expectedRing=structuredClone(store.ring);
  for(let i=0;i<12;i++)expectedRing.U[3*i]=es[readAt].m[1+3*i];
  assert.deepEqual(stored.ring,expectedRing,'D4 writes precisely the twelve P7 source tetras to ordinary P0');
  const storeWrites=r.traced.writes.filter(w=>w.command===store.command);
  assert.equal(storeWrites.length,12);assert.ok(storeWrites.every(w=>w.chip===3&&w.slot==='U'&&w.nibble%3===0&&w.nibble<36));
  const eraseLiftAt=es.findIndex(e=>e.stage==='erase-v'&&e.ip===0xE7&&e.slot==='X');
  const lifted=checkSwapBlock(r,eraseLiftAt,4);
  assert.equal(raw(lifted.body[0].r,0),eraser);assert.equal(raw(lifted.after.ring.Z),marker);
  const eraseAt=es.findIndex(e=>e.stage==='erase-v'&&e.ip===0xE7&&e.slot==='V');
  assert.ok(eraseAt>eraseLiftAt);
  const erased=checkSwapBlock(r,eraseAt,1);
  assert.equal(erased.body[0].raw,marker);assert.equal(raw(erased.body[0].r,0),eraser);
  assert.equal(erased.after.ip,0x47);assert.equal(raw(erased.after.ring.V),eraser);
  const restoration=es.find(e=>e.stage==='source-p7');
  for(const n of Object.keys(r.before))assert.notEqual(restoration.ring[n][22],15,'all hidden false markers removed before restoration');
  for(const source of [7,6,5,4]) {
    const at=es.findIndex(e=>e.stage==='restore-p'+source+'/shifted-swap'&&e.ip===0xE7&&e.slot==='U');
    const b=checkSwapBlock(r,at,4);assert.equal(raw(b.body[0].r,0),expected[source]);
  }
  const writes=r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.ok(writes.every(w=>['U','V','W','Q'].includes(w.slot)&&w.nibble<=34),
    'no temporary changed tetra in the four upper Ms words or any service field');
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.equal(r.calc.displayText(),'5,');aligned(r.calc);
  assert.deepEqual(fullMsPages(r.calc),r.before);assert.deepEqual(registers(r.calc),expected);assert.deepEqual(program(r.calc),r.beforeProgram);
}
function main() {
  const stressValues=['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'];
  const cases=[...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true})),
    ...[0,1,2].map(phaseOffset=>({phaseOffset,enriched:true,stress:true,values:stressValues,
      upperValues:['-1E-99','-8.7654321E-17','333','444']})),
    {enriched:true,settleFrames:12,markerFrames:8},
    {values:['12345678','0','-1E-99','0']}];
  let firstDigest,firstOptions;
  for(const options of cases) {
    const r=p.run(options);firstDigest??=digest(r.calc);firstOptions??=options;check(r);
    if(options.enriched)assert.notEqual(r.before.P7,'00000000000000');
    console.log('PASS:',JSON.stringify(options),'five exact words read; all Ms restored; upper Ms never changed; program preserved.');
  }
  const plain=p.prepare(firstOptions);p.finish(plain,firstOptions);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);console.log('PASS: observed/unobserved full state:',firstDigest);
  for(const phaseOffset of [1,2]) {check(p.runPrepared(plain,{phaseOffset}));console.log('PASS: repeated five-word read without reset, phase',phaseOffset);}
  const words=fullMsPages(plain),regs=registers(plain),code=program(plain);
  plain.pressSequence(['В/О','С/П']).runFrames(12);aligned(plain);
  assert.equal(plain.displayText(),'5,');assert.equal(plain.programCounter(),'05');
  assert.deepEqual(fullMsPages(plain),words);assert.deepEqual(registers(plain),regs);assert.deepEqual(program(plain),code);
  console.log('PASS: preserved user program runs and returns 5.');
  console.log('CONDITIONAL: nonnegative initial U exponent; P3=0; P0/P4..P7 outputs; P2/P8/P9 scratch. NOT full K1.');
}
if(require.main===module)main();
module.exports={check};
