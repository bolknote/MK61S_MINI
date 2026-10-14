#!/usr/bin/env node
'use strict';
// Native-key upper-pair reader with a tested marker-removal continuation.
// Outputs: old Ms P7 -> ordinary P8, old Ms P8 -> ordinary P0.
// Ms is NOT restored: the upper pair stays swapped; U/V/W/Q are modified.
// Tested domain includes P3=0 and nonnegative initial U exponent. The prior
// swap has an explicit counterexample for old fifth=0, sixth=-1E-99.
const candidate=require('./probe_ms_upper_marked_return.cjs');
const {inputLiteral}=require('./probe_c8_payload.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const loadD=['K','П→X','Сx'],loadE=['K','П→X','В↑'];
const optionsFor=(o={})=>({...o,pointer:'0',fifthCopyKey:'8',p1Pointer:'111',dPointer:'3',traceFormatterExit:true,
  afterKeys:[...Array.from({length:o.zeroLoads??3},()=>loadD),loadE,loadD,
    ['П→X','4'],['П→X','3'],['П→X','3'],['Сx','В↑','В↑','В↑','+']]});
function prepare(o={}) {
  const c=candidate.prepare(optionsFor(o));
  // Indirect index 6 increments 9 to decimal 10 before storing X in A.
  // This creates normalized P6=007000000010; ordinary A=9 is scratch.
  inputLiteral(c,'9');c.pressSequence(['X→П','6','K','X→П','6']);
  return aligned(c);
}
const finish=(c,o={},record=()=>{})=>candidate.finish(c,optionsFor(o),record);
const runPrepared=(c,o={})=>candidate.runPrepared(c,optionsFor(o));
const run=(o={})=>runPrepared(prepare(o),o);
if(require.main===module)console.log(JSON.stringify(candidate.brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,optionsFor};
