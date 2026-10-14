#!/usr/bin/env node
'use strict';
// Read hiddenP10 AFTER canonical normal arithmetic/register/LastX work and
// explicit ordinaryRE backup erasure. Fixed public keys on fresh originals
// and full observer-free mirrors; no ROM/state/phase patches or state imports.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const NUMBER='007012345678',ZERO='000000000000';
function run({proof=false,wrongSource=false}={}) {
  const v=prepare({proof,phase:wrongSource?'ykv':'yku'}),get=n=>v.exitStages.find(s=>s.name===n);
  const inlet=get('packet-clean-backup-zero'),final=v.exitStages.at(-1);
  assert.deepEqual(inlet.markers,['aux0']);assert.equal(inlet.display,'0,');
  assert.equal(get('packet-clean-plus').display,'5,');
  assert.equal(get('packet-clean-read2').display,'5,');
  assert.equal(get('packet-clean-lastx').display,'3,');
  assert.equal(inlet.registers[14],ZERO);assert.ok(!inlet.registers.includes(NUMBER));
  for(const s of v.exitStages.filter(s=>s.name.startsWith('packet-reopen-')||s.name==='packet-idle')) {
    assert.deepEqual(s.registers,inlet.registers);assert.deepEqual(s.program,inlet.program);
    assert.equal(s.words['Ms:P10'],NUMBER);
  }
  if(wrongSource) {
    assert.equal(final.display,'0,');assert.deepEqual(final.markers,['Z','T','Ms:P8','aux0']);
  } else {
    assert.deepEqual(get('packet-reopen-aux0zero-native').markers,['Z','Ms:P8','aux1']);
    assert.deepEqual(get('packet-reopen-Zzero').markers,['Ms:P8','aux1']);
    assert.deepEqual(get('packet-reopen-flush3').markers,['Ms:P8']);
    assert.deepEqual(final.markers,['Ms:P8']);assert.equal(final.display,'12345678,');
    assert.equal(final.words.aux0,NUMBER);
  }
  assert.equal(final.ip,0x35);assert.equal(final.pc,'06');
  assert.equal(v.report.packetAudit.checkedWords,939120);
  assert.equal(v.report.packetAudit.numberHeld,true);assert.equal(v.report.packetAudit.firstDifference,null);
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input'),wrongSource:process.argv.includes('--wrong-source-control')});
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(v));
  else console.log(JSON.stringify({stages:v.exitStages.filter(s=>s.name.startsWith('packet-reopen-')||s.name==='packet-idle')
    .map(s=>({name:s.name,keys:s.keys,markers:s.markers,display:s.display,P10:s.words['Ms:P10']})),
    audit:v.report.packetAudit,onlyPublicKeys:true,ALL5mirror:true,
    boundary:'one hidden numerical fixture read after normal work; current read mode is relocatedP8, clean repeat/full bank/K1/K2 still remain'}));
}
module.exports={run};
