#!/usr/bin/env node
'use strict';
// Fixed public-key two-number retrieval AFTER ordinary math. P7->R6 is a
// true output; no subsequent ordinary source is allowed to stand in for P10.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const FIRST='007012345678',SECOND='007024681357';
function run({proof=false}={}) {
  const v=prepare({proof,phase:'yku',secondPhase:'p7-normal-retain-both'});
  const get=n=>v.exitStages.find(s=>s.name===n),start=get('packet-normal-preclear4'),final=v.exitStages.at(-1);
  assert.equal(v.report.packetAudit.numberHeld,true);assert.equal(v.report.secondSlotAudit.numberHeld,true);
  assert.equal(get('packet-normal-plus').display,'5,');
  assert.ok(!start.registers.includes(FIRST)&&!start.registers.includes(SECOND));
  assert.equal(get('packet-p7-read-output').registers[6],SECOND);
  assert.equal(get('packet-p7-first-read').display,'12345678,');
  assert.equal(final.registers[6],SECOND);assert.equal(final.registers[7],FIRST);
  assert.equal(final.words['Ms:P7'],SECOND);assert.equal(final.words['Ms:P10'],FIRST);
  assert.equal(final.display,'12345678,');assert.deepEqual(final.program,start.program);
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input')});
  console.log(JSON.stringify(process.argv.includes('--proof-input')?v:{
    stages:v.exitStages.filter(s=>s.name.startsWith('packet-p7-first')||s.name==='packet-p7-read-output'||s.name==='packet-idle')
      .map(s=>({name:s.name,display:s.display,markers:s.markers,R6:s.registers[6],R7:s.registers[7],P7:s.words['Ms:P7'],P10:s.words['Ms:P10']})),
    first:v.report.packetAudit.checkedWords,second:v.report.secondSlotAudit.checkedWords,
    boundary:'both physical numbers read after ordinary math; normal repeated cycle/arbitrary full eight-word K1/K2 still required'}));
}
module.exports={run};
