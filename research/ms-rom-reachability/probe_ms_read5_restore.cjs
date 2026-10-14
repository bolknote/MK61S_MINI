#!/usr/bin/env node
'use strict';
// Conditional five-word readout candidate. Only native keys mutate state.
// P3=0; outputs U/V/W/Q -> P4..P7, Ms P7 -> ordinary P0.
// Scratch: P2 (fixed eraser), P8 (zero), P9 (ends original U).
const assert=require('node:assert/strict');
const lower=require('./probe_ms_wq_repair.cjs');
const markers=require('./probe_ms_two_markers.cjs');
const push=require('./probe_ms_p9_push.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const prepare=(options={})=>options.enriched?require('./prepare_ms_upper_fixture.cjs').prepare(options):lower.prepare(options);
function finish(calc,options={},record=()=>{}) {
  assert.ok([0,1,2].includes(options.phaseOffset??0));
  calc.runFrames(options.phaseOffset??0);
  const local={...options,phaseOffset:0},wait=options.settleFrames??8;
  const under=name=>label=>record(name+'/'+label);
  lower.finish(calc,{...local,restore:true},under('backup-four'));
  record('prepare-eraser');inputLiteral(calc,options.eraser??'-1.2345678E-42');
  calc.pressSequence(['X→П','2']).runFrames(wait);
  markers.finish(calc,{phaseOffset:0,settleFrames:wait,markerFrames:options.markerFrames??12,
    shifts:1,reads:true},under('fifth-word'));
  for(const [label,keys] of [
    ['erase-v',['П→X','2']],
    ['remove-visible-z',['П→X','3']],['remove-visible-t',['П→X','3']],
    ['clear-after-erase',['Сx','В↑','В↑','В↑','+']]]) {
    record(label);calc.pressSequence(keys).runFrames(wait);
  }
  for(const source of ['7','6','5','4']) {
    record('source-p'+source);calc.pressSequence(['П→X',source,'X→П','9']).runFrames(wait);
    push.finish(calc,local,under('restore-p'+source));
  }
  return calc;
}
function runPrepared(calc,options={}) {
  const before=fullMsPages(calc),beforeRegisters=registers(calc),beforeProgram=program(calc);
  assert.equal(beforeRegisters[3],'000000000000');
  let stage='',seen=new Set();
  const traced=trace(calc,c=>{finish(c,options,label=>{stage=label;});stage='done';c.runFrames(3);},
    {extraIps:[0x9C,0xC9,0xD4,0xD6,0xAA,0xAB,0xAD,0xA4,0xA5,0xED,0xE5,0xE6,0xE8,0xE7,0xA7,0xA8,0xA9,0x47],
      fullState:true,allWrites:true,
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xE7,0xA9,0xEE,0xD4,0xA5,0x47].includes(e.ip);}});
  aligned(calc);return {calc,options,before,after:fullMsPages(calc),beforeRegisters,
    afterRegisters:registers(calc),beforeProgram,afterProgram:program(calc),traced};
}
const run=(options={})=>runPrepared(prepare(options),options);
if(require.main===module) {
  const r=run(process.argv[2]?JSON.parse(process.argv[2]):{});
  console.log(JSON.stringify({options:r.options,before:r.before,after:r.after,registers:r.afterRegisters,
    programPreserved:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    erasers:r.traced.events.filter(e=>e.stage==='erase-v'&&e.ip===0xE7).map(e=>({slot:e.slot,old:e.raw}))},null,2));
}
module.exports={prepare,finish,runPrepared,run};
