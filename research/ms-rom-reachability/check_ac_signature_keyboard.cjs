#!/usr/bin/env node
'use strict';
// Reach the joint AC-entry predicate on the complete reference through keys.
// These are emulator frames, not a claim of verified physical-key timings.
const assert=require('node:assert/strict');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {prepare700}=require('./check_tail_sources_keyboard.cjs');
const registerKeys=[...'0123456789',',','/-/','ВП','Сx','В↑'];
function registerKey(index) {
  assert.ok(Number.isInteger(index)&&index>=0&&index<registerKeys.length);
  return registerKeys[index];
}

function finishSignature700(calc,{settleFrames=4,startAddress=null}={}) {
  if(startAddress!==null) assert.match(startAddress,/^\d{2}$/);
  calc.pressSequence(startAddress===null?['В/О','С/П']:
    ['БП',...startAddress,'С/П']).runFrames(12);
  calc.pressSequence(['F','/-/']);
  calc.pressSequence(['F','ВП']).runFrames(settleFrames);
  calc.press('В↑').runFrames(settleFrames);
  calc.pressSequence(['F','/-/']).runFrames(settleFrames);
  calc.pressSequence(['БП','5','8']).runFrames(settleFrames);
  calc.pressSequence(['БП','5','8']).runFrames(settleFrames);
}

function isSignature(e) {
  return e.ip===0xAC && e.pc===0x58 && e.r1===5 && e.st32===15 && e.st35===9;
}

function installArithmetic(calc,{input,multiplier,store=null,prefixNops=0}) {
  // Caller must be in the ordinary automatic scanner. No state setter is used.
  assert.ok(Number.isInteger(prefixNops)&&prefixNops>=0&&prefixNops<=9);
  calc.pressSequence(['В/О','F','ВП',...Array.from({length:prefixNops},()=>['K','0']).flat(),
    'F','*','F','*','F','*','П→X','0','*',
    ...(store===null?[]:['X→П',registerKey(store)]),'С/П','F','/-/','В/О']);
  const expected=[...Array(prefixNops).fill(0x54),0x22,0x22,0x22,0x60,0x12,
    ...(store===null?[]:[0x40+store]),0x50];
  assert.deepEqual(expected.map((_,i)=>calc.readCommand(i)),expected);
  calc.inputNumber(multiplier,{clear:true}).pressSequence(['X→П','0']);
  calc.inputNumber(input,{clear:true});
  return aligned(calc);
}

function rawMemoryRegister(calc,index) {
  assert.equal(calc.ir2a.tickIndex,84,'read numeric mapping only at phase 1');
  const [chip,end]=calc.commandAddress(index*7,1);
  const m=calc.memoryForChip(chip);
  return Array.from({length:12},(_,i)=>m[end-8-3*i].toString(16).toUpperCase()).join('');
}

function prepareStored600(calc=new MK61(),lowDigit=3) {
  assert.ok(Number.isInteger(lowDigit)&&lowDigit>=0&&lowDigit<=9);
  installArithmetic(calc,{input:'1E75',multiplier:'1.000000'+lowDigit,store:7});
  calc.pressSequence(['В/О','С/П']).runFrames(12);
  aligned(calc);
  return calc;
}

function prepareCombined({counter=null,calc=new MK61(),lowDigit=3}={}) {
  prepareStored600(calc,lowDigit);
  assert.equal(rawMemoryRegister(calc,7),'60001000000'+lowDigit);
  if(counter!==null) calc.inputNumber(String(counter),{clear:true}).pressSequence(['X→П','2']);
  installArithmetic(calc,{input:'1E87',multiplier:'1.0000005E4'});
  assert.equal(rawMemoryRegister(calc,7),'60001000000'+lowDigit);
  if(counter===1) assert.equal(rawMemoryRegister(calc,2),'000010000000');
  if(counter===0) assert.equal(rawMemoryRegister(calc,2),'000000000000');
  return calc;
}

function finishCombined(calc,options={}) {
  finishSignature700(calc,options);
  calc.pressSequence(['П→X','7']).runFrames(8);
}

function run() {
  const result=trace(prepare700(),finishSignature700);
  const signatures=result.events.filter(isSignature);
  assert.ok(signatures.length,'joint PC58/R1=5/ST32=F/ST35=9 AC entry');
  assert.deepEqual(result.primitives,[]);
  console.log('PASS: keys alone reach AC with PC58, R1=5, ST32=F, ST35=9. '+
    'This is the joint entry predicate, NOT an invocation of C8.');
  for(const ac of signatures) {
    const reads=result.events.filter(e=>e.ip===0xEE && e.acNumber===ac.acNumber);
    console.log(JSON.stringify({ac,reads}));
  }
  return result;
}

if(require.main===module)run();
module.exports={run,finishSignature700,isSignature,installArithmetic,
  rawMemoryRegister,prepareStored600,prepareCombined,finishCombined,registerKey};
