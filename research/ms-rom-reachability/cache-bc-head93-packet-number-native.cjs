#!/usr/bin/env node
'use strict';
// Native hiddenP10 -> numerical aux0/display -> SIGN1, repeated twice.
// Three source-selected realR2-zero recalls remove only the extra stack
// markers; LastX then reads P10 instead of the previous aux1-relative Y/F.
// No state imports, ROM/control/phase edits, setters or keyboard sweeps.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const NUMBER='007012345678',ONE='000010000000',ZERO='000000000000',F='0000F0000000';
function run({proof=false,negative=false,repeat=true,overwrite=false}={}) {
  assert.ok(!overwrite||(!negative&&repeat),'buffer overwrite is one source-selected post-repeat diagnostic');
  const v=prepare({proof,phase:negative?'yls':overwrite?'ynb':repeat?'ynr':'yns'});
  const stage=n=>v.exitStages.find(s=>s.name===n);
  const inlet=stage('packet-sign-retry'),last=v.exitStages.at(-1);
  assert.equal(inlet.words['Ms:P10'],NUMBER);
  assert.deepEqual(inlet.markers,['Y','Ms:P8','aux1']);
  assert.deepEqual(last.registers,inlet.registers);assert.deepEqual(last.program,inlet.program);
  if(negative) {
    assert.equal(stage('packet-lastx').words.aux0,F);
    assert.equal(stage('packet-lastx').words['Ms:P10'],NUMBER);
    assert.equal(last.words['Ms:P10'],ZERO);assert.equal(last.display,',');
    assert.equal(v.report.packetAudit.numberHeld,false);
    assert.deepEqual(v.report.packetAudit.firstDifference,
      {word:797485,stage:'packet-sign-number',moment:'after',actual:ZERO});
    assert.equal(v.report.packetAudit.checkedWords,258720);
  } else {
    assert.deepEqual(stage('packet-flush1').markers,['X','Ms:P8']);
    assert.deepEqual(stage('packet-flush2').markers,['Y','Ms:P8']);
    assert.deepEqual(stage('packet-flush3').markers,['Ms:P8']);
    for(const name of ['packet-lastx-clean',...(repeat?['packet-lastx-repeat']:[])]) {
      const s=stage(name);assert.equal(s.words.aux0,NUMBER);
      assert.equal(s.words['Ms:P10'],NUMBER);assert.equal(s.display,'12345678,');
      assert.deepEqual(s.markers,['Ms:P8']);
    }
    for(const name of ['packet-sign-clean',...(repeat?['packet-sign-repeat']:[])]) {
      const s=stage(name);assert.equal(s.words.aux0,ONE);
      assert.equal(s.words['Ms:P10'],NUMBER);assert.equal(s.display,'1,');
      assert.deepEqual(s.markers,['Ms:P8']);
    }
    assert.equal(last.words.aux1,repeat?ONE:ZERO);
    assert.equal(v.report.packetAudit.numberHeld,!overwrite);
    if(overwrite) {
      assert.equal(last.words['Ms:P10'],ONE);assert.equal(last.words.aux0,ONE);
      assert.equal(last.display,'1,');assert.deepEqual(last.markers,['Ms:P8']);
      assert.equal(v.report.packetAudit.firstDifference.stage,'packet-sign-overwrite');
      assert.equal(v.report.packetAudit.firstDifference.actual,ONE);
    } else assert.equal(v.report.packetAudit.firstDifference,null);
    assert.equal(v.report.packetAudit.checkedWords,overwrite?359520:repeat?342720:309120);
  }
  assert.equal(last.pc,'06');assert.equal(last.ip,0x35);
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input'),negative:process.argv.includes('--no-cleanup'),
    repeat:!process.argv.includes('--once'),overwrite:process.argv.includes('--buffer-overwrite')});
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(v));
  else console.log(JSON.stringify({stages:v.exitStages.filter(s=>[
    'packet-flush1','packet-flush2','packet-flush3','packet-lastx-clean','packet-sign-clean',
    'packet-lastx-repeat','packet-sign-repeat','packet-sign-overwrite','packet-lastx','packet-sign-number','packet-idle'].includes(s.name))
    .map(s=>({name:s.name,keys:s.keys,display:s.display,words:s.words,markers:s.markers})),
    audit:v.report.packetAudit,onlyPublicKeys:v.report.onlyPublicKeys,ALL5mirror:v.report.ALL5mirror,
    boundary:'relocated P8 stack/LastX, not independent normal-geometry register or full K1/K2'}));
}
module.exports={run};
