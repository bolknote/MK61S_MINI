#!/usr/bin/env node
'use strict';
// DATA-key writer candidate. FIRST is explicitly kept in its genuine R7
// readout while P10 may be consumed. No imported state/control/ROM repairs.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
function run({proof=false}={}) {
  const v=prepare({proof,phase:'yku',secondPhase:'p7-normal-retain-write3'});
  const stages=v.exitStages.filter(s=>s.name.startsWith('packet-third-'));
  return {...v,thirdDiagnostic:{audit:v.report.thirdAudit,oldFixedP10:v.report.packetAudit,
    stages:stages.map(s=>({name:s.name,display:s.display,markers:s.markers,
      R4:s.registers[4],R6:s.registers[6],R7:s.registers[7],R8:s.registers[8],
      P7:s.words['Ms:P7'],P9:s.words['Ms:P9'],P10:s.words['Ms:P10']})),
    boundary:'native writer candidate with explicit transient R7 holder; no third readback/canonical no-reserve work/full K1/K2 claim'}};
}
if(require.main===module){const v=run({proof:process.argv.includes('--proof-input')});console.log(JSON.stringify(process.argv.includes('--proof-input')?v:v.thirdDiagnostic));}
module.exports={run};
