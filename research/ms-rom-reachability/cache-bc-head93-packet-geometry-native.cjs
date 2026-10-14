#!/usr/bin/env node
'use strict';
// Native return of aux0/F, removal of old P8/F and one temporaryX1/F.
// It is a PARTIAL geometry restoration: X/W/Q/aux1 flags still interfere.
// Fixed public keys, guarded original references/observer-free full mirrors.
// Optional clock control uses24+6 REAL idle words, never a phase/state patch;
// the preferred protocol demonstrably needs NO additional precise pause.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const NUMBER='007012345678',F='0000F0000000',ZERO='000000000000',ONE='000010000000';
const labels=['packet-restore-aux0F','packet-restore-clone1','packet-restore-clone2',
  'packet-restore-TF','packet-restore-X1F','packet-restore-removeP8'];
function run({proof=false,clock=false,bridge=false}={}) {
  const v=prepare({proof,phase:bridge?'yc6':clock?'yc7':'yc7z'});
  const stage=n=>v.exitStages.find(s=>s.name===n),inlet=stage('packet-sign-repeat'),last=v.exitStages.at(-1);
  assert.deepEqual(inlet.markers,['Ms:P8']);assert.equal(inlet.words['Ms:P10'],NUMBER);
  const expected=[['Ms:P8','aux0'],['Ms:P8','aux0','aux1'],['X','Ms:P8','aux0','aux1'],
    ['X','T','Ms:P8','aux0','aux1'],['X','X1','W','Ms:P8','aux0','aux1'],
    ['X','X1','W','Q','aux0','aux1']];
  labels.forEach((name,i)=>assert.deepEqual(stage(name).markers,expected[i]));
  assert.equal(stage('packet-restore-removeP8').words['Ms:P8'],ZERO);
  assert.equal(stage('packet-restore-removeP8').words['Ms:P9'],ONE);
  for(const s of v.exitStages.filter(s=>s.name.startsWith('packet-restore-')||s.name==='packet-idle')) {
    assert.deepEqual(s.registers,inlet.registers);assert.deepEqual(s.program,inlet.program);
    assert.equal(s.words['Ms:P10'],NUMBER);assert.equal(s.words.aux0,F);
  }
  assert.deepEqual(last.markers,bridge?expected.at(-1):['X','W','Q','aux0','aux1']);
  assert.equal(last.words['Ms:P10'],NUMBER);
  if(!bridge) {
    assert.equal(stage('packet-restore-cx').display,'ЕГГ0Г');
    assert.equal(last.words.X1,ZERO);assert.equal(last.words.U,'FFF000000000');
    assert.equal(last.words['Ms:P8'],ONE);
  }
  assert.equal(last.display,'1,');assert.equal(last.pc,'06');assert.equal(last.ip,0x35);
  assert.equal(v.report.packetAudit.numberHeld,true);assert.equal(v.report.packetAudit.firstDifference,null);
  assert.equal(v.report.packetAudit.checkedWords,bridge?443520:clock?468750:468720);
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input'),clock:process.argv.includes('--clock-control'),
    bridge:process.argv.includes('--bridge-only')});
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(v));
  else console.log(JSON.stringify({stages:v.exitStages.filter(s=>s.name.startsWith('packet-restore-')
    ||s.name==='packet-idle').map(s=>({name:s.name,keys:s.keys,markers:s.markers,words:s.words,
      display:s.display,pc:s.pc})),audit:v.report.packetAudit,
    onlyPublicKeys:v.report.onlyPublicKeys,ALL5mirror:v.report.ALL5mirror,
    boundary:'aux0 restored, P8/X1 removed; X/W/Q/aux1 remain, normal arithmetic/independence/full K1/K2 unproved'}));
}
module.exports={run,labels};
