#!/usr/bin/env node
'use strict';
// Keyboard-only P9 -> U, old U/V/W -> V/W/Q. Old Q is discarded.
// Unlike the fixture writer, this operation installs no user program.
const assert=require('node:assert/strict');
const shifted=require('./probe_ms_shifted_swap.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const optionsFor=o=>({...o,lifts:1,sourceKey:['П→X','9'],save:false});
function prepare(options={}) {
  const calc=shifted.prepare(options),before=fullMsPages(calc);
  inputLiteral(calc,options.source??'12345678');
  calc.pressSequence(['X→П','9']).runFrames(8);aligned(calc);
  assert.deepEqual(fullMsPages(calc),before,'preparing ordinary P9 must preserve Ms');
  return calc;
}
function finish(calc,options={},record=()=>{}) {return shifted.finish(calc,optionsFor(options),record);}
function runPrepared(calc,options={}) {return shifted.runPrepared(calc,optionsFor(options));}
function run(options={}) {return runPrepared(prepare(options),options);}
function fill4FromRegisters(calc,options={}) {
  // P3 must be zero. P4..P7 are retained; P9 is explicit scratch and ends
  // equal to P4. No observer, alignment helper or reset between pushes.
  for(const source of ['7','6','5','4']) {
    calc.pressSequence(['П→X',source,'X→П','9']).runFrames(options.settleFrames??8);
    finish(calc,options);
  }
  return calc;
}
if(require.main===module) {
  const r=run(process.argv[2]?JSON.parse(process.argv[2]):{});
  console.log(JSON.stringify({source:r.beforeRegisters[9],before:r.before,after:r.after,
    registersPreserved:JSON.stringify(r.beforeRegisters)===JSON.stringify(r.afterRegisters),
    programPreserved:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram)},null,2));
}
module.exports={prepare,finish,runPrepared,run,optionsFor,fill4FromRegisters};
