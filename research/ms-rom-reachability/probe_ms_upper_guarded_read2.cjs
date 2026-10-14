#!/usr/bin/env node
'use strict';
// A fixed guard word replaces old Ms P7 AFTER its backup, before the swap.
// This removes the zero-fifth stale-formatter counterexample in tested cases.
// Destructive Ms operation: final P8 contains the guard, not the old fifth.
const handoff=require('./probe_ms_swap_handoff.cjs');
const optionsFor=(o={})=>({...o,mode:'keyboard',primeKeys:['П→X','4']});
const prepare=(o={})=>handoff.prepare(optionsFor(o));
const finish=(c,o={},record=()=>{})=>handoff.finish(c,optionsFor(o),record);
const runPrepared=(c,o={})=>handoff.runPrepared(c,optionsFor(o));
const run=(o={})=>runPrepared(prepare(o),o);
if(require.main===module)console.log(JSON.stringify(handoff.analyze(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,optionsFor};
