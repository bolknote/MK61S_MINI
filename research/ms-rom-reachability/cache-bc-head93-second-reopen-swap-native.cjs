#!/usr/bin/env node
'use strict';
// Fresh ALL5 diagnostic. PRIMARY only issues SWAP's request; it does NOT
// model the secondary/tertiary numerical swap. No snapshot import/setters.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const FIRST='007012345678',SECOND='007024681357',ZERO='000000000000';
function run({proof=false}={}) {
  const v=prepare({proof,phase:'yku',secondPhase:'p8-reopen-swap'});
  const before=v.exitStages.find(s=>s.name==='packet-reopen-control-front3'),final=v.exitStages.at(-1);
  assert.deepEqual(before.markers,['V','aux0']);
  assert.equal(before.words['Ms:P7'],ZERO);assert.equal(before.words['Ms:P8'],SECOND);
  assert.equal(before.words['Ms:P10'],FIRST);
  assert.ok(!before.registers.includes(FIRST)&&!before.registers.includes(SECOND));
  assert.equal(v.report.packetAudit.numberHeld,true);assert.equal(final.words['Ms:P10'],FIRST);
  assert.deepEqual(final.registers,before.registers);assert.deepEqual(final.program,before.program);
  assert.equal(final.display,'0,');assert.equal(final.words['Ms:P7'],ZERO);
  assert.equal(final.words['Ms:P8'],ZERO);assert.ok(!Object.values(final.words).includes(SECOND));
  assert.equal(v.report.secondRelocationAudit.firstDifference.word,2889684);
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input')});
  console.log(JSON.stringify(process.argv.includes('--proof-input')?v:{
    stages:v.exitStages.filter(s=>s.name.startsWith('packet-reopen-control')||s.name==='packet-idle')
      .map(s=>({name:s.name,display:s.display,markers:s.markers,
        P7:s.words['Ms:P7'],P8:s.words['Ms:P8'],P10:s.words['Ms:P10']})),
    failure:v.report.secondRelocationAudit.firstDifference,
    finalWords:v.exitStages.at(-1).words,
    boundary:'measured failed ALL5 reverse SWAP: physicalP8->P7 transfer is overwritten by late primary E7/P7; NOT recovered output/repeat'}));
}
module.exports={run};
