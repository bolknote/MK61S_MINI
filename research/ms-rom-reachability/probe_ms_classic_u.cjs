#!/usr/bin/env node
'use strict';
// A native candidate derived from the secondary-chip X/Y exchange path.
// The false marker begins in X, not Y/Z. No reader program or 600/700 setup.
const assert=require('node:assert/strict');
const {prepare}=require('./probe_ms_classic_v.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');

function finish(calc,{settleFrames=8,markerFrames=12,phaseOffset=0,swapWait=0,preLifts=0}={},record=()=>{}) {
  assert.ok([0,1,2].includes(phaseOffset));
  assert.ok(Number.isInteger(settleFrames)&&settleFrames>=1);
  assert.ok(Number.isInteger(markerFrames)&&markerFrames>=1);
  assert.ok(Number.isInteger(swapWait)&&swapWait>=0);
  assert.ok([0,1].includes(preLifts),'one extra lift is a source-offset negative control');
  calc.runFrames(phaseOffset);const stages=[];
  const actions=[['clear-before',['Сx','В↑','В↑','В↑','+'],settleFrames],
    ...['Сx','K','-','ВП','K','0'].map((key,i)=>['make-marker-'+i,[key],markerFrames]),
    ...Array.from({length:preLifts},(_,i)=>['pre-lift-'+i,['П→X','3'],settleFrames]),
    ['swap-read-u',['↔'],swapWait],['save-u',['X→П','9'],settleFrames],
    ...Array.from({length:4},(_,i)=>['remove-marker-'+(i+1),['П→X','3'],settleFrames]),
    ['clear-after',['Сx','В↑','В↑','В↑','+'],settleFrames]];
  for(const [label,keys,frames] of actions) {
    record(label);calc.pressSequence(keys).runFrames(frames);
    stages.push({label,display:calc.displayText()});
  }
  return stages;
}

function runPrepared(calc,options={}) {
  const before=fullMsPages(calc),beforeRegisters=registers(calc),beforeProgram=program(calc);
  assert.equal(beforeRegisters[3],'000000000000','explicit zero P3 required');
  let stage='',stages=[],seen=new Set();
  const record=label=>{stage=label;};
  const traced=trace(calc,c=>{
    stages=finish(c,options,record);record('done');c.runFrames(3);
  },{extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
    otherChipsAt:e=>['swap-read-u','save-u'].includes(stage),
    ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
      return first||[0xEE,0xE7,0xD4,0xD6,0xAD,0xA8,0xA9,0xAC,0xA2,0xA3].includes(e.ip)||
        [0x4E,0x2A,0x39].includes(e.otherChips?.[4].ip);}});
  aligned(calc);
  return {calc,options,stages,traced,before,after:fullMsPages(calc),
    beforeRegisters,afterRegisters:registers(calc),beforeProgram,afterProgram:program(calc)};
}
function run(options={}) {return runPrepared(prepare(options),options);}
if(require.main===module) {
  const r=run(process.argv[2]?JSON.parse(process.argv[2]):{});
  console.log(JSON.stringify({options:r.options,stages:r.stages,before:r.before,after:r.after,
    p9:r.afterRegisters[9],msUnchanged:JSON.stringify(r.before)===JSON.stringify(r.after),
    programUnchanged:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram)},null,2));
}
module.exports={prepare,finish,run,runPrepared};
