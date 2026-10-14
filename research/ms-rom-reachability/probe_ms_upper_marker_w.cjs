#!/usr/bin/env node
'use strict';
// Structural experiment, NOT a working writer. Move the false marker
// farther into lower Ms while using known negative formatter sources.
// Upper data preservation and actual marker placement must be inspected.
const fixture=require('./prepare_ms_full_upper_fixture.cjs');
const two=require('./probe_ms_two_markers.cjs');
const push=require('./probe_ms_p9_push.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
function prepare(o={}) {
  const c=fixture.prepare({stress:true,fullUpper:['1111','2222','3333','4444'],...o});
  inputLiteral(c,'-1.2345678E-42');c.pressSequence(['X→П','9']).runFrames(8);
  push.finish(c,{phaseOffset:0});
  for(const key of o.mirrorSource===false?['8']:['8','1']) {
    inputLiteral(c,o.shiftSource??'-1.2345678E-42');c.pressSequence(['X→П',key]).runFrames(8);
  }
  if(o.visibleSource!==undefined) {
    inputLiteral(c,o.visibleSource);c.pressSequence(['X→П','3']).runFrames(8);
  }
  if(o.programShift) {
    // A separate native fixture: run the last recall as program code,
    // to test whether its normal formatter is still executed.
    c.pressSequence(['В/О','F','ВП','П→X','8','С/П','F','/-/','В/О']).runFrames(8);
    require('node:assert/strict').deepEqual(program(c).slice(0,2),[0x68,0x50]);
  }
  if(o.formatterBypass580) {
    const {installArithmetic,rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
    installArithmetic(c,{input:'1E72',multiplier:'1.0000005E4',store:3});
    c.pressSequence(['В/О','С/П']).runFrames(12);aligned(c);
    require('node:assert/strict').equal(rawMemoryRegister(c,3),'580010000005');
    c.pressSequence(['F','/-/','Сx','В↑','В↑','В↑','+']).runFrames(8);
  }
  return aligned(c);
}
function finish(c,o={},record=()=>{}) {
  return two.finish(c,{...o,shifts:o.programShift?1:2,keepP8:true,zeroKey:'8',reads:false,
    tailActions:o.programShift?[['tail-run',['С/П'],20]]:o.tailActions??[]},record);
}
function runPrepared(c,o={}) {
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  let stage='',seen=new Set();
  const traced=trace(c,calc=>{finish(calc,o,label=>{stage=label;});stage='done';calc.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      eventFilter:ip=>stage==='done'||stage.startsWith('shift-')||stage.startsWith('tail-')||
        [0x9C,0xD5,0xD6,0xDE,0xEE,0xE7,0xE9,0xA7,0xA8,0xA9,0xA2,0xA3,0x47].includes(ip),
      otherChipsAt:()=>stage.startsWith('tail-'),
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xD6,0xEE,0xE7,0xE9,0xA9,0xA2,0xA3,0x47].includes(e.ip)||
          [0x4E,0x2A,0x39].includes(e.otherChips?.[4].ip);}});
  aligned(c);return {calc:c,options:o,traced,before,beforeRegisters,beforeProgram,
    after:fullMsPages(c),afterRegisters:registers(c),afterProgram:program(c)};
}
const run=(o={})=>runPrepared(prepare(o),o);
function brief(r) {
  const es=r.traced.events;
  return {options:r.options,before:r.before,after:r.after,
    program:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    paths:es.filter(e=>(e.stage.startsWith('shift-')||e.stage.startsWith('tail-'))&&
      [0x9C,0xD6,0xEE,0xE7,0xE9,0xA9,0x47].includes(e.ip))
      .map(e=>[e.stage,e.command,e.ip.toString(16),e.slot,two.raw(e.m,0),two.raw(e.r,0),e.nextIp.toString(16)]),
    starts:es.filter(e=>e.ring&&(e.stage.startsWith('shift-')||e.stage==='done'))
      .filter((e,i,a)=>!i||e.stage!==a[i-1].stage)
      .map(e=>({stage:e.stage,words:Object.fromEntries(['X','Y','Z','T',...Object.keys(r.before)].map(n=>[n,two.raw(e.ring[n])]))}))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,brief};
