#!/usr/bin/env node
'use strict';
// Ordinary number -> hiddenP10 -> ordinaryP9 + display, with a real STOP,
// source erasure and released-key idle BETWEEN storage and retrieval.
// Header6 is a disposable marker-cleanup carrier, NOT the stored number.
// All actions run on the unchanged guarded stock reference and fresh mirrors.
const assert=require('node:assert/strict');
const {stopTransport}=require('./cache-bc-head93-blank-marker-native.cjs');
const {aligned,rawRegister,hashes}=require('./cache-bc-head93-indirect-ghost-native.cjs');
const {MK61}=require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
function baseline(input) {
  const c=new MK61();assert.equal(c.extended,true);
  for(const n of ['setRegister','writeCommand','loadProgram','writeNumber'])
    c[n]=()=>{throw Error('Forbidden baseline setter '+n);};
  c.inputNumber(input.startsWith('-')?input.slice(1):input,{clear:true});
  if(input.startsWith('-'))c.press('/-/');
  c.pressSequence(['X→П','6','Сx','П→X','6']).runFrames(12);
  aligned(c);return {input,word:rawRegister(c,6),display:c.displayText(),R2:c.ik1302.r[2]};
}
function run({proof=false,normalInput='12345678',control=null,arithmeticCheck=false}={}) {
  hashes();const ordinary=baseline(normalInput);
  const value=stopTransport({zeros:1,minimal:true,proof,readBack:true,
    readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,
    qReadInsteadLastX:true,qReadDigit:'9',qZeroSource:true,qIdleCheck:true,
    qWholeTail:true,qCleanup:'read2_twice',qFinalIdleCheck:true,qReserveGhost8:true,
    qAddressRead:'D',qAddressIdleCheck:true,qNormalReserve:true,normalInput,
    qPayloadExit:'plain_roundtrip',qPlainControl:control,qReadbackIdleCheck:true,
    qNormalArithmeticCheck:arithmeticCheck,log:false});
  const stored=value.exitStages.find(v=>v.name==='plain-storage-idle');
  const final=value.readbackStable,word=ordinary.word;
  assert.equal(value.report.normalWord,word);
  assert.equal(stored.display,'0,');assert.equal(stored.registers[6],'000000000000');
  assert.equal(stored.registers[9],'000000000000');
  assert.equal(stored.words['Ms:P9'],'000000000000');
  assert.equal(stored.words['Ms:P10'],control==='no_enter'?'000000000000':word);
  assert.equal(stored.words.Q,'0000F0000000');
  assert.equal(final.registers[6],'000000000000');
  assert.equal(final.registers[9],control?'000000000000':word);
  assert.equal(final.display,control?'0,':ordinary.display);
  assert.equal(final.words['Ms:P10'],control==='no_swap'?word:'000000000000');
  assert.equal(final.words.Q,'0000F0000000');
  if(arithmeticCheck) {
    const used=value.arithmeticStages.at(-1);
    assert.equal(used.display,'12345679,');assert.deepEqual(used.registers,final.registers);
    assert.equal(used.words.Q,'0000F0000000');
  }
  value.baseline=ordinary;hashes();return value;
}
if(require.main===module) {
  const normalInput=process.argv.includes('--negative')?'-87654321':
    process.argv.includes('--small')?'1.2345678E-50':'12345678';
  const control=process.argv.includes('--no-enter')?'no_enter':
    process.argv.includes('--no-swap')?'no_swap':null;
  const proof=process.argv.includes('--proof-input');
  const value=run({normalInput,control,proof,arithmeticCheck:process.argv.includes('--add-one')});
  if(proof)console.log(JSON.stringify(value));
  else {
    for(const name of ['payload-exit-run','plain-storage-idle','payload-readback-run']) {
      const s=value.exitStages.find(v=>v.name===name);
      console.log(JSON.stringify({name,control,input:normalInput,pc:s.pc,R2:s.modeR2,
        display:s.display,registers:s.registers,words:s.words}));
    }
    console.log(JSON.stringify({baseline:value.baseline,onlyPublicKeys:true,ALL5mirror:true}));
    if(value.arithmeticStages.length)console.log(JSON.stringify({arithmetic:value.arithmeticStages}));
  }
}
module.exports={run,baseline};
