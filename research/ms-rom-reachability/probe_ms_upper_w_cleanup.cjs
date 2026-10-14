#!/usr/bin/env node
'use strict';
// Research only: stage a visible marker after the conditional upper cycle.
// P2/P3 copies are intentionally reused; b/c remain in P7/P6 respectively.
// Neither W removal nor a complete exchange is assumed by this probe.
const four=require('./probe_ms_quiet_read_four.cjs');
const restore=require('./probe_ms_quiet_upper_restore.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
function options(o={}) {
  const s=restore.suffix;
  return {...o,afterFour:[...s.slice(0,4),['Сx'],['X→П','9'],
    s[4],...(o.stageB?[['X→П','6']]:[]),s[5],
    ...(o.stageB?[['П→X','Сx'],['X→П',',']]:[]),
    ...s.slice(6,8),['X→П','8'],...s.slice(8),
    ['Сx'],...(o.zeroBeforeMarker?[['П→X','9']]:[]),['П→X','8'],...(o.cleanupTail??[])]};
}
const prepare=four.prepare;
const finish=(c,o={},record=()=>{})=>four.finish(c,options(o),record);
function run(o={}) {
  const calc=prepare(o),before=fullMsPages(calc),beforeRegisters=registers(calc),beforeProgram=program(calc);
  if(o.observe===false) {
    const result=finish(calc,o);calc.runFrames(3);aligned(calc);
    return {calc,options:o,result,before,beforeRegisters,beforeProgram,
      after:fullMsPages(calc),afterRegisters:registers(calc),afterProgram:program(calc)};
  }
  let stage='',result;const seen=new Set();
  const active=()=>stage==='done'||stage.startsWith('clone-quiet-after-')&&Number(stage.slice(18))>=(o.traceFrom??19);
  const traced=trace(calc,c=>{result=finish(c,o,s=>{stage=s;});stage='done';c.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
      get allWrites(){return active();},eventFilter:active,otherChipsAt:active,
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xD6,0xEE,0xE7,0xE9,0xA9,0xA2,0xA3,0x47].includes(e.ip)||[0x4E,0x2A,0x39].includes(e.otherChips?.[4].ip);}});
  aligned(calc);return {calc,options:o,traced,result,before,beforeRegisters,beforeProgram,
    after:fullMsPages(calc),afterRegisters:registers(calc),afterProgram:program(calc)};
}
if(require.main===module)console.log(JSON.stringify(require('./probe_ms_clone_quiet_request.cjs').brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={options,prepare,finish,run};
