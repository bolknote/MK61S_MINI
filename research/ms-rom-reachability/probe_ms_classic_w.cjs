#!/usr/bin/env node
'use strict';
// Move the same direct-store marker one slot farther: T + 3 = W.
// Destination P1 keeps both previous U/P9 and V/P2 results available.
// CONDITIONAL: negative-exponent U can be accepted as false control and
// redirect the store to X. The default fixture has a nonnegative U exponent.
const v=require('./probe_ms_classic_v.cjs');
const optionsFor=o=>({...o,lifts:3,destination:o?.destination??1});
const prepare=(o={})=>v.prepare({values:['111','222','333','444'],...o});
const finish=(calc,options={},record)=>v.finish(calc,optionsFor(options),record);
const runPrepared=(calc,options={})=>v.runPrepared(calc,optionsFor(options));
const run=(options={})=>runPrepared(prepare(options),options);
if(require.main===module) {
  const r=run(process.argv[2]?JSON.parse(process.argv[2]):{});
  console.log(JSON.stringify({before:r.before,after:r.after,p1:r.afterRegisters[1],
    programUnchanged:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram)},null,2));
}
module.exports={prepare,finish,runPrepared,run};
