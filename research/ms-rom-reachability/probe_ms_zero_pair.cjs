#!/usr/bin/env node
'use strict';
// Native upper-pair writer with P0 shared between zero data and late pointer.
// B -> Ms P7, A -> Ms P8; ordinary P3 is arbitrary retained payload.
// The middle move does not need a BC capture: with C=7 it would overwrite P7.
const assert=require('node:assert/strict');
const pair=require('./probe_ms_upper_write2.cjs');
const zero=require('./probe_ms_zero_p0.cjs');
const two=require('./probe_ms_two_markers.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
function prepare(o={}) {
  const c=pair.prepare(o);
  inputLiteral(c,o.payload??'-7.654321E23');c.pressSequence(['X→П','3']);
  return aligned(c);
}
function moveOptions(o={}) {
  const result=zero.optionsFor(o);
  result.tailActions=result.tailActions.filter(a=>!['upper-prime','upper-after-0'].includes(a[0]));
  result.tailActions.find(a=>a[0]==='upper-swap')[1]=['↔'];
  return result;
}
function finish(c,o={},record=()=>{}) {
  assert.ok([0,1,2].includes(o.phaseOffset??0));
  assert.ok(!o.directSource&&!o.legacyCopy,'this composition uses the compensated source and no unused copy');
  c.runFrames(o.phaseOffset??0);
  const local={...o,phaseOffset:0},wait=o.settleFrames??8;
  const under=name=>label=>record(name+'/'+label);
  zero.prepareScratch(c,local,under('sixth-to-top'));
  zero.finish(c,local,under('sixth-to-top'));
  zero.prepareScratch(c,local,under('sixth-to-second'));
  two.finish(c,moveOptions(local),under('sixth-to-second'));
  record('copy-fifth-source');c.pressSequence(['П→X','/-/','X→П',',']).runFrames(wait);
  zero.prepareScratch(c,local,under('fifth-to-top'));
  zero.finish(c,local,under('fifth-to-top'));
  return c;
}
function runPrepared(c,o={}) {
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  let stage='',seen=new Set();
  const short=new Set([0xAC,0xEE,0xDE,0x9C,0xC9,0xD4,0xD6,0xE7,0xA8,0xA9,0xA5,0x47]);
  const traced=trace(c,calc=>{finish(calc,o,label=>{stage=label;});stage='done';calc.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      eventFilter:ip=>stage==='done'||stage.includes('/upper-')||short.has(ip),
      otherChipsAt:()=>stage.endsWith('/upper-swap'),
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xEE,0xE7,0xA9,0xA5,0xD4,0xD6,0x47].includes(e.ip)||
          [0x3A,0x4E,0x2A,0x39].includes(e.otherChips?.[4].ip);}});
  aligned(c);return {calc:c,options:o,traced,before,after:fullMsPages(c),beforeRegisters,
    afterRegisters:registers(c),beforeProgram,afterProgram:program(c)};
}
const run=(o={})=>runPrepared(prepare(o),o);
if(require.main===module)console.log(JSON.stringify(pair.brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,moveOptions};
