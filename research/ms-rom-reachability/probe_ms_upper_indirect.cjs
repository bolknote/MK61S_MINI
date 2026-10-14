#!/usr/bin/env node
'use strict';
// Conditional sixth-word reader: two physical pointer copies compensate for
// the two possible first M1 reads. No intact-Ms return is claimed here.
const upper=require('./probe_ms_upper_swap.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {inputLiteral}=require('./probe_c8_payload.cjs');
function prepare(o={}) {
  const calc=upper.prepare(o);
  inputLiteral(calc,o.pointer??'1');
  calc.pressSequence(['X→П','5','X→П','ВП']);
  return aligned(calc);
}
const optionsFor=o=>({...o,afterKeys:[['K','X→П','ВП'],...(o.afterKeys||[])]});
const finish=(c,o={},record=()=>{})=>upper.finish(c,optionsFor(o),record);
const runPrepared=(c,o={})=>upper.runPrepared(c,optionsFor(o));
const run=(o={})=>runPrepared(prepare(o),o);
if(require.main===module)console.log(JSON.stringify(upper.brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,optionsFor};
