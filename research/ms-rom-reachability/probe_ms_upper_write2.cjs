#!/usr/bin/env node
'use strict';
// Conditional native upper-pair writer. Ordinary B -> Ms P7, A -> Ms P8.
// Three separately re-entered ROM operations; native preparation between them.
// Lower Ms and ordinary scratch are deliberately modified; not full K1.
const assert=require('node:assert/strict');
const fixture=require('./prepare_ms_upper_fixture.cjs');
const compact=require('./probe_ms_upper_compact_exit.cjs');
const one=require('./probe_ms_upper_write1.cjs');
const two=require('./probe_ms_two_markers.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
function prepare(o={}) {
  const c=(o.fullUpper?require('./prepare_ms_full_upper_fixture.cjs'):fixture).prepare(o);
  for(const [value,key] of [[o.fifth??'-9.8765432E99','/-/'],[o.sixth??'6.5432109E-23',',']]) {
    inputLiteral(c,value);c.pressSequence(['X→П',key]);
  }
  return aligned(c);
}
function moveOptions(o={}) {
  const result=compact.optionsFor(o);
  // Its stale formatter may replace P7; only the result in P8 matters here.
  result.tailActions=result.tailActions.filter(a=>a[0]!=='upper-prime'&&(o.legacyCopy||a[0]!=='upper-copy-fifth'));
  return result;
}
function finish(c,o={},record=()=>{}) {
  assert.ok([0,1,2].includes(o.phaseOffset??0));c.runFrames(o.phaseOffset??0);
  const local={...o,phaseOffset:0,postPointer:'110'},wait=o.settleFrames??8;
  const under=name=>label=>record(name+'/'+label);
  one.prepareScratch(c,local,under('sixth-to-top'));
  one.finish(c,local,under('sixth-to-top'));
  compact.prepareScratch(c,local,under('sixth-to-second'));
  two.finish(c,moveOptions(local),under('sixth-to-second'));
  record('copy-fifth-source');c.pressSequence(['П→X','/-/','X→П',',']).runFrames(wait);
  one.prepareScratch(c,local,under('fifth-to-top'));
  one.finish(c,local,under('fifth-to-top'));
  return c;
}
function runPrepared(c,o={}) {
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  assert.equal(beforeRegisters[3],'000000000000');
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
function brief(r) {
  const names=['P7','P8','P9','P10'];
  return {before:r.before,after:r.after,inputs:{fifth:r.beforeRegisters[11],sixth:r.beforeRegisters[10]},
    registers:r.afterRegisters,programPreserved:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    boundaries:r.traced.events.filter(e=>e.ring&&['sixth-to-second/compact-payload-marker',
      'copy-fifth-source','done'].includes(e.stage))
      .filter((e,i,all)=>all.findIndex(x=>x.stage===e.stage)===i)
      .map(e=>({stage:e.stage,upper:Object.fromEntries(names.map(n=>[n,two.raw(e.ring[n])]))})),
    end:Object.fromEntries(['X','Y','Z','T'].map(n=>[n,two.raw(r.traced.events.findLast(e=>e.ring).ring[n])]))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,brief,moveOptions};
