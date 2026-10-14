#!/usr/bin/env node
'use strict';
// Repeat the SAME normal-return/math/both-reader programme of public keys.
// No re-entry of either payload, no register/model/ROM/phase repair.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const FIRST='007012345678',SECOND='007024681357';
function run({proof=false}={}) {
  const v=prepare({proof,phase:'yku',secondPhase:'p7-normal-retain-repeat'});
  const get=n=>v.exitStages.find(s=>s.name===n);
  assert.equal(v.report.packetAudit.numberHeld,true);assert.equal(v.report.secondSlotAudit.numberHeld,true);
  const start=get('packet-p7-repeat-inlet'),ready=get('packet-p7-repeat-normal-port5-zero');
  assert.ok(!ready.registers.includes(FIRST)&&!ready.registers.includes(SECOND));
  assert.deepEqual(ready.markers,['aux0']);assert.equal(ready.registers[5],'000000000000');
  assert.equal(get('packet-p7-repeat-normal-plus').display,'5,');
  assert.equal(get('packet-p7-repeat-p7-read-output').registers[6],SECOND);
  const final=get('packet-p7-repeat-idle');
  assert.equal(final.registers[6],SECOND);assert.equal(final.registers[7],FIRST);
  assert.equal(final.words['Ms:P7'],SECOND);assert.equal(final.words['Ms:P10'],FIRST);
  assert.deepEqual(final.program,start.program);assert.deepEqual(final.markers,['Ms:P8']);
  const equal=JSON.stringify(v.nativeIdleStates['packet-p7-repeat-inlet'])===JSON.stringify(v.nativeIdleStates['packet-p7-repeat-idle']);
  return {...v,repeatDiagnostic:{equal,startWord:v.nativeEndpoints['packet-p7-repeat-inlet'].word,
    endWord:v.nativeEndpoints['packet-p7-repeat-idle'].word,
    ready:{markers:ready.markers,ordinaryNumericCopies:ready.registers.filter(x=>[FIRST,SECOND].includes(x))},
    final:{display:final.display,R6:final.registers[6],R7:final.registers[7],P7:final.words['Ms:P7'],P10:final.words['Ms:P10']},
    boundary:equal?'one complete repeated cycle has exact whole-core endpoint equality; variants/arbitrary bank/full K1/K2 still required':
      'both retrieved again, but exact whole-core closure not yet obtained'}};
}
if(require.main===module){const v=run({proof:process.argv.includes('--proof-input')});console.log(JSON.stringify(process.argv.includes('--proof-input')?v:v.repeatDiagnostic));}
module.exports={run};
