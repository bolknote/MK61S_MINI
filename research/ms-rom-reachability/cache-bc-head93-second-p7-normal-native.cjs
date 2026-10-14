#!/usr/bin/env node
'use strict';
// Native normal return without relocating SECOND: P7 and P10 hold every
// word, while a safe X1..W transport replaces the former W..P8 frame.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const FIRST='007012345678',SECOND='007024681357',ZERO='000000000000';
function run({proof=false,math=false}={}) {
  const v=prepare({proof,phase:'yku',secondPhase:math?'p7-normal-retain-math':'p7-normal-retain'});
  const get=n=>v.exitStages.find(s=>s.name===n),ready=get('packet-normal-port5-zero'),final=v.exitStages.at(-1);
  assert.equal(v.report.packetAudit.numberHeld,true);assert.equal(v.report.packetAudit.firstDifference,null);
  assert.equal(v.report.secondSlotAudit.numberHeld,true);assert.equal(v.report.secondSlotAudit.firstDifference,null);
  assert.equal(v.report.secondRelocationAudit.numberHeld,true);assert.equal(v.report.secondRelocationAudit.location,'P7');
  assert.deepEqual(v.report.secondRelocationAudit.moves,[]);
  assert.deepEqual(ready.markers,['aux0']);assert.equal(ready.words['Ms:P7'],SECOND);
  assert.equal(ready.words['Ms:P10'],FIRST);assert.equal(ready.registers[5],ZERO);
  assert.ok(!ready.registers.includes(FIRST)&&!ready.registers.includes(SECOND));
  assert.deepEqual(ready.program,get('packet-second-first-output').program);
  if(math) {
    assert.equal(get('packet-normal-plus').display,'5,');
    assert.equal(get('packet-normal-plus').words.Y,'000050000000');
    assert.equal(get('packet-normal-lastx').display,'3,');
    assert.deepEqual(final.markers,['aux0']);assert.equal(final.display,'0,');
    assert.equal(final.words['Ms:P7'],SECOND);assert.equal(final.words['Ms:P10'],FIRST);
    assert.deepEqual(final.registers,ready.registers);assert.deepEqual(final.program,ready.program);
  }
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input')||process.argv.includes('--audit-primary'),math:process.argv.includes('--math')});
  if(process.argv.includes('--audit-primary')){
    require('./cache-bc-head93-second-p7-return-plan.cjs').auditNative(v);
    process.exit(0);
  }
  console.log(JSON.stringify(process.argv.includes('--proof-input')?v:{
    stages:v.exitStages.filter(s=>s.name.startsWith('packet-normal-')||s.name==='packet-idle')
      .map(s=>({name:s.name,display:s.display,markers:s.markers,P7:s.words['Ms:P7'],P10:s.words['Ms:P10'],R5:s.registers[5]})),
    first:v.report.packetAudit,second:v.report.secondSlotAudit,onlyPublicKeys:true,ALL5mirror:true,
    boundary:'normal return/math with P7/P10 retained, not native readers/repeat/arbitrary eight-word K1/K2'}));
}
module.exports={run};
