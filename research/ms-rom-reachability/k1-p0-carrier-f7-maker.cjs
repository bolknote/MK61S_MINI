#!/usr/bin/env node
'use strict';
// Rejected fixed-key maker: 0.7 yields E7, not the required F7.
const assert=require('node:assert/strict');
const capture=require('./k1-bank-v-capture.cjs');
const retained=require('./k1-bank-marker-tail-check.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {rawStack}=require('./k1-p0-carrier-or-maker.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const markerActions=[['Сx'],['+'],['0',',','7'],['K','-'],['ВП'],['K','0'],['ВП'],['1']];
function run(o={}) {
  const c=capture.prepare(o),before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  retained.operation(c,{...o,recoverCapture:true},()=>{});
  for(const keys of markerActions)c.pressSequence(keys).runFrames(8);
  aligned(c);const stack=rawStack(c),after=fullMsPages(c),afterRegisters=registers(c),afterProgram=program(c);
  assert.deepEqual(after,before);assert.deepEqual(afterProgram,beforeProgram);
  assert.deepEqual(afterRegisters,beforeRegisters.map((v,i)=>i===0?before.V.slice(2):v));
  assert.deepEqual(['X','Y','Z','T'].map(n=>stack[n]),['0010E7000000',beforeRegisters[0],before.V.slice(2),before.V.slice(2)]);
  assert.notEqual(stack.X,'0010F7000000','E7 is not a marker and cannot be substituted for F7');
  return {stack,p0:afterRegisters[0],requiredMarkerAbsent:true,allMsHeld:true,other14RegistersHeld:true,programHeld:true};
}
if(require.main===module)console.log('PASS rejected F7 maker:',JSON.stringify(run()));
module.exports={markerActions,run};
