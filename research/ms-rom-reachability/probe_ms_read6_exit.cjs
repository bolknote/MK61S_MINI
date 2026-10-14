#!/usr/bin/env node
'use strict';
// Compose four lower backups with the compact guarded upper reader/exit.
// All preparation and transfers are keys. No alignment/getters between stages.
// Outputs U/V/W/Q/P7/P8 -> P1/P6/B/D/P8/A. restoreLower:true restores U/V/W/Q.
// P3=0 and the existing nonnegative-U-exponent domain are still required.
// Ms P7/P8 are NOT restored; the last two words are NOT read. Not full K1.
const assert=require('node:assert/strict');
const fixture=require('./prepare_ms_upper_fixture.cjs');
const lower=require('./probe_ms_wq_repair.cjs');
const upper=require('./probe_ms_upper_compact_exit.cjs');
const push=require('./probe_ms_p9_push.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const prepare=(o={})=>fixture.prepare(o);
function finish(c,o={},record=()=>{}) {
  assert.ok([0,1,2].includes(o.phaseOffset??0));
  c.runFrames(o.phaseOffset??0);
  const local={...o,phaseOffset:0},wait=o.settleFrames??8;
  lower.finish(c,{...local,restore:true},label=>record('backup-four/'+label));
  // Preserve W before reusing P6 for V. P4/P5/P7 then become scratch.
  for(const [source,destination] of [['6','/-/'],['7','Сx'],['4','1'],['5','6']]) {
    record('relocate-'+source+'-to-'+destination);
    c.pressSequence(['П→X',source,'X→П',destination]).runFrames(wait);
  }
  upper.prepareScratch(c,local,record);
  upper.finish(c,local,record);
  if(o.restoreLower) {
    for(const source of ['Сx','/-/','6','1']) {
      record('restore-source-'+source);
      c.pressSequence(['П→X',source,'X→П','9']).runFrames(wait);
      push.finish(c,local,label=>record('restore-lower-'+source+'/'+label));
    }
  }
  return c;
}
function runPrepared(c,o={}) {
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  assert.equal(beforeRegisters[3],'000000000000');
  let stage='',seen=new Set();
  const shortIps=new Set([0xAC,0xEE,0xDE,0x9C,0xC9,0xD4,0xD6,0xAA,0xAB,0xAD,
    0xA4,0xA5,0xA2,0xA3,0xED,0xE5,0xE6,0xE8,0xE7,0xA7,0xA8,0xA9,0x47]);
  const traced=trace(c,calc=>{finish(calc,o,label=>{stage=label;});stage='done';calc.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),
      eventFilter:ip=>stage==='done'||stage.startsWith('upper-')||shortIps.has(ip),
      fullState:true,allWrites:true,
      otherChipsAt:()=>stage==='upper-swap',
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xEE,0xE7,0xD4,0xA5,0xA3,0xA9,0x47].includes(e.ip)||
          [0x4E,0x2A,0x39].includes(e.otherChips?.[4].ip);}});
  aligned(c);return {calc:c,options:o,traced,before,after:fullMsPages(c),beforeRegisters,
    afterRegisters:registers(c),beforeProgram,afterProgram:program(c)};
}
const run=(o={})=>runPrepared(prepare(o),o);
function brief(r) {
  return {options:r.options,before:r.before,after:r.after,registers:r.afterRegisters,
    programPreserved:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    end:Object.fromEntries(['X','Y','Z','T'].map(n=>[n,raw(r.traced.events.findLast(e=>e.ring).ring[n])])),
    indirect:r.traced.events.filter(e=>e.stage.startsWith('upper-after-')&&[0xD6,0xD4,0xE7].includes(e.ip))
      .map(e=>[e.stage,e.ip.toString(16),e.slot,raw(e.m,0),raw(e.r,0),e.nextIp.toString(16)])};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,brief};
