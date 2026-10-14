#!/usr/bin/env node
'use strict';
// Guarded six-word backup. P2 is free in the original six-word layout.
// This removes the early zero-fifth loss; it does NOT implement the new exit.
const base=require('./probe_ms_read6_backup.cjs');
const {inputLiteral}=require('./probe_c8_payload.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const optionsFor=(o={})=>({...o,beforeSwapKeys:['П→X','2'],traceFormatterExit:true,traceSecondary:true});
function prepare(o={}) {
  const c=base.prepare(o);inputLiteral(c,'-1.2345678E-42');c.pressSequence(['X→П','2']);
  return aligned(c);
}
const finish=(c,o={},record=()=>{})=>base.finish(c,optionsFor(o),record);
const runPrepared=(c,o={})=>base.runPrepared(c,optionsFor(o));
const run=(o={})=>runPrepared(prepare(o),o);
if(require.main===module)console.log(JSON.stringify(base.brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,optionsFor};
