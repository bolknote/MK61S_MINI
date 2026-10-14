#!/usr/bin/env node
'use strict';
// A candidate loader after the sixth-word backup. Index B uses two already
// normalized pointers so both first D6 positions start the next 01 search
// before V. Pointer 8 then compensates the hidden marker's M1 displacement.
const upper=require('./probe_ms_upper_indirect.cjs');
const {inputLiteral}=require('./probe_c8_payload.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
function preparePointers(calc) {
  inputLiteral(calc,'8');calc.pressSequence(['X→П','/-/','K','X→П','/-/']);
  // Ordinary index 4 increments its pointer: canonical 7 becomes raw 8.
  inputLiteral(calc,'7');calc.pressSequence(['X→П','4','K','X→П','4']);
  return calc;
}
const prepare=(o={})=>aligned(preparePointers(upper.prepare(o)));
const optionsFor=o=>({...o,afterKeys:[
  ...Array.from({length:o.loads??1},()=>['K','П→X','/-/']),...(o.afterKeys||[])]});
const finish=(c,o={},record=()=>{})=>upper.finish(c,optionsFor(o),record);
const runPrepared=(c,o={})=>upper.runPrepared(c,optionsFor(o));
const run=(o={})=>runPrepared(prepare(o),o);
if(require.main===module) {
  const r=run(process.argv[2]?JSON.parse(process.argv[2]):{});
  console.log(JSON.stringify(require('./probe_ms_upper_swap.cjs').brief(r),null,2));
}
module.exports={preparePointers,prepare,finish,runPrepared,run,optionsFor};
