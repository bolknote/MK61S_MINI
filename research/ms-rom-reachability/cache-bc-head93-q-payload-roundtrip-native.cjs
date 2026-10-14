#!/usr/bin/env node
'use strict';
// Native raw readback plus two source-selected negative decoder controls.
// Original stock reference, public keys only; generated order600/order400
// are NOT loaded through setters. Raw readback is tested by the companion
// ALL5 proof; inverse-scale and VP7 do NOT decode the eight-digit payload.
const assert=require('node:assert/strict');
const {aligned,rawRegister,dump,hashes}=
  require('./cache-bc-head93-indirect-ghost-native.cjs');
const {MK61}=require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
function fresh() {
  const c=new MK61();assert.equal(c.extended,true);
  for(const name of ['setRegister','writeCommand','loadProgram','writeNumber'])
    c[name]=()=>{throw Error('Forbidden setter '+name);};
  return aligned(c);
}
function prepareInverseScale(c,multiplier='1.2345678') {
  assert.equal(multiplier,'1.2345678','one selected eight-digit fixture, no sweep');
  c.inputNumber('1E7',{clear:true}).pressSequence(['X→П','5']);
  c.inputNumber(multiplier,{clear:true}).pressSequence(['X→П','1']);
  c.inputNumber('1E-75',{clear:true}).pressSequence(['X→П','0']);
  const keys=['В/О','F','ВП',
    'F','*','F','*','F','*','П→X','1','*','X→П','8',
    'П→X','0','F','*','F','*','F','*','X→П','6',
    'П→X','1','F','*','Сx','В↑','В↑','В↑','В↑',
    'С/П','F','/-/','В/О'];
  c.pressSequence(keys);aligned(c);
  const codes=[0x22,0x22,0x22,0x61,0x12,0x48,
    0x60,0x22,0x22,0x22,0x46,0x61,0x22,
    0x0D,0x0E,0x0E,0x0E,0x0E,0x50];
  assert.deepEqual(codes.map((_,i)=>c.readCommand(i)),codes);
  c.inputNumber('1E75',{clear:true}).pressSequence(['В/О','С/П']).runFrames(60);
  aligned(c);
  const made=Array.from({length:15},(_,i)=>rawRegister(c,i));
  assert.equal(made[8],'600012345678','actual arithmetic payload in ordinaryP8');
  assert.equal(made[6],'400010000000','actual order-600 inverse factor in ordinaryP6');
  assert.equal(made[5],'007010000000','ordinaryP5=1E7');
  c.inputNumber('0',{clear:true}).pressSequence(['X→П','0','X→П','1']);aligned(c);
  assert.equal(rawRegister(c,0),'000000000000');
  assert.equal(rawRegister(c,1),'000000000000','remove the visible coefficient copy');
  assert.equal(rawRegister(c,8),made[8]);assert.equal(rawRegister(c,6),made[6]);
  return {keys,codes,made,registers:Array.from({length:15},(_,i)=>rawRegister(c,i)),
    pc:c.programCounter(),display:c.displayText(),onlyPublicKeys:true};
}
function run() {
  if(process.argv.includes('--raw-read-proof-input')||process.argv.includes('--raw-read-short-proof-input')
      ||process.argv.includes('--raw-read-control-proof-input')) {
    const short=process.argv.includes('--raw-read-short-proof-input');
    const control=process.argv.includes('--raw-read-control-proof-input');
    const r=require('./cache-bc-head93-blank-marker-native.cjs').stopTransport({zeros:1,
      minimal:true,proof:true,readBack:true,readAgainAfterClear:true,lastXLift:true,
      removeRealThenLastX:true,qReadInsteadLastX:true,qReadDigit:'9',qZeroSource:true,
      qIdleCheck:true,qWholeTail:true,qCleanup:'read2_twice',qFinalIdleCheck:true,
      qReserveGhost8:true,qAddressRead:'D',qAddressIdleCheck:true,
      ghostMultiplier:short?'1.0000003':'1.2345678',
      qPayloadExit:control?'raw_read_control':'raw_read',qReadbackIdleCheck:true,log:false});
    console.log(JSON.stringify(r));return;
  }
  if(process.argv.includes('--decode-trace')||process.argv.includes('--raw-read-trace')
      ||process.argv.includes('--exponent-read-trace')) {
    const inverse=process.argv.includes('--decode-trace');
    const r=require('./cache-bc-head93-blank-marker-native.cjs').stopTransport({zeros:1,
      minimal:true,readBack:true,readAgainAfterClear:true,lastXLift:true,
      removeRealThenLastX:true,qReadInsteadLastX:true,qReadDigit:'9',qZeroSource:true,
      qIdleCheck:true,qWholeTail:true,qCleanup:'read2_twice',qFinalIdleCheck:true,
      qReserveGhost8:true,qAddressRead:'D',qAddressIdleCheck:true,
      ghostMultiplier:'1.2345678',qInverseScale:inverse,
      qPayloadExit:inverse?'decode':process.argv.includes('--exponent-read-trace')?'exponent_read':'raw_read',log:false});
    const last=r.exitStages.at(-1);
    if(inverse)assert.equal(last.display,'0,','the selected inverse-scale decoder fails');
    else if(process.argv.includes('--exponent-read-trace')) {
      assert.equal(last.display,'10000000,','VP7 creates mantissa1, not recovered12345678');
      assert.equal(last.registers[9],'007010000000');
    } else {
      assert.equal(last.registers[8],'000000000000');
      assert.equal(last.registers[9],'600012345678','positive raw readback');
    }
    for(const s of r.exitStages)console.log(JSON.stringify({name:s.name,pc:s.pc,mode:s.modeR2,
      display:s.display,P8:s.registers[8],P9:s.registers[9],words:s.words}));
    for(const e of r.events.filter(e=>e.stage==='payload-exit-run'&&![1,2].includes(e.ip)))
      console.log(JSON.stringify(e));
    return;
  }
  hashes();const c=fresh(),plain=fresh();
  const prepared=prepareInverseScale(c),mirror=prepareInverseScale(plain);
  assert.deepEqual(prepared,mirror);assert.deepEqual(dump(c),dump(plain));hashes();
  console.log(JSON.stringify({prepared,ALL5mirror:true,onlyPublicKeys:true}));
}
module.exports={prepareInverseScale};
if(require.main===module)run();
