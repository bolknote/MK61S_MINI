#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_wq_repair.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const raw=(m,lane,count)=>Array.from({length:count},(_,i)=>m[lane+3*(count-1-i)].toString(16).toUpperCase()).join('');
const fromRing=(ring,names)=>Object.fromEntries(names.map(n=>[n,raw(ring[n],1,14)]));
const m1Names=['U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T'];
function check(r) {
  assert.deepEqual(r.after,r.options.restore?r.before:{...r.before,W:r.before.Q,Q:r.before.W},
    'exact final Ms state, including the restored U header');
  const regs=r.beforeRegisters.slice();
  for(const [n,word] of [[4,'U'],[5,'V'],[6,r.options.restore?'W':'Q'],[7,r.options.restore?'Q':'W'],[9,'U']])
    regs[n]=r.before[word].slice(2);
  assert.deepEqual(r.afterRegisters,regs,'only explicit P4..P7/P9 scratch registers change');
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  const es=r.traced.events;assert.ok(es.every(e=>e.ip!==0xC9));
  assert.deepEqual(m1Names.map(n=>raw(es[0].ring[n],0,12)),r.beforeRegisters,'physical M1 mapping cross-check');
  const start=es.find(e=>e.stage==='exchange-wq/clear-before');
  assert.deepEqual(fromRing(start.ring,Object.keys(r.before)),r.before,'U/V/W backups must not change Ms');
  const afterSwap=es.find(e=>e.stage==='read-q/clear-before');
  const saved=es.find(e=>e.stage==='source-p7');
  const mustPreserve=Object.keys(r.before).filter(n=>n!=='V');
  assert.deepEqual(fromRing(saved.ring,mustPreserve),fromRing(afterSwap.ring,mustPreserve),
    'secondary Q reader may change only the already-backed-up V');
  assert.deepEqual([4,5,6,7].map(n=>raw(saved.ring[m1Names[n]],0,12)),[4,5,6,7].map(n=>regs[n]));
  for(const n of [7,6,5,4]) {
    const at=es.findIndex(e=>e.stage==='write-p'+n+'/shifted-swap'&&e.ip===0xE7&&e.slot==='U');
    assert.ok(at>=0);const block=checkSwapBlock(r,at,4);
    assert.deepEqual(block.body.map(e=>e.slot),['U','V','W','Q']);
    assert.equal(raw(block.body[0].r,0,12),regs[n]);
  }
  const writes=r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.ok(writes.every(w=>w.command>=start.command), 'no temporary Ms writes during U/V/W backups');
  assert.ok(writes.every(w=>['U','V','W','Q'].includes(w.slot)&&w.nibble<=34));
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.equal(r.calc.displayText(),'5,');aligned(r.calc);
  assert.deepEqual(fullMsPages(r.calc),r.after);assert.deepEqual(registers(r.calc),regs);assert.deepEqual(program(r.calc),r.beforeProgram);
}
function main() {
  const cases=[{}, {phaseOffset:1}, {phaseOffset:2},
    ...[0,1,2].map(phaseOffset=>({phaseOffset,values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],stress:true}))];
  let firstDigest;
  for(const options of cases) {const r=p.run(options);firstDigest??=digest(r.calc);check(r);
    console.log('PASS:',JSON.stringify(options),'W/Q swapped, U/V restored, remaining Ms/program preserved; P4..P7/P9 scratch.');}
  const plain=p.prepare();p.finish(plain);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);console.log('PASS: observed/unobserved repaired W/Q:',firstDigest);
  const original=fullMsPages(plain);const r=p.runPrepared(plain);check(r);
  assert.equal(r.after.W,original.Q);assert.equal(r.after.Q,original.W);
  console.log('PASS: repeated composition without reset restores W/Q order.');
  plain.pressSequence(['В/О','С/П']).runFrames(12);aligned(plain);
  assert.equal(plain.displayText(),'5,');assert.equal(plain.programCounter(),'05');
  console.log('PASS: preserved program runs and returns 5.');
  const failed=p.run({phaseOffset:1,qReader:'direct'});
  assert.deepEqual(failed.after,{...failed.before,W:'00000000000000',Q:failed.before.W});
  assert.equal(failed.afterRegisters[6],'000000000000');
  assert.ok(failed.traced.events.some(e=>e.stage==='read-q/save-v-direct'&&e.ip===0x9C&&e.slot==='U'&&e.nextIp===0x9E));
  console.log('PASS: negative control: direct Q reader on phase 1 reads zero under false 1F control; the repair cannot recover that lost Q.');
  const negativeU=p.run({phaseOffset:1,values:['111','222','333','-1.2345678E-42']});
  assert.deepEqual(negativeU.after,{...negativeU.before,Q:negativeU.before.W});
  assert.equal(negativeU.afterRegisters[6],negativeU.before.W.slice(2));
  assert.deepEqual(negativeU.afterProgram,negativeU.beforeProgram);
  assert.ok(negativeU.traced.events.some(e=>e.stage==='exchange-wq/shifted-swap'&&e.ip===0x9C&&e.slot==='U'&&e.nextIp===0x9E));
  console.log('PASS: negative control: negative-exponent U diverts the W/Q exchange on phase 1; the full composition is not general.');
  console.log('CONDITIONAL composition: not a full K1; general negative-exponent U is not claimed.');
}
if(require.main===module)main();
module.exports={check};
