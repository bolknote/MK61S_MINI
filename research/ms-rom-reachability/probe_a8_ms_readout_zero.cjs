#!/usr/bin/env node
'use strict';
// Second native readout: a zero-register recall replaces ENTER, and the
// already-normal return is not subjected to the older F AVT recovery.
const readout=require('./probe_a8_ms_readout.cjs');
function run(options={}) {
  return readout.run({markerLift:'recall-zero',autoRecovery:false,...options});
}
function runPrepared(calc,options={}) {
  return readout.runPrepared(calc,{markerLift:'recall-zero',autoRecovery:false,...options});
}
if(require.main===module) {
  const r=run(process.argv[2]?JSON.parse(process.argv[2]):{});
  console.log(JSON.stringify({options:r.options,stages:r.stages,before:r.before,after:r.after,
    u:r.before.U.slice(2),p9:r.afterRegisters[9],v:r.before.V.slice(2),p2:r.afterRegisters[2],
    programUnchanged:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    c9:r.traced.events.filter(e=>e.ip===0xC9).map(e=>({stage:e.stage,slot:e.slot,pc:e.pc}))},null,2));
}
module.exports={run,runPrepared};
