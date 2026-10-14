#!/usr/bin/env node
'use strict';
// Experimental control-word prevention/repair. The complete native prefix
// runs unchanged; the observer retains only the last restoration stages.
// No synchronizing getters or alignment occur between live stages.
const base=require('./probe_ms_quiet_upper_restore.cjs');
const four=require('./probe_ms_quiet_read_four.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
function options(o={}) {
  const suffix=base.suffix.slice();
  if(o.insertAfterD) suffix.splice(9,0,...o.insertAfterD);
  return {...o,afterFour:[...suffix,...(o.afterRestore??[])]};
}
const prepare=base.prepare;
const finish=(c,o={},record=()=>{})=>four.finish(c,options(o),record);
function run(o={}) {
  const c=prepare(o),before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  let stage='',seen=new Set(),result;
  const settings={extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:false,
    eventFilter:()=>stage==='done'||Number(stage.slice('clone-quiet-after-'.length))>=22,
    otherChipsAt:()=>true,
    ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);return first||
      [0x9C,0xD4,0xD6,0xEE,0xE7,0xE9,0xA9,0xA2,0xA3,0x47].includes(e.ip)||
      [0x4E,0x2A,0x39,0x27].includes(e.otherChips?.[4].ip);}};
  const traced=trace(c,calc=>{
    result=finish(calc,o,label=>{stage=label;settings.allWrites=Number(label.slice('clone-quiet-after-'.length))>=22;});
    stage='done';settings.allWrites=true;calc.runFrames(3);
  },settings);
  aligned(c);return {calc:c,options:o,before,beforeRegisters,beforeProgram,result,traced,
    after:fullMsPages(c),afterRegisters:registers(c),afterProgram:program(c)};
}
function brief(r) {
  const es=r.traced.events;
  return {after:r.after,registers:r.afterRegisters,display:r.calc.displayText(),
    program:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    tail:es.filter(e=>[0x9C,0xD6,0xEE,0xE7,0xE9,0xA3].includes(e.ip))
      .map(e=>({stage:e.stage,command:e.command,ip:e.ip.toString(16),slot:e.slot,m:raw(e.m),r:raw(e.r,0)})),
    end:Object.fromEntries(Object.entries(es.find(e=>e.stage==='done'&&e.ring).ring).map(([k,v])=>[k,raw(v)]))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={options,prepare,finish,run,brief};
