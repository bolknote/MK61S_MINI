#!/usr/bin/env node
'use strict';
// Source-selected extension: keep a normal backup in physicalRD, clearR8,
// create a native rawF/R9 port, then plantU and targetQ/P7/P8/P9. No setters,
// ROM/control/IP/phase edits or keyboard sweep. Fresh observer-free ALL5 mirror.
// --next-zero follows the ACTUAL post-CX 01/aux1 root: logicalE -> realR0.
// It removes Z/U while moving oldZ/F to T. --wrong-post-source retains the
// old U-relative logical8 as a negative control; --post-calc still errors.
const {stopTransport}=require('./cache-bc-head93-blank-marker-native.cjs');
const assert=require('node:assert/strict');
function run({proof=false,wrongSource=false,ack=false,oldReader=false,calc=false,nextZero=false,wrongPostSource=false,postCalc=false}={}) {
  const value=stopTransport({zeros:1,minimal:true,proof,readBack:true,readAgainAfterClear:true,
    lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,qReadDigit:'9',
    qZeroSource:true,qIdleCheck:true,qWholeTail:true,qCleanup:'read2_twice',
    qFinalIdleCheck:true,qReserveGhost8:true,qAddressRead:'D',qAddressIdleCheck:true,
    qNormalReserve:true,qPayloadExit:'plain_roundtrip',qRestoreControl:'noP9',
    qRestoreIdleCheck:true,qRestoreCalcCheck:calc,qControllerZeroDigit:wrongSource?'D':'A',qControllerAck:ack,
    qControllerClearDigit:oldReader?'E':'5',qControllerZeroAfterCx:nextZero,
    qControllerPostCxDigit:wrongPostSource?'8':'E',qControllerPostCalc:postCalc,log:false});
  if(ack&&!wrongSource&&!oldReader) {
    const final=value.exitStages.find(s=>s.name==='restore-idle');
    assert.equal(final.words.Q,'000000000000');
    assert.equal(final.words['Ms:P9'],'000000000000');
    assert.equal(final.words['Ms:P10'],'007012345678');
    assert.deepEqual(final.markers,['Z','U','aux1']);
    assert.equal(final.registers[13],'007012345678');
    assert.equal(final.registers[8],'000000000000');
    if(calc) {
      assert.equal(value.report.calcAudit.checkedWords,42000);
      assert.equal(value.exitStages.at(-1).display,'ЕГГ0Г');
    }
    if(nextZero) {
      const shifted=value.exitStages.find(s=>s.name==='restore-next-idle');
      assert.equal(shifted.words['Ms:P10'],'007012345678');
      assert.deepEqual(shifted.markers,wrongPostSource?['Z','U','V','aux1']:['T','aux1']);
      if(!wrongPostSource) {
        assert.equal(shifted.words.Z,'000000000000');
        assert.equal(shifted.words.U,'000000000000');
        assert.equal(shifted.display,'0,');
      }
    }
    if(postCalc) {
      assert.equal(value.report.postCalcAudit.checkedWords,42000);
      assert.equal(value.report.postCalcAudit.numberHeld,true);
      assert.equal(value.report.postCalcAudit.firstDifference,null);
      assert.equal(value.exitStages.at(-1).display,'ЕГГ0Г');
    }
  }
  return value;
}
if(require.main===module) {
  const value=run({proof:process.argv.includes('--proof-input'),wrongSource:process.argv.includes('--wrong-source'),
    ack:process.argv.includes('--ack'),oldReader:process.argv.includes('--old-reader'),calc:process.argv.includes('--calc'),
    nextZero:process.argv.includes('--next-zero'),wrongPostSource:process.argv.includes('--wrong-post-source'),
    postCalc:process.argv.includes('--post-calc')});
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(value));
  else {
    for(const s of value.exitStages.filter(s=>s.name.startsWith('restore-')))
      console.log(JSON.stringify({name:s.name,display:s.display,pc:s.pc,R2:s.modeR2,
        ip:s.ip,words:s.words,registers:s.registers}));
    console.log(JSON.stringify({events:value.events.filter(e=>e.stage==='restore-P9-clear'&&![1,2,156].includes(e.ip)).slice(0,45),
      onlyPublicKeys:true,ALL5mirror:true}));
  }
}
module.exports={run};
