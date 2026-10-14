#!/usr/bin/env node
'use strict';
// Native ordinary geometry, with SECOND relocated P7 -> workingA -> P8.
// Keep the OLD P7-only failure ledger: relocation is not mislabeled as P7
// preservation. Original guarded reference/fresh full mirror/public keys.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const FIRST='007012345678',SECOND='007024681357',ZERO='000000000000';
function run({proof=false,math=false}={}) {
  const v=prepare({proof,phase:'yku',secondPhase:math?'p8-normal-math':'p8-normal'});
  const get=n=>v.exitStages.find(s=>s.name===n),ready=get('packet-normal-port5-zero'),final=v.exitStages.at(-1);
  assert.equal(v.report.packetAudit.numberHeld,true);assert.equal(v.report.packetAudit.firstDifference,null);
  assert.equal(v.report.secondRelocationAudit.numberHeld,true);assert.equal(v.report.secondRelocationAudit.firstDifference,null);
  assert.equal(v.report.secondRelocationAudit.location,'P8');assert.equal(v.report.secondRelocationAudit.moves.length,2);
  assert.equal(v.report.secondSlotAudit.numberHeld,false);
  assert.equal(v.report.secondSlotAudit.firstDifference.stage,'packet-normal-relocate');
  assert.deepEqual(ready.markers,['aux0']);assert.equal(ready.registers[5],ZERO);
  assert.ok(!ready.registers.includes(FIRST)&&!ready.registers.includes(SECOND));
  assert.equal(ready.words['Ms:P8'],SECOND);assert.equal(ready.words['Ms:P10'],FIRST);
  assert.deepEqual(ready.program,get('packet-second-first-output').program);
  if(math) {
    assert.equal(get('packet-normal-plus').display,'5,');
    assert.equal(get('packet-normal-plus').words.Y,'000050000000');
    assert.equal(get('packet-normal-plus').words.X,'000030000000');
    assert.equal(get('packet-normal-lastx').display,'3,');
    assert.deepEqual(final.markers,['aux0']);assert.equal(final.display,'0,');
    assert.equal(final.words['Ms:P8'],SECOND);assert.equal(final.words['Ms:P10'],FIRST);
    assert.deepEqual(final.registers,ready.registers);assert.deepEqual(final.program,ready.program);
  }
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input'),math:process.argv.includes('--math')});
  console.log(JSON.stringify(process.argv.includes('--proof-input')?v:{
    stages:v.exitStages.filter(s=>s.name.startsWith('packet-normal-')||s.name==='packet-idle')
      .map(s=>({name:s.name,display:s.display,markers:s.markers,R5:s.registers[5],R6:s.registers[6],R7:s.registers[7],
        P7:s.words['Ms:P7'],P8:s.words['Ms:P8'],P10:s.words['Ms:P10']})),
    first:v.report.packetAudit,relocation:v.report.secondRelocationAudit,oldP7:v.report.secondSlotAudit,
    onlyPublicKeys:true,ALL5mirror:true,boundary:'normal geometry/math with two preserved numbers, SECOND nowP8; reverse readers/repeat/arbitrary bank unproved'}));
}
module.exports={run};
