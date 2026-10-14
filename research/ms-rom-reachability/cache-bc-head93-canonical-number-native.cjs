#!/usr/bin/env node
'use strict';
// A transient realP5/F port creates Y/X1 directly, avoiding the W/Q flag
// bridge. Restore only aux0/F and P5/0, then exercise normal2 ENTER3+,
// realR2 store/recall/restore and NORMAL LastX3, while hiddenP10 holds12345678.
// All actions on fresh guarded originals/full mirrors. No live hardware,
// setters, ROM edits, state/phase patches or model state imports.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const NUMBER='007012345678',ZERO='000000000000',F='0000F0000000',FIVE='000050000000',THREE='000030000000';
function run({proof=false}={}) {
  const v=prepare({proof,phase:'ykm'}),get=n=>v.exitStages.find(s=>s.name===n);
  const inlet=get('packet-sign-repeat'),restored=get('packet-clean-port5-zero'),final=v.exitStages.at(-1);
  assert.equal(get('packet-clean-port5').registers[5],F);
  assert.deepEqual(get('packet-clean-P8').markers,['Y','X1','aux0']);
  assert.equal(get('packet-clean-flush1').display,'ЕГГ0Г');
  assert.deepEqual(get('packet-clean-flush5').markers,['aux0']);
  assert.deepEqual(restored.markers,['aux0']);assert.equal(restored.registers[5],ZERO);
  assert.deepEqual(restored.registers,inlet.registers);assert.deepEqual(restored.program,inlet.program);
  for(const s of v.exitStages.filter(s=>s.name.startsWith('packet-clean-')||s.name==='packet-idle'))
    assert.equal(s.words['Ms:P10'],NUMBER);
  for(const name of ['packet-clean-cx1','packet-clean-cx2','packet-clean-register-clear','packet-clean-register-clear2'])
    assert.equal(get(name).display,'0,');
  assert.equal(get('packet-clean-plus').display,'5,');
  assert.equal(get('packet-clean-plus').words.Y,FIVE);
  assert.equal(get('packet-clean-plus').words.X,THREE);
  assert.equal(get('packet-clean-store2').registers[2],FIVE);
  assert.equal(get('packet-clean-read2').display,'5,');
  assert.equal(get('packet-clean-register-zero2').registers[2],ZERO);
  assert.equal(get('packet-clean-lastx').display,'3,');
  assert.equal(final.display,'0,');assert.deepEqual(final.markers,['aux0']);
  assert.equal(final.words.aux0,F);assert.equal(final.words['Ms:P10'],NUMBER);
  assert.deepEqual(Object.keys(final.words).filter(n=>final.words[n]===NUMBER),['Ms:P10']);
  assert.deepEqual(get('packet-clean-lastx').registers,inlet.registers);
  const expected=inlet.registers.slice();expected[14]=ZERO;
  assert.deepEqual(final.registers,expected);assert.ok(!final.registers.includes(NUMBER));
  assert.deepEqual(final.program,inlet.program);
  assert.equal(final.pc,'06');assert.equal(final.ip,0x35);
  assert.equal(v.report.packetAudit.checkedWords,754320);
  assert.equal(v.report.packetAudit.numberHeld,true);assert.equal(v.report.packetAudit.firstDifference,null);
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input')});
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(v));
  else console.log(JSON.stringify({stages:v.exitStages.filter(s=>s.name.startsWith('packet-clean-')||s.name==='packet-idle')
    .map(s=>({name:s.name,keys:s.keys,markers:s.markers,display:s.display,P10:s.words['Ms:P10'],R2:s.registers[2],R5:s.registers[5]})),
    audit:v.report.packetAudit,onlyPublicKeys:true,ALL5mirror:true,
    boundary:'one NUM fixture survives ordinary arithmetic/register access; reverse hidden read, arbitrary old-bank preservation, full K1/K2 not yet established'}));
}
module.exports={run};
