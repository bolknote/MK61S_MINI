#!/usr/bin/env node
'use strict';
// Native negative control for the precise late-writer obstruction. No model
// import/setters/ROM repair. BOTH hidden values survive through V/F, then
// the calculated next A-port call overwrites P8 in its FORMATTER, not frame.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const FIRST='007012345678',SECOND='007024681357',ZERO='000000000000',F='0000F0000000';
function run({proof=false,clearY=false}={}) {
  const v=prepare({proof,phase:'yku',secondPhase:clearY?'p8-reopen-clear':'p8-reopen-control'});
  const get=n=>v.exitStages.find(s=>s.name===n),before=get('packet-reopen-control-V'),final=v.exitStages.at(-1);
  assert.equal(before.words['Ms:P8'],SECOND);assert.equal(before.words['Ms:P10'],FIRST);
  assert.equal(v.report.packetAudit.numberHeld,true);
  assert.equal(v.report.secondRelocationAudit.numberHeld,false);
  assert.equal(v.report.secondRelocationAudit.firstDifference.stage,'packet-reopen-control-unsafe');
  if(clearY) {
    const cleared=get('packet-reopen-control-clearY');
    assert.equal(cleared.words.Y,ZERO);assert.equal(cleared.words['Ms:P8'],SECOND);
    assert.equal(cleared.words['Ms:P10'],FIRST);assert.ok(!cleared.markers.includes('Y'));
  }
  assert.equal(final.words['Ms:P8'],clearY?ZERO:F);assert.equal(final.words['Ms:P10'],FIRST);
  assert.ok(!before.registers.includes(FIRST)&&!before.registers.includes(SECOND));
  assert.deepEqual(final.registers,before.registers);assert.deepEqual(final.program,before.program);
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input'),clearY:process.argv.includes('--clear-y')});
  console.log(JSON.stringify(process.argv.includes('--proof-input')?v:{
    stages:v.exitStages.filter(s=>s.name.startsWith('packet-reopen-control')||s.name==='packet-idle')
      .map(s=>({name:s.name,markers:s.markers,display:s.display,P8:s.words['Ms:P8'],P10:s.words['Ms:P10']})),
    failure:v.report.secondRelocationAudit.firstDifference,
    boundary:'measured failed reverse constructor, not a successful reader/global impossibility'}));
}
module.exports={run};
