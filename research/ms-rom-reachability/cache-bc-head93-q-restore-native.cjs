#!/usr/bin/env node
'use strict';
// A native rawF reservoir survives normal hiddenP10 storage. Only the exact
// source-selected first shifted reader is tried, not a keyboard search.
const assert=require('node:assert/strict');
const {stopTransport}=require('./cache-bc-head93-blank-marker-native.cjs');
function run({proof=false,readF=false,second=false,lastX=false,eraseQ=false,plantZ=false,
  wipeQ=false,short=false,noZ=false,idle=false,calc=false}={}) {
  const value=stopTransport({zeros:1,minimal:true,proof,readBack:true,
    readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,
    qReadInsteadLastX:true,qReadDigit:'9',qZeroSource:true,qIdleCheck:true,
    qWholeTail:true,qCleanup:'read2_twice',qFinalIdleCheck:true,qReserveGhost8:true,
    qAddressRead:'D',qAddressIdleCheck:true,qNormalReserve:true,
    qPayloadExit:'plain_roundtrip',qRestoreIdleCheck:idle,qRestoreCalcCheck:calc,
    qRestoreControl:noZ?'noZ':short?'wipeQShort':wipeQ?'wipeQ':plantZ?'plantZ':eraseQ?'eraseQ':lastX?'lastX':second?'readF2':readF?'readF':'seed',log:false});
  assert.equal(value.markerPrepared.registers[3],'0000F0000000');
  const stored=value.exitStages.find(s=>s.name==='plain-storage-idle');
  assert.equal(stored.words['Ms:P10'],'007012345678');
  assert.equal(stored.registers[3],'0000F0000000');
  assert.equal(stored.registers[6],'000000000000');
  assert.deepEqual(stored.markers,['Q']);
  if(short) {
    const erased=value.exitStages.find(s=>s.name==='restore-idle')||value.exitStages.at(-1);
    assert.equal(erased.words.Q,'000000000000');
    assert.equal(erased.words['Ms:P10'],'007012345678');
    assert.deepEqual(erased.markers,['Z','Ms:P9','aux1']);
  }
  if(noZ)assert.equal(value.exitStages.at(-1).words.Q,'0000F0000000');
  if(calc) {
    const first=value.exitStages.find(s=>s.name==='restore-test-cx');
    const last=value.exitStages.at(-1);
    assert.equal(first.words['Ms:P10'],'FFF012345678','CX damages the saved exponent');
    assert.equal(last.display,'3,','not a restored ordinary2/ENTER/3/+ exit');
    assert.equal(last.registers[9],'007012345678','ordinary backup survives');
  }
  return value;
}
if(require.main===module) {
  const value=run({proof:process.argv.includes('--proof-input'),readF:process.argv.includes('--readF'),
    second:process.argv.includes('--second'),lastX:process.argv.includes('--lastx'),eraseQ:process.argv.includes('--eraseQ'),
    plantZ:process.argv.includes('--plantZ'),wipeQ:process.argv.includes('--wipeQ'),
    short:process.argv.includes('--short'),noZ:process.argv.includes('--noZ'),idle:process.argv.includes('--idle'),calc:process.argv.includes('--calc')});
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(value));
  else {
    for(const s of (process.argv.includes('--calc')?value.exitStages.filter(s=>
      s.name==='restore-idle'||s.name.startsWith('restore-test-')):
      [value.markerPrepared,...value.exitStages.filter(s=>s.name==='plain-storage-idle'||s.name?.startsWith('restore-'))]))
      console.log(JSON.stringify({name:s.name||'markerPrepared',display:s.display,pc:s.pc,
        R2:s.modeR2,ip:s.ip,words:s.words,registers:s.registers}));
    const stage=['--wipeQ','--short','--noZ'].some(f=>process.argv.includes(f))?'restore-wipeQ':'restore-plantZ';
    console.log(JSON.stringify({events:value.events.filter(e=>e.stage===stage&&![1,2].includes(e.ip)),
      onlyPublicKeys:true,ALL5mirror:true}));
  }
}
module.exports={run};
