#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_p9_push.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');

function check(calc,options) {
  const sources=['-1.2345678E-42','-9.8765432E99','0','12345678'];
  for(let i=0;i<4;i++){inputLiteral(calc,sources[i]);calc.pressSequence(['X→П',String(4+i)]);}
  aligned(calc);
  const before=fullMsPages(calc),regs=registers(calc),code=program(calc);
  assert.equal(regs[3],'000000000000');
  p.fill4FromRegisters(calc,options);calc.runFrames(3);aligned(calc);
  const expected={...before};
  for(const [i,n] of ['U','V','W','Q'].entries())expected[n]=before[n].slice(0,2)+regs[4+i];
  assert.deepEqual(fullMsPages(calc),expected);
  const expectedRegs=regs.slice();expectedRegs[9]=regs[4];
  assert.deepEqual(registers(calc),expectedRegs);assert.deepEqual(program(calc),code);
  calc.pressSequence(['В/О','С/П']).runFrames(12);aligned(calc);
  assert.equal(calc.displayText(),'5,');assert.equal(calc.programCounter(),'05');
  assert.deepEqual(fullMsPages(calc),expected);assert.deepEqual(registers(calc),expectedRegs);
  assert.deepEqual(program(calc),code);
  console.log('PASS:',JSON.stringify(options),'P4/P5/P6/P7 -> U/V/W/Q; other Ms preserved; only P9 scratch; program returns 5.');
}
for(const phaseOffset of [0,1,2])check(p.prepare({stress:true}),{phaseOffset});
console.log('NOT K1: four-word one-way write, P9 scratch; no eight-register reverse exchange.');
