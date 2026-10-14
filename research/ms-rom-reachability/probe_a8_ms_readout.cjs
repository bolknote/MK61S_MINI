#!/usr/bin/env node
'use strict';
// A finite, native Ms-readout construction. No state injection, saved-state
// import, ROM edits, or phase synchronization between its key groups.
const {prepare,finish}=require('./probe_a8_marker_route.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const registers=c=>Array.from({length:15},(_,i)=>rawMemoryRegister(c,i));
const program=c=>Array.from({length:105},(_,i)=>c.readCommand(i));

function recover(calc,{settleFrames=8,skipLastX=false,autoRecovery=true}={},record=()=>{}) {
  const stages=[];
  const actions=[...(autoRecovery?[['auto-prefix',['F']],['auto-readout',['/-/']]]:[]),
    ...(skipLastX?[]:[['read-v-remove-marker',['F','В↑']],
      ['save-v',['X→П','2']],['restore-u',['↔']]]),
    ['save-u',['X→П','9']],['clear-stack',['Сx','В↑','В↑','В↑','+']]];
  for(const [label,keys] of actions) {
    record(label);calc.pressSequence(keys).runFrames(settleFrames);
    const k=calc.ik1302;
    stages.push({label,display:calc.displayText(),pc:k.r[31]+16*k.r[34],
      ip:k.r[36]+16*k.r[39],r2:k.r[2],r5:k.r[5],r23:k.r[23]});
  }
  return stages;
}

function normalized(options) {
  return {values:['111','222','333','444'],seedLowDigit:0,clearKey:'8',
    ...options,markerLifts:1,captureProgram:false};
}

function runPrepared(calc,options={}) {
  options=normalized(options);
  const before=fullMsPages(calc),beforeRegisters=registers(calc),beforeProgram=program(calc);
  let stage='',stages=[],seen=new Set();
  const record=label=>{stage=label;};
  const traced=trace(calc,c=>{
    stages.push(...finish(c,options,record));
    stages.push(...recover(c,options,record));
    record('done');c.runFrames(3);
  },{extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
    ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
      return first||[0xAC,0xEE,0xE7,0xAD,0xA8,0xA9,0xD4,0xBE,0x63,0xC9,0x67,0x06].includes(e.ip);}});
  aligned(calc);
  return {calc,options,stages,traced,before,after:fullMsPages(calc),
    beforeRegisters,afterRegisters:registers(calc),beforeProgram,afterProgram:program(calc)};
}

function run(options={}) {
  options=normalized(options);
  return runPrepared(prepare(options),options);
}

if(require.main===module) {
  const options=process.argv[2]?JSON.parse(process.argv[2]):{};
  const r=run(options);
  console.log(JSON.stringify({options:r.options,stages:r.stages,before:r.before,after:r.after,
    p2:r.afterRegisters[2],p9:r.afterRegisters[9],
    msReads:r.traced.events.filter(e=>e.ip===0xEE&&['U','V','W','Q','P7','P8'].includes(e.slot))
      .map(e=>({stage:e.stage,slot:e.slot,raw:e.raw})),
    programUnchanged:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram)},null,2));
}
module.exports={recover,run,runPrepared,registers,program};
