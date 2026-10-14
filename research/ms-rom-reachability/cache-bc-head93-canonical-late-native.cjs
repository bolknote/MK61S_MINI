#!/usr/bin/env node
'use strict';
// Geometry is prepared with the known safe integer. AFTER ordinary reserve
// erasure, ordinary numeric keys enter a new value; SIGN/E9 deliberately
// rewrites physicalP10. Then two normal-work/read cycles preserve the new data.
// Fresh guarded originals/full mirrors, no ROM/state/phase edits or imports.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const {baseline:ordinaryBaseline}=require('./cache-bc-head93-q-normal-roundtrip-native.cjs');
const OLD='007012345678',ZERO='000000000000';
function run({proof=false,lateNumber='1.2345678E-50'}={}) {
  assert.ok(['2468','1.2345678E-50'].includes(lateNumber));
  const ordinary=ordinaryBaseline(lateNumber),wanted=ordinary.word;
  const v=prepare({proof,phase:'yku',repeat:true,repeatClear:true,repeatCount:2,lateNumber});
  const get=n=>v.exitStages.find(s=>s.name===n),inlet=get('packet-reopen-lastx'),final=v.exitStages.at(-1);
  const entered=get('packet-late-key'+lateNumber.length),written=get('packet-late-sign');
  assert.equal(inlet.words['Ms:P10'],OLD);assert.equal(inlet.registers[14],ZERO);
  assert.equal(entered.display,ordinary.display);assert.equal(entered.words.aux0,wanted);
  assert.equal(entered.words['Ms:P10'],OLD);assert.equal(written.words['Ms:P10'],wanted);
  assert.equal(written.display,'1,');assert.deepEqual(written.markers,['Ms:P8']);
  for(const s of v.exitStages.filter(s=>s.name.startsWith('packet-late-')||s.name.startsWith('packet-repeat')||s.name==='packet-idle')) {
    assert.deepEqual(s.program,inlet.program);assert.ok(!s.registers.includes(wanted));
    assert.deepEqual(s.registers.map((n,i)=>i===5?ZERO:n),inlet.registers);
    if(s.name==='packet-late-sign'||s.name.startsWith('packet-repeat')||s.name==='packet-idle')
      assert.equal(s.words['Ms:P10'],wanted);
  }
  for(const prefix of ['packet-repeat-','packet-repeat2-']) {
    const restored=get(prefix+'port5-zero');assert.deepEqual(restored.markers,['aux0']);
    assert.deepEqual(restored.registers,inlet.registers);
    assert.deepEqual(Object.keys(restored.words).filter(n=>restored.words[n]===wanted),['Ms:P10']);
    assert.equal(get(prefix+'plus').display,'13,');assert.equal(get(prefix+'lastx').display,'7,');
    assert.equal(get(prefix+'reopen-lastx').display,ordinary.display);
  }
  assert.equal(final.display,ordinary.display);assert.equal(final.words.aux0,wanted);
  assert.equal(final.words['Ms:P10'],wanted);assert.equal(final.words['Ms:P7'],ZERO);
  assert.equal(final.pc,'06');assert.equal(final.ip,0x35);assert.deepEqual(final.markers,['Ms:P8']);
  assert.deepEqual(v.nativeIdleStates['packet-repeat-idle'],v.nativeIdleStates['packet-idle']);
  const audit=v.report.lateNumberAudit,word=lateNumber==='2468'?1536700:1612300;
  assert.equal(audit.checkedWords,lateNumber==='2468'?2147040:2222640);
  assert.equal(audit.contractHeld,true);assert.equal(audit.firstDifference,null);
  assert.deepEqual(audit.writes,[{word,stage:'packet-late-sign',ip:0xE9,target:'Ms:P10',actual:wanted}]);
  // Preserve the old-value diagnostic: its first loss is the intentional
  // E9 write, not silently relabeled as perpetual preservation of OLD.
  assert.equal(v.report.packetAudit.numberHeld,false);
  assert.deepEqual(v.report.packetAudit.firstDifference,{word,stage:'packet-late-sign',moment:'after',actual:wanted});
  v.baseline=ordinary;return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input'),lateNumber:process.argv.includes('--integer')?'2468':'1.2345678E-50'});
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(v));
  else console.log(JSON.stringify({baseline:v.baseline,
    stages:v.exitStages.filter(s=>['packet-late-sign','packet-repeat-port5-zero','packet-repeat-plus',
      'packet-repeat-reopen-lastx','packet-repeat2-plus','packet-repeat2-reopen-lastx','packet-idle'].includes(s.name))
      .map(s=>({name:s.name,display:s.display,P10:s.words['Ms:P10'],markers:s.markers})),
    ledger:v.report.lateNumberAudit,exactNativeRepeat:true,onlyPublicKeys:true,ALL5mirror:true,
    boundary:'one cell, two late values, fixed ordinary work/keys/timing; not arbitrary bank or full K1/K2'}));
}
module.exports={run};
