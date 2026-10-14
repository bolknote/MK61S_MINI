#!/usr/bin/env node
'use strict';
// Source-led second-slot alternative. Three U..Q shifts followed by Q..P9
// avoid the former destructive P7..P10 push. Fresh original+full mirror,
// public keys only. Basic mode explicitly retains temporary R6/R7 reserves;
// --erase deletes them, --read then recovers physical P7 into R6/display.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const FIRST='007012345678',SECOND='007024681357';
function run({proof=false,erase=false,read=false}={}) {
  if(read)erase=true;
  const v=prepare({proof,phase:'yku',secondPhase:read?'p7-shift-read':erase?'p7-shift-clear':'p7-shift-write'});
  const stages=v.exitStages.filter(x=>x.name.startsWith('packet-second-shift')||x.name.startsWith('packet-second-erase')||x.name.startsWith('packet-second-read')||x.name==='packet-idle');
  assert.equal(v.report.onlyPublicKeys,true);assert.equal(v.report.ALL5mirror,true);
  v.secondShift={stages:stages.map(s=>({name:s.name,keys:s.keys,display:s.display,markers:s.markers,
    P7:s.words['Ms:P7'],P10:s.words['Ms:P10'],U:s.words.U,V:s.words.V,W:s.words.W,Q:s.words.Q,
    R6:s.registers[6],R7:s.registers[7]})),
    firstHeld:v.report.packetAudit.numberHeld,
    twoPhysicalSlots:v.exitStages.at(-1).words['Ms:P7']===SECOND&&v.exitStages.at(-1).words['Ms:P10']===FIRST,
    erased:erase,read,
    boundary:erase?'ordinary numerical copies erased; clean return, independent read and normal arithmetic NOT yet proved':
      'temporary ordinary R6/R7 copies remain; clean return, independent read and normal arithmetic NOT yet proved'};
  assert.equal(v.secondShift.firstHeld,true);assert.equal(v.secondShift.twoPhysicalSlots,true);
  assert.equal(v.report.secondSlotAudit.numberHeld,true);assert.equal(v.report.secondSlotAudit.firstDifference,null);
  assert.equal(v.report.secondSlotAudit.writes.length,1);
  const final=v.exitStages.at(-1);
  assert.equal(final.words['Ms:P7'],SECOND);assert.equal(final.words['Ms:P10'],FIRST);
  if(erase) {
    const cleared=v.exitStages.find(s=>s.name==='packet-second-erase7');
    assert.equal(cleared.registers[6],'000000000000');assert.equal(cleared.registers[7],'000000000000');
    assert.ok(!cleared.registers.includes(FIRST)&&!cleared.registers.includes(SECOND));
    assert.deepEqual(Object.keys(cleared.words).filter(n=>cleared.words[n]===FIRST),['Ms:P10']);
    assert.deepEqual(Object.keys(cleared.words).filter(n=>cleared.words[n]===SECOND),['Ms:P7']);
    if(!read)assert.deepEqual(final.registers,cleared.registers);
  }
  if(read) {
    assert.equal(final.registers[6],SECOND);assert.equal(final.registers[7],'000000000000');
    assert.ok(!final.registers.includes(FIRST));
    v.secondShift.boundary='both ordinary sources erased BEFORE P7 is read into realR6; P10 held; clean return, first-slot reader and normal arithmetic not yet proved';
  }
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input'),erase:process.argv.includes('--erase'),read:process.argv.includes('--read')});
  console.log(JSON.stringify(process.argv.includes('--proof-input')?v:{...v.secondShift,audit:v.report.packetAudit,secondAudit:v.report.secondSlotAudit}));
}
module.exports={run};
