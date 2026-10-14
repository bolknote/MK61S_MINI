#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_p9_push.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
function expected(r) {
  const out={...r.before};
  for(const [dst,word] of [['U',r.beforeRegisters[9]],['V',r.before.U.slice(2)],
    ['W',r.before.V.slice(2)],['Q',r.before.W.slice(2)]])out[dst]=r.before[dst].slice(0,2)+word;
  return out;
}
function check(r) {
  assert.deepEqual(r.after,expected(r));assert.deepEqual(r.afterRegisters,r.beforeRegisters);
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  const es=r.traced.events;assert.ok(es.every(e=>e.ip!==0xC9));
  const at=es.findIndex(e=>e.stage==='shifted-swap'&&e.ip===0xE7&&e.slot==='U');
  assert.ok(at>=0);const block=checkSwapBlock(r,at,4);
  assert.deepEqual(block.body.map(e=>e.slot),['U','V','W','Q']);
  assert.equal(block.after.ip,0xA9);assert.equal(block.after.slot,'P7');
  const loadAt=es.findLastIndex((e,i)=>i<at&&e.ip===0xD6);
  assert.ok(loadAt>=0);const load=es[loadAt];assert.equal(load.slot,'control');
  const raw=xs=>xs.map(n=>n.toString(16).toUpperCase()).reverse().join('');
  assert.equal(raw(Array.from({length:12},(_,i)=>load.m[3*i])),r.beforeRegisters[9]);
  assert.equal(raw(Array.from({length:12},(_,i)=>es[at].r[3*i])),r.beforeRegisters[9]);
  assert.deepEqual(es.slice(loadAt,at+6).map(e=>[e.ip,e.slot]),
    [[0xD6,'control'],[0xA7,'X1'],[0xE5,'X'],[0xE5,'Y'],[0xE6,'Z'],[0xE8,'T'],
     [0xE7,'U'],[0xA8,'V'],[0xA8,'W'],[0xA8,'Q'],[0xA9,'P7'],[0xAC,'P8']]);
  const changed=r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.ok(changed.every(w=>w.command>=block.body[0].command&&w.command<block.after.command));
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.equal(r.calc.displayText(),'5,');aligned(r.calc);
  assert.deepEqual(fullMsPages(r.calc),r.after);assert.deepEqual(registers(r.calc),r.afterRegisters);
  assert.deepEqual(program(r.calc),r.beforeProgram);
}
function checkEnriched() {
  const old=require('./probe_a8_ms_readout_zero.cjs');
  const seeded=old.run();old.runPrepared(seeded.calc);
  const r=p.runPrepared(seeded.calc);
  assert.notEqual(r.before.P7,'00000000000000');assert.notEqual(r.before.P8,'00000000000000');
  check(r);console.log('PASS: P9 push preserves native nonzero Ms P7/P8.');
}
function main() {
  const cases=[...[0,1,2].map(phaseOffset=>({phaseOffset})),
    ...[0,1,2].map(phaseOffset=>({phaseOffset,source:'-1.2345678E-42'})),
    {source:'0',values:['-1E-99','12345678','-9.8765432E99','-1E-99']},
    {source:'-9.8765432E99',stress:true},
    {source:'-1E-99',settleFrames:12,markerFrames:8}];
  let firstDigest;
  for(const options of cases) {const r=p.run(options);firstDigest??=digest(r.calc);check(r);
    console.log('PASS:',JSON.stringify(options),'P9 -> U, U/V/W -> V/W/Q; other Ms/program/all registers preserved.');}
  const plain=p.prepare();p.finish(plain);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);console.log('PASS: observed/unobserved P9 push:',firstDigest);
  for(let i=0;i<3;i++){check(p.runPrepared(plain,{phaseOffset:i}));console.log('PASS: repeat',i+1,'without reset.');}
  const words=fullMsPages(plain),source=registers(plain)[9];
  assert.ok(['U','V','W','Q'].every(n=>words[n].slice(2)===source));
  console.log('PASS: four pushes fill all four U/V/W/Q words with P9.');
  plain.pressSequence(['В/О','С/П']).runFrames(12);aligned(plain);
  assert.equal(plain.displayText(),'5,');assert.equal(plain.programCounter(),'05');
  console.log('PASS: preserved user program runs and returns 5.');
  checkEnriched();
  console.log('NOT full K1 and NOT an in-place U repair: old Q is discarded, three other words move.');
}
if(require.main===module)main();
module.exports={check,expected,checkEnriched};
