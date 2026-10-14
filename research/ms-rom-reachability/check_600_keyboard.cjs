#!/usr/bin/env node
'use strict';
// Construct an actual six-hundreds exponent, including the low mantissa
// nibble 3 required by the AC/A9 candidate. No injected program, register,
// chip state, serial input, or microcode. All setup goes through keys.
const assert=require('node:assert/strict');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');

function prepare(withMultiplier, {input='1E75',multiplier='1.0000003'}={}) {
  const calc=new MK61();
  calc.pressSequence(['F','ВП','F','*','F','*','F','*',
    ...(withMultiplier?['П→X','0','*']:[]),'С/П','F','/-/','В/О']);
  const expected=withMultiplier?[0x22,0x22,0x22,0x60,0x12,0x50]:[0x22,0x22,0x22,0x50];
  assert.deepEqual(expected.map((_,i)=>calc.readCommand(i)),expected);
  if(withMultiplier) calc.inputNumber(multiplier,{clear:true}).pressSequence(['X→П','0']);
  calc.inputNumber(input,{clear:true});
  return aligned(calc);
}

function run() {
  const ordinary=trace(prepare(false),calc=>{
    calc.pressSequence(['В/О','С/П']);calc.runFrames(12);
  });
  assert.ok(ordinary.events.some(e=>e.ip===0xEE && e.slot==='X' && e.raw==='600010000000'));
  assert.ok(ordinary.events.some(e=>e.ip===0xDE && e.nextIp===0xD6));
  assert.ok(ordinary.writes.some(e=>e.slot==='X' && e.chip===4 && e.ip===0x2A && e.value===6));
  assert.deepEqual(ordinary.primitives,[]);
  console.log('PASS: program x²,x²,x²,STOP with X=1E75 produces real X word '+
    '600010000000; IK1303:2A writes its 6; EE reads it; DE enters D6.');

  const combined=trace(prepare(true),calc=>{
    calc.pressSequence(['В/О','С/П']);calc.runFrames(12);
    calc.pressSequence(['БП','5','8','↔']);calc.runFrames(5);
  });
  const read=combined.events.find(e=>e.ip===0xEE && e.pc===0x58 && e.raw==='600010000003');
  assert.ok(read && read.slot==='X','genuine AC/PC58/EE M1=3 M34=6 combination');
  const ac=combined.events.find(e=>e.ip===0xAC && e.acNumber===read.acNumber);
  assert.ok(ac);
  assert.equal(ac.pc,0x58);
  assert.equal(ac.r1,0);
  assert.equal(ac.st32,0);
  assert.equal(ac.st35,0);
  const expected='AC E2 E5 E6 ED EE E3 91 92 93 94 95 98 9A '+
    '93 94 95 98 9A E4 DE D6 E5 E6 E0';
  const expectedRoute=expected.split(' ').map(v=>parseInt(v,16));
  assert.deepEqual(ac.route.slice(0,expectedRoute.length),expectedRoute);
  assert.deepEqual(combined.primitives,[]);
  console.log('PASS: keyboard-only AC at PC58 reads real word 600010000003. '+
    'It follows the proposed prefix through DE/D6, then E6->E0, not E9: '+
    'original R1=ST32=ST35=0. This is NOT a C8 entry.');
  return {ordinary,combined};
}

if(require.main===module) run();
module.exports={prepare,run};
