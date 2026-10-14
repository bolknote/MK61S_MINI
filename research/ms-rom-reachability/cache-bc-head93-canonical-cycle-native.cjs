#!/usr/bin/env node
'use strict';
// Two hidden reads separated by a clean canonical return and NEW6 ENTER7+.
// Four normal zero recalls flush the visible stack before the second reader.
// Fresh stock original/full mirror, fixed public keys only; no state imports.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const NUMBER='007012345678',ZERO='000000000000',SEVEN='000070000000',THIRTEEN='001013000000';
function run({proof=false,noPreclear=false}={}) {
  const v=prepare({proof,phase:'yku',repeat:true,repeatClear:!noPreclear});
  const get=n=>v.exitStages.find(s=>s.name===n),inlet=get('packet-reopen-lastx');
  const restored=get('packet-repeat-port5-zero'),final=v.exitStages.at(-1);
  assert.equal(inlet.display,'12345678,');assert.equal(inlet.words.aux0,NUMBER);
  assert.deepEqual(restored.markers,['aux0']);assert.deepEqual(restored.registers,inlet.registers);
  assert.deepEqual(restored.program,inlet.program);
  assert.deepEqual(Object.keys(restored.words).filter(n=>restored.words[n]===NUMBER),['Ms:P10']);
  assert.equal(get('packet-repeat-plus').display,'13,');
  assert.equal(get('packet-repeat-plus').words.Y,THIRTEEN);
  assert.equal(get('packet-repeat-plus').words.X,SEVEN);
  assert.equal(get('packet-repeat-lastx').display,'7,');
  for(const s of v.exitStages.filter(s=>s.name.startsWith('packet-repeat-')||s.name==='packet-idle')) {
    assert.equal(s.words['Ms:P10'],NUMBER);assert.deepEqual(s.program,inlet.program);
    assert.ok(!s.registers.includes(NUMBER));assert.equal(s.registers[14],ZERO);
  }
  if(noPreclear) {
    assert.equal(get('packet-repeat-reopen-Zzero').registers[5],THIRTEEN);
    assert.equal(final.display,'13,');assert.deepEqual(final.markers,['Z','Ms:P8']);
    assert.equal(v.report.packetAudit.checkedWords,1443120);
  } else {
    const clear=get('packet-repeat-preclear4');assert.deepEqual(clear.markers,['aux0']);
    for(const name of ['Y','Z','T','X1'])assert.equal(clear.words[name],ZERO);
    assert.deepEqual(clear.registers,inlet.registers);
    assert.deepEqual(final.registers,inlet.registers);assert.deepEqual(final.markers,['Ms:P8']);
    assert.equal(final.display,'12345678,');assert.equal(final.words.aux0,NUMBER);
    // The visible numeric endpoint is reproduced except one spent service
    // header. Do NOT claim a whole-core cycle or unlimited repeat from this.
    assert.equal(inlet.words['Ms:P7'],'FFF000000000');
    const expectedWords={...inlet.words,'Ms:P7':ZERO};assert.deepEqual(final.words,expectedWords);
    assert.equal(v.report.packetAudit.checkedWords,1510320);
  }
  assert.equal(final.pc,'06');assert.equal(final.ip,0x35);
  assert.equal(v.report.packetAudit.numberHeld,true);assert.equal(v.report.packetAudit.firstDifference,null);
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input'),noPreclear:process.argv.includes('--no-preclear-control')});
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(v));
  else console.log(JSON.stringify({stages:v.exitStages.filter(s=>s.name.startsWith('packet-repeat-')||s.name==='packet-idle')
    .map(s=>({name:s.name,keys:s.keys,markers:s.markers,display:s.display,P10:s.words['Ms:P10']})),
    audit:v.report.packetAudit,onlyPublicKeys:true,ALL5mirror:true,
    boundary:'one fixed NUM fixture, two read/work cycles; no universal operation safety, arbitrary old bank or full K1/K2'}));
}
module.exports={run};
