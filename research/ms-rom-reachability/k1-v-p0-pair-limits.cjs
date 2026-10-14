#!/usr/bin/env node
'use strict';
// Small observer-free negative controls. These reject complete pair claims,
// rather than accepting a correct P0/V with collateral damage elsewhere.
const assert=require('node:assert/strict');
const pair=require('./k1-v-p0-pair.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const cases=[{label:'wrong initial phase',options:{phaseOffset:1}},
  {label:'positive-order U rejected as control',options:{phaseOffset:2,values:['111','222','333','444']}},
  {label:'q5 collateral W write',options:{phaseOffset:2,incoming:'-1.23E-42'}}];
function run(test) {
  const c=capture.prepare(test.options),before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  aligned(c);pair.finish(c,test.options);c.runFrames(3);aligned(c);
  const after=fullMsPages(c),afterRegisters=registers(c),afterProgram=program(c);
  const wanted={...before,V:before.V.slice(0,2)+beforeRegisters[0]};
  const expected=test.options.incoming?
    {...wanted,W:before.W.slice(0,2)+beforeRegisters[0]}:
    {...before,U:before.U.slice(0,2)+'1F2'+before.U.slice(5),
      W:before.W.slice(0,2)+before.Q.slice(2),Q:before.Q.slice(0,2)+before.W.slice(2)};
  assert.deepEqual(after,expected);
  assert.notDeepEqual(after,wanted,'collateral changes mean the full pair did not succeed');
  assert.deepEqual(afterRegisters,beforeRegisters.map((v,i)=>i===0?before.V.slice(2):v));
  assert.deepEqual(afterProgram,beforeProgram);
  return {label:test.label,options:test.options,
    changedMs:Object.keys(before).filter(n=>before[n]!==after[n]),
    pairValuesCorrect:after.V===wanted.V,other14RegistersHeld:true,programHeld:true,validPair:false};
}
if(require.main===module)for(const test of cases)console.log('PASS exact negative pair control:',JSON.stringify(run(test)));
module.exports={cases,run};
