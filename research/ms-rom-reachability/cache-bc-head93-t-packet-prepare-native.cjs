#!/usr/bin/env node
'use strict';
// Earlier source-selected constructor: reserve F/C by original STOP/STORE,
// back up number in realRE (predecessor RD remains0), seed F/R8, then read
// actualR8 to plant U/F while erasing Q. Native keys/mirrors only, no setters.
const assert=require('node:assert/strict');
const {stopTransport}=require('./cache-bc-head93-blank-marker-native.cjs');
function run({proof=false,phase='u',repeat=false,repeatClear=false,repeatCount=1,normalInput='12345678',lateNumber=null,secondPhase=null}={}) {
  const v=stopTransport({zeros:1,minimal:true,proof,readBack:true,readAgainAfterClear:true,
    lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,qReadDigit:'9',
    qZeroSource:true,qIdleCheck:true,qWholeTail:true,qCleanup:'read2_twice',
    qFinalIdleCheck:true,qReserveGhost8:true,qAddressRead:'D',qAddressIdleCheck:true,
    qNormalReserve:true,normalInput,qPayloadExit:'plain_roundtrip',qRestoreControl:'noP9',
    qRestoreIdleCheck:true,qMarkerPacket:phase,qMarkerRepeat:repeat,qMarkerRepeatClear:repeatClear,qMarkerRepeatCount:repeatCount,qMarkerLateNumber:lateNumber,qMarkerSecondPhase:secondPhase,log:false});
  assert.equal(v.extraMarkerPrepared.registers[12],'0000F0000000');
  assert.equal(v.exitStages.find(s=>s.name==='plain-storage-idle').words['Ms:P10'],v.report.normalWord);
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input'),phase:process.argv.includes('--repeat-number')?'ynr':process.argv.includes('--clean-sign')?'yns':process.argv.includes('--clean-lastx')?'ynx':process.argv.includes('--flush-three')?'yf3':process.argv.includes('--flush-two')?'yf2':process.argv.includes('--flush-one')?'yf1':process.argv.includes('--sign-number')?'yls':process.argv.includes('--lastx-number')?'ylx':process.argv.includes('--sign-retry')?'ysr':process.argv.includes('--sign-lead')?'ysl':process.argv.includes('--sign')?'ys':process.argv.includes('--clear-u-lead')?'ycl':process.argv.includes('--clear-u')?'yc':process.argv.includes('--old-y-address')?'yfd':process.argv.includes('--shift-y')?'yf':process.argv.includes('--open-y')?'xf':process.argv.includes('--p8')?'p8':process.argv.includes('--move-two')?'m2':process.argv.includes('--move-ack')?'m1a':process.argv.includes('--move-one')?'m1':process.argv.includes('--retry')?'q2':
    process.argv.includes('--insert-q')?'q':'u'});
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(v));
  else console.log(JSON.stringify({stages:v.exitStages.filter(s=>s.name.startsWith('packet-')),
    audit:v.report.packetAudit,events:v.events.filter(e=>e.stage.startsWith('packet-')
      &&[0xD4,0xD6,0xE7,0xA8,0xEE,0xA3].includes(e.ip)).slice(0,32),
    onlyPublicKeys:true,ALL5mirror:true}));
}
module.exports={run};
