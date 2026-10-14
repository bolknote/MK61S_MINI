#!/usr/bin/env node
'use strict';
// Derived from the ring positions of AA -> E5 and the M1 store helper.
// No injected state, breakpoint timing, or altered ROM. Unlike the earlier
// ENTER readout, the source is stored before it can become a display value.
const marker=require('./probe_a8_marker_route.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');

function normalized(options={}) {
  return {values:['111','222','333','-1.2345678E-42'],seedLowDigit:0,
    clearKey:'8',markerLifts:2,markerLift:'recall-zero',finalRecall:false,
    ...options};
}

function finish(calc,options={},record=()=>{}) {
  options=normalized(options);
  const stages=marker.finish(calc,options,record);
  for(const [label,keys] of [['save-v-direct',['X→П','2']],
    ['remove-marker-1',['П→X','3']],['remove-marker-2',['П→X','3']],
    ['clear-stack',['Сx','В↑','В↑','В↑','+']]]) {
    record(label);calc.pressSequence(keys).runFrames(options.settleFrames??8);
    stages.push({label,display:calc.displayText()});
  }
  return stages;
}

function runPrepared(calc,options={}) {
  options=normalized(options);
  const before=fullMsPages(calc),beforeRegisters=registers(calc),beforeProgram=program(calc);
  let stage='',stages=[],seen=new Set();
  const record=label=>{stage=label;};
  const traced=trace(calc,c=>{
    stages=finish(c,options,record);record('done');c.runFrames(3);
  },{extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
    ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
      return first||[0xEE,0xE7,0xD4,0xD6,0xAD,0xA8,0xA9,0xAC].includes(e.ip);}});
  aligned(calc);
  return {calc,options,stages,traced,before,after:fullMsPages(calc),
    beforeRegisters,afterRegisters:registers(calc),beforeProgram,afterProgram:program(calc)};
}

function run(options={}) {
  options=normalized(options);
  return runPrepared(marker.prepare(options),options);
}

if(require.main===module) {
  const r=run(process.argv[2]?JSON.parse(process.argv[2]):{});
  console.log(JSON.stringify({options:r.options,stages:r.stages,before:r.before,after:r.after,
    p2:r.afterRegisters[2],msUnchanged:JSON.stringify(r.before)===JSON.stringify(r.after),
    programUnchanged:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram)},null,2));
}
module.exports={run,runPrepared,finish,normalized};
