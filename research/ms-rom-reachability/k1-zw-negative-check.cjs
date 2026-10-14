#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-zw-entry.cjs');
function check(r,source) {
  const lost=source==='P8'?r.before.P8.slice(2):r.before.Q.slice(2);
  assert.deepEqual(r.rows.filter(e=>e.missing.length).map(e=>[e.stage,e.missing]),
    [['immediate',[lost]],['done',[lost]]]);
  return {lostSource:source,lost,frameEvidenceOnly:true,wholeMachineImpossibility:false};
}
if(require.main===module) {
  if(process.env.K1_ZW_NEGATIVE!=='swap')console.log('PASS wrong ENTER phase:',JSON.stringify(check(probe.run({
    deepTail:[['K','0'],['В↑']],deepTailPhases:[1,1]}),'P8')));
  if(process.env.K1_ZW_NEGATIVE!=='enter')console.log('PASS immediate swap:',JSON.stringify(check(probe.run({
    afterW:[['↔']],afterWPhases:[0]}),'Q')));
}
module.exports={check};
