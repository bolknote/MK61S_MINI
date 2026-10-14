#!/usr/bin/env node
'use strict';
// Source-selected E9/SIGN and zero-lift candidates after native T/aux1 cleanup.
// SIGN stores zero/Y but primary writes request32/X1 while secondary reads
// X/control00. Direct zero reads/ENTER/LastX are rejected by9C at X/zero.
// All profiles preserve P10, but DO NOT removeT or restore normal arithmetic.
// Fresh guarded references, fixed public keys, observer-free ALL5 mirrors.
// No model state is loaded, no ROM/control/phase/return edits.
const assert=require('node:assert/strict');
const {stopTransport}=require('./cache-bc-head93-blank-marker-native.cjs');
function run({proof=false,calc=false,profile='sign',leadFrames=0,zeroDigit='E'}={}) {
  const value=stopTransport({zeros:1,minimal:true,proof,readBack:true,readAgainAfterClear:true,
    lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,qReadDigit:'9',
    qZeroSource:true,qIdleCheck:true,qWholeTail:true,qCleanup:'read2_twice',
    qFinalIdleCheck:true,qReserveGhost8:true,qAddressRead:'D',qAddressIdleCheck:true,
    qNormalReserve:true,qPayloadExit:'plain_roundtrip',qRestoreControl:'noP9',
    qRestoreIdleCheck:true,qControllerZeroDigit:'A',qControllerAck:true,
    qControllerClearDigit:'5',qControllerZeroAfterCx:true,qControllerPostCxDigit:'E',
    qControllerPostCalc:calc,qTRecoveryProfile:profile,qTLeadFrames:leadFrames,qTZeroDigit:zeroDigit,log:false});
  const inlet=value.exitStages.find(s=>s.name==='restore-next-idle');
  assert.deepEqual(inlet.markers,['T','aux1']);
  assert.equal(inlet.words['Ms:P10'],'007012345678');
  const final=value.exitStages.find(s=>s.name==='t-recovery-idle');
  assert.deepEqual(final.markers,['T','aux1']);
  assert.equal(final.words['Ms:P10'],'007012345678');
  assert.equal(final.display,'ЕГГ0Г');
  assert.deepEqual(final.registers,inlet.registers);
  assert.deepEqual(final.program,inlet.program);
  const expected={...inlet.words,...(profile==='sign'?{Y:'000000000000'}:{})};
  assert.deepEqual(final.words,expected);
  assert.equal(value.report.tRecoveryAudit.numberHeld,true);
  assert.equal(value.report.tRecoveryAudit.firstDifference,null);
  assert.equal(value.report.tRecoveryAudit.checkedWords,profile==='enter'?15120:23520);
  if(calc) {
    assert.equal(value.report.postCalcAudit.checkedWords,42000);
    assert.equal(value.report.postCalcAudit.numberHeld,true);
    assert.equal(value.report.postCalcAudit.firstDifference,null);
    assert.equal(value.exitStages.at(-1).display,'ЕГГ0Г');
  }
  return value;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input'),calc:process.argv.includes('--calc'),
    profile:process.argv.includes('--lastx')?'lastx':process.argv.includes('--enter')?'enter':process.argv.includes('--zero')?'zero':'sign',leadFrames:process.argv.includes('--lead-two')?2:0,
    zeroDigit:process.argv.includes('--digit-six')?'6':'E'});
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(v));
  else console.log(JSON.stringify({stages:v.exitStages.filter(s=>s.name.startsWith('t-recovery-')
    ||s.name.startsWith('restore-post-')),audit:v.report.tRecoveryAudit,
    mathAudit:v.report.postCalcAudit,events:v.events.filter(e=>e.stage.startsWith('t-recovery-')
      &&![0x01,0x02,0x9C,0x9D].includes(e.ip)).slice(0,45),onlyPublicKeys:true,ALL5mirror:true}));
}
module.exports={run};
