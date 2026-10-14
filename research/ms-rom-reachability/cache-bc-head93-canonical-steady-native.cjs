#!/usr/bin/env node
'use strict';
// Third/fourth hidden read from an already spentP7 endpoint. Same complete
// fixed key/timing cycle, all five mutable chip fields/caches/UI/tags compared.
// Fresh guarded stock originals and full mirrors. No state imports or repairs.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const {baseline:ordinaryBaseline}=require('./cache-bc-head93-q-normal-roundtrip-native.cjs');
const ZERO='000000000000',SEVEN='000070000000',THIRTEEN='001013000000';
function run({proof=false,repeats=2,normalInput='12345678'}={}) {
  assert.ok([2,3].includes(repeats));
  const ordinary=ordinaryBaseline(normalInput),NUMBER=ordinary.word;
  const v=prepare({proof,phase:'yku',repeat:true,repeatClear:true,repeatCount:repeats,normalInput});
  assert.equal(v.report.normalWord,NUMBER);
  const get=n=>v.exitStages.find(s=>s.name===n),steady=get('packet-repeat-idle'),final=v.exitStages.at(-1);
  assert.equal(steady.display,ordinary.display);assert.equal(steady.words['Ms:P7'],ZERO);
  for(let i=2;i<=repeats;i++) {
    const prefix='packet-repeat'+i+'-';
    const restored=get(prefix+'port5-zero'),math=get(prefix+'plus'),read=get(prefix+'reopen-lastx');
    assert.deepEqual(restored.markers,['aux0']);assert.deepEqual(restored.registers,steady.registers);
    assert.deepEqual(Object.keys(restored.words).filter(n=>restored.words[n]===NUMBER),['Ms:P10']);
    assert.equal(math.display,'13,');assert.equal(math.words.Y,THIRTEEN);assert.equal(math.words.X,SEVEN);
    assert.equal(get(prefix+'lastx').display,'7,');
    assert.equal(read.display,ordinary.display);assert.deepEqual(read.words,steady.words);
    for(const s of v.exitStages.filter(s=>s.name.startsWith(prefix))) {
      assert.equal(s.words['Ms:P10'],NUMBER);assert.equal(s.words['Ms:P7'],ZERO);
      assert.equal(s.registers[14],ZERO);assert.ok(!s.registers.includes(NUMBER));
      assert.deepEqual(s.program,steady.program);
    }
  }
  assert.deepEqual(final.words,steady.words);assert.deepEqual(final.registers,steady.registers);
  assert.equal(final.pc,'06');assert.equal(final.ip,0x35);
  const baseline=v.nativeIdleStates['packet-repeat-idle'];assert.ok(baseline);
  for(const [name,state] of Object.entries(v.nativeIdleStates))assert.deepEqual(state,baseline,
    'EXACT native steady endpoint '+name+', all mutable five-chip fields/caches/UI/630 tags; not just display');
  assert.equal(v.report.packetAudit.checkedWords,repeats===2?2088240:2666160);
  assert.equal(v.report.packetAudit.numberHeld,true);assert.equal(v.report.packetAudit.firstDifference,null);
  v.baseline=ordinary;return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input'),repeats:process.argv.includes('--fourth')?3:2,
    normalInput:process.argv.includes('--negative')?'-87654321':process.argv.includes('--small')?'1.2345678E-50':'12345678'});
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(v));
  else console.log(JSON.stringify({stages:v.exitStages.filter(s=>s.name==='packet-repeat-idle'||
    /^packet-repeat[23]-(port5-zero|plus|lastx|preclear4|reopen-lastx|idle)$/.test(s.name)||s.name==='packet-idle')
    .map(s=>({name:s.name,display:s.display,markers:s.markers,P7:s.words['Ms:P7'],P10:s.words['Ms:P10']})),
    audit:v.report.packetAudit,exactNativeEndpoint:true,onlyPublicKeys:true,ALL5mirror:true,
    boundary:'fixed integer, fixed complete key/timing cycle in stock model; not arbitrary operations/data, live hardware or full K1/K2'}));
}
module.exports={run};
