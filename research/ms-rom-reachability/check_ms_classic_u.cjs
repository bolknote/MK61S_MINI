#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {run,runPrepared,prepare,finish}=require('./probe_ms_classic_u.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const A=e=>Array.from({length:12},(_,i)=>e.r[3*i]);
const raw=m=>Array.from({length:12},(_,i)=>m[34-3*i].toString(16).toUpperCase()).join('');

function check(r) {
  const es=r.traced.events;
  assert.equal(r.afterRegisters[9],r.before.U.slice(2),'complete original U -> P9');
  assert.deepEqual(r.after,r.before);assert.deepEqual(r.afterProgram,r.beforeProgram);
  for(let i=0;i<15;i++) if(i!==9) assert.equal(r.afterRegisters[i],r.beforeRegisters[i]);
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  assert.deepEqual(r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&
    w.nibble%3===1&&w.before!==w.value),[],'no changed Ms tetra, even transiently');
  const save=es.find(e=>e.stage==='save-u');
  assert.equal(raw(save.ring.X),r.before.U.slice(2),'U has already reached X before the store');
  const request=es.find(e=>e.stage==='swap-read-u'&&e.ip===0xA2);
  assert.equal(request.slot,'X');assert.equal(request.m[22],15);
  assert.deepEqual([request.r[32],request.r[35],request.r[27],request.r[37],request.r[40]],
    [4,1,0,3,13],'native IK1302 source supplies the symbolic 140 request premise');
  const writerAt=es.findIndex(e=>e.stage==='swap-read-u'&&e.otherChips?.[4].ip===0x4E);
  assert.ok(writerAt>=0);const writer=es[writerAt].otherChips[4];
  assert.equal(writer.slot,'X');assert.equal(writer.m[22],15);
  assert.equal(A(writer).slice().reverse().map(x=>x.toString(16).toUpperCase()).join(''),r.before.U.slice(2));
  const sourceAt=es.findLastIndex((e,i)=>i<writerAt&&e.otherChips?.[4].ip===0x53);
  assert.ok(sourceAt>=0);const source=es[sourceAt].otherChips[4];
  const prefix=es.slice(sourceAt-4,sourceAt).map(e=>e.otherChips[4]);
  assert.deepEqual(prefix.map(e=>[e.ip,e.slot]),[[0x6E,'X'],[0x5E,'Y'],[0x50,'Z'],[0x52,'T']]);
  assert.equal(prefix[0].r[29],0);assert.equal(prefix[0].m[22],15);
  assert.deepEqual([prefix[1].m[34],prefix[1].m[31],prefix[1].m[28]],[1,4,0]);
  assert.equal(raw(prefix[2].m),'000000000000');assert.equal(raw(prefix[3].m),'000000000000');
  assert.equal(source.slot,'U');assert.equal(raw(source.m),r.before.U.slice(2));
  assert.deepEqual([source.l,source.s1,source.r[32],source.r[35],source.r[41]],
    [1,6,5,0,5],'native entry satisfies every symbolic route premise');
  assert.deepEqual(A(es[sourceAt+1].otherChips[4]),Array.from({length:12},(_,i)=>source.m[1+3*i]));
  assert.equal(es[writerAt+1].otherChips[4].ip,0x2A);
  assert.deepEqual(A(es[writerAt+1].otherChips[4]),Array.from({length:12},(_,i)=>writer.m[1+3*i]));
  const expected=Object.fromEntries(Object.entries(es[writerAt].ring).map(([name,m])=>[name,m.slice()]));
  for(let i=0;i<12;i++) {expected.X[1+3*i]=writer.r[3*i];expected.Y[1+3*i]=writer.m[1+3*i];}
  assert.deepEqual(es[writerAt+2].ring,expected,'IK1303 pair checked on all 630 ring tetras');
  const pairWrites=r.traced.writes.filter(w=>w.command>=es[writerAt].command&&w.command<es[writerAt+2].command);
  assert.equal(pairWrites.length,24);
  assert.ok(pairWrites.every(w=>w.chip===4&&w.nibble%3===1&&w.nibble<=34&&
    ((w.ip===0x4E&&w.slot==='X')||(w.ip===0x2A&&w.slot==='Y'))));
  for(let i=1;i<=4;i++) {
    const at=es.findIndex(e=>e.stage==='remove-marker-'+i&&e.ip===0xE7&&e.s1===8&&e.sp[0]===0xA8);
    const block=checkSwapBlock(r,at,4);
    assert.deepEqual(block.body.map(e=>e.slot),['X','Y','Z','T']);
    assert.deepEqual(A(block.body[0]),Array(12).fill(0));
  }
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.equal(r.calc.displayText(),'5,');aligned(r.calc);
  assert.deepEqual(fullMsPages(r.calc),r.before);
  assert.deepEqual(registers(r.calc),r.afterRegisters);
  assert.deepEqual(program(r.calc),r.beforeProgram);
}

function main() {
  const negative=['111','222','333','-1.2345678E-42'];
  const extreme=['-1.2345678E-42','-9.8765432E99','9.8765432E99','-1E-99'];
  const cases=[{},...[0,1,2].map(phaseOffset=>({values:negative,phaseOffset})),
    ...[0,1,2].map(phaseOffset=>({values:extreme,phaseOffset})),
    {values:negative,settleFrames:12,markerFrames:8,swapWait:8},
    {values:['111','222','-1E-99','0']},
    {values:['111','222','-1.2345678E-42','12345678']},
    {values:['111','222','-9.8765432E99','9.8765432E99'],stress:true}];
  let firstDigest;
  for(const options of cases) {
    const r=run(options);firstDigest??=digest(r.calc);check(r);
    console.log('PASS:',JSON.stringify(options),'U -> IK1303:53 -> X -> P9; all Ms/program/other registers preserved.');
  }
  const plain=prepare();finish(plain);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);
  console.log('PASS: all-chip observation does not affect full state:',firstDigest);
  for(let i=0;i<3;i++) {const r=runPrepared(plain,{phaseOffset:i});check(r);
    console.log('PASS: repeated U read',i+1,'after arithmetic, without initialization.');}
  plain.pressSequence(['В/О','С/П']).runFrames(12);aligned(plain);
  assert.equal(plain.displayText(),'5,');assert.equal(plain.programCounter(),'05');
  assert.deepEqual(fullMsPages(plain),fullMsPages(prepare()));
  console.log('PASS: preserved program executes and returns 5.');
  const shifted=run({preLifts:1});
  assert.equal(shifted.afterRegisters[9],shifted.before.V.slice(2));
  assert.notEqual(shifted.afterRegisters[9],shifted.before.U.slice(2));
  assert.deepEqual(shifted.after,shifted.before);
  console.log('PASS: source-offset negative control: marker Y returns V, not U.');
  console.log('NOT K1: nondestructive numeric U read, not an eight-word exchange.');
}
if(require.main===module)main();
module.exports={check};
