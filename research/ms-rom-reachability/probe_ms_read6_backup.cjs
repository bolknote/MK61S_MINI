#!/usr/bin/env node
'use strict';
// Six-word backup candidate, NOT a restored-Ms reader or a K1 exchange.
// Native keys only, no alignment/getters between the lower and upper stages.
const assert=require('node:assert/strict');
const lower=require('./probe_ms_wq_repair.cjs');
const upper=require('./probe_ms_upper_indirect.cjs');
const fixture=require('./prepare_ms_upper_fixture.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const prepare=(o={})=>o.enriched===false?lower.prepare(o):fixture.prepare(o);
function finish(calc,o={},record=()=>{}) {
  assert.ok([0,1,2].includes(o.phaseOffset??0));
  calc.runFrames(o.phaseOffset??0);
  const local={...o,phaseOffset:0},wait=o.settleFrames??8;
  lower.finish(calc,{...local,restore:true},label=>record('backup-four/'+label));
  record('preserve-v-in-a');
  calc.pressSequence(['П→X','5','X→П',',']).runFrames(wait);
  record('prepare-two-pointers');inputLiteral(calc,'1');
  calc.pressSequence(['X→П','5','X→П','ВП']).runFrames(wait);
  upper.finish(calc,local,record);
  return calc;
}
function runPrepared(calc,o={}) {
  const before=fullMsPages(calc),beforeRegisters=registers(calc),beforeProgram=program(calc);
  assert.equal(beforeRegisters[3],'000000000000');
  let stage='',seen=new Set();
  const traced=trace(calc,c=>{finish(c,o,label=>{stage=label;});stage='done';c.runFrames(3);},
    {extraIps:[0x9C,0xC9,0xD4,0xD6,0xAA,0xAB,0xAD,0xA4,0xA5,0xA2,0xA3,0xED,0xE5,0xE6,0xE8,0xE7,0xA7,0xA8,0xA9,0x47],
      fullState:true,allWrites:true,
      otherChipsAt:o.traceSecondary?()=>stage.startsWith('upper-'):undefined,
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xEE,0xE7,0xD4,0xA5,0xA3].includes(e.ip)||
          (o.traceFormatterExit&&[0xA9,0x47].includes(e.ip));}});
  aligned(calc);return {calc,options:o,traced,before,after:fullMsPages(calc),beforeRegisters,
    afterRegisters:registers(calc),beforeProgram,afterProgram:program(calc)};
}
const run=(o={})=>runPrepared(prepare(o),o);
function brief(r) {
  return {options:r.options,before:r.before,after:r.after,registers:r.afterRegisters,
    programPreserved:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    pointerReads:r.traced.events.filter(e=>e.stage==='upper-after-0'&&e.ip===0xD6)
      .map(e=>({slot:e.slot,next:e.nextIp.toString(16)}))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,brief};
