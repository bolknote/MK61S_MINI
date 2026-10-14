#!/usr/bin/env node
'use strict';
// Actual unsuccessful second-cell writer frontier. Preserve the first value
// explicitly in temporary realR6 and stage the second in realR7. The measured
// four-word/formatter path is NOT a two-hidden-number success.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const FIRST='007012345678',SECOND='007024681357',F='0000F0000000';
function run({proof=false,inputControl=false}={}) {
  const v=prepare({proof,phase:'yku',secondPhase:inputControl?'p9-write':'p9-source-write'});
  const get=n=>v.exitStages.find(s=>s.name===n),final=v.exitStages.at(-1);
  assert.equal(get('packet-second-backup-first').registers[6],FIRST);
  assert.equal(get('packet-second-port5-zero').words['Ms:P10'],FIRST);
  assert.deepEqual(get('packet-second-port5-zero').markers,['aux0']);
  if(inputControl) {
    assert.equal(get('packet-second-open5').words['Ms:P7'],F);
    assert.equal(get('packet-second-input4').words['Ms:P7'],F);
    assert.equal(get('packet-second-input5').words['Ms:P7'],'004024681000');
    assert.equal(final.words['Ms:P7'],SECOND);
    assert.equal(v.report.packetAudit.firstDifference.word,1847500);
  } else {
    assert.equal(get('packet-second-source-store').registers[7],SECOND);
    const before=get('packet-second-open4');assert.equal(before.words['Ms:P10'],FIRST);
    assert.equal(before.words.U,SECOND);assert.deepEqual(before.markers,['Z','V','aux0']);
    const after=get('packet-second-open5');assert.equal(after.words['Ms:P7'],SECOND);
    assert.equal(after.words['Ms:P10'],'3F7000000000');
    assert.deepEqual(after.markers,['Z','V','aux0']);
    assert.equal(final.words['Ms:P7'],SECOND);assert.equal(final.words['Ms:P9'],'FFF000000000');
    assert.equal(final.registers[6],FIRST);assert.equal(final.registers[7],SECOND);
    assert.equal(v.report.packetAudit.firstDifference.word,2015500);
  }
  assert.equal(v.report.packetAudit.numberHeld,false);
  assert.equal(v.report.packetAudit.firstDifference.stage,'packet-second-open5');
  assert.equal(final.display,'24681357,');
  assert.deepEqual(final.program,get('packet-second-port5-zero').program);
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input'),inputControl:process.argv.includes('--input-control')});
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(v));
  else console.log(JSON.stringify({endpoint:v.exitStages.at(-1),audit:v.report.packetAudit,
    onlyPublicKeys:true,ALL5mirror:true,boundary:'explicit failed frontier; first number is in ordinaryR6 reserve, NOT two hidden values'}));
}
module.exports={run};
