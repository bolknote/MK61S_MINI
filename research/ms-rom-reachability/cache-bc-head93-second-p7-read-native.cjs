#!/usr/bin/env node
'use strict';
// Read actual P7 via STORE after normal math, not asynchronous SWAP/P8.
// All earlier ordinary number outputs erased, guarded original+full mirror.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const FIRST='007012345678',SECOND='007024681357';
function run({proof=false}={}) {
  const v=prepare({proof,phase:'yku',secondPhase:'p7-normal-retain-read'});
  const get=n=>v.exitStages.find(s=>s.name===n),start=get('packet-normal-preclear4'),before=get('packet-p7-read-front3');
  const final=v.exitStages.at(-1);
  assert.equal(v.report.packetAudit.numberHeld,true);assert.equal(v.report.secondSlotAudit.numberHeld,true);
  assert.equal(start.words['Ms:P7'],SECOND);assert.equal(start.words['Ms:P10'],FIRST);
  assert.ok(!start.registers.includes(FIRST)&&!start.registers.includes(SECOND));
  assert.deepEqual(before.markers,['V','aux0']);
  assert.ok(!before.registers.includes(FIRST)&&!before.registers.includes(SECOND));
  assert.equal(final.registers[6],SECOND);assert.equal(final.display,'24681357,');
  assert.equal(final.words['Ms:P7'],SECOND);assert.equal(final.words['Ms:P10'],FIRST);
  assert.deepEqual(final.program,start.program);
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input')});
  console.log(JSON.stringify(process.argv.includes('--proof-input')?v:{
    stages:v.exitStages.filter(s=>s.name.startsWith('packet-p7-read')||s.name==='packet-normal-plus'||s.name==='packet-idle')
      .map(s=>({name:s.name,display:s.display,markers:s.markers,P7:s.words['Ms:P7'],P10:s.words['Ms:P10'],R6:s.registers[6]})),
    first:v.report.packetAudit.checkedWords,second:v.report.secondSlotAudit.checkedWords,
    onlyPublicKeys:true,ALL5mirror:true,
    boundary:'P7 read after actual ordinary math; first P10 reader/repeat/full eight-word K1/K2 still required'}));
}
module.exports={run};
