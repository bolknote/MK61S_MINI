#!/usr/bin/env node
'use strict';
// Fresh public-key native preparation, then the derived two-key-command tail.
// This asserts three bank words, not a usable no-reserve three-word cycle.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
function run({proof=false,negativeCX=false}={}){
  const v=prepare({proof,phase:'yku',secondPhase:negativeCX?'p7-normal-retain-restore3-cx':'p7-normal-retain-restore3'});
  const a=v.report.thirdRestoreAudit;
  assert.ok(a.holdersHeld&&a.bankReady);
  assert.equal(a.bankHeld,!negativeCX);
  assert.equal(a.holderDifference,null);
  if(negativeCX){assert.equal(a.bankDifference.stage,'packet-third-restore-CX');
    assert.deepEqual(a.bankDifference.bank,{P7:'FFF024681357',P9:'007012345678',P10:'950013579246'});}
  else assert.equal(a.bankDifference,null);
  assert.equal(v.report.thirdAudit.thirdHeld,false,'old fixed P9 third-slot audit must report the intentional relocation');
  assert.equal(v.report.packetAudit.numberHeld,false,'old fixed P10 first-slot loss must remain visible');
  const stages=v.exitStages.filter(s=>s.name==='packet-third-write-P9'||s.name.startsWith('packet-third-restore-')||s.name==='packet-idle');
  return{...v,restoration:{audit:a,onlyPublicKeys:v.report.onlyPublicKeys,ALL5mirror:v.report.ALL5mirror,
    stages:stages.map(s=>({name:s.name,display:s.display,markers:s.markers,
      bank:{P7:s.words['Ms:P7'],P9:s.words['Ms:P9'],P10:s.words['Ms:P10']},
      R4:s.registers[4],R6:s.registers[6],R7:s.registers[7],R8:s.registers[8]}))}};
}
if(require.main===module)console.log(JSON.stringify(run({negativeCX:process.argv.includes('--negative-cx')}).restoration));
module.exports={run};
