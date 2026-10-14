#!/usr/bin/env node
'use strict';
// Experimental non-shifting W placement: E9 with marker U would copy X
// to W. Native reachability, source and preservation are NOT assumed.
const fixture=require('./probe_ms_upper_marker_w.cjs');
const two=require('./probe_ms_two_markers.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
function prepare(o={}) {
  const c=fixture.prepare({...o,mirrorSource:false});
  if(o.independentP8!==undefined) {
    inputLiteral(c,o.independentP8);c.pressSequence(['X→П','8']).runFrames(8);
  }
  return aligned(c);
}
function finish(c,o={},record=()=>{}) {
  const sourceKey=o.sourceKey??'1';
  const attempts=Array.from({length:o.swaps??3},(_,i)=>[
    ...(o.refreshSource?[
      ...Array.from({length:4},(_,j)=>['clone-refresh'+i+'-'+j,['П→X','3']]),
      ...Array.from({length:o.sourceCopies??1},(_,j)=>['clone-reload'+i+'-'+j,['П→X',sourceKey]])]:[]),
    ['clone-swap'+i,['↔']]]).flat();
  return two.finish(c,{...o,shifts:0,keepP8:true,reads:false,payloadCopies:[sourceKey,...(o.sourceMirror?[o.sourceMirror]:[])],
    tailActions:[...Array.from({length:o.visibleLifts??3},(_,i)=>['clone-lift'+i,['П→X','3']]),
      ...Array.from({length:o.sourceCopies??1},(_,j)=>['clone-source'+(j?'-'+j:''),['П→X',sourceKey]]),
      ...attempts,
      ...(o.tailActions??[])]},record);
}
function runPrepared(c,o={},operation=finish) {
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  let stage='',seen=new Set(),result;
  const traced=trace(c,calc=>{result=operation(calc,o,label=>{stage=label;});stage='done';calc.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      eventFilter:ip=>stage==='done'||stage.startsWith('clone-')||
        [0x9C,0xD6,0xEE,0xE7,0xE9,0xA7,0xA8,0xA9,0xA2,0xA3,0x47].includes(ip),
      otherChipsAt:()=>stage.startsWith('clone-'),
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xD6,0xEE,0xE7,0xE9,0xA9,0xA2,0xA3,0x47].includes(e.ip)||
          [0x4E,0x2A,0x39].includes(e.otherChips?.[4].ip);}});
  aligned(c);return {calc:c,options:o,traced,result,before,beforeRegisters,beforeProgram,
    after:fullMsPages(c),afterRegisters:registers(c),afterProgram:program(c)};
}
const run=(o={})=>runPrepared(prepare(o),o);
function brief(r) {
  const es=r.traced.events;
  return {options:r.options,before:r.before,after:r.after,registers:r.afterRegisters,
    program:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    entries:es.filter(e=>e.ip===0xE9).map(e=>[e.stage,e.command,e.slot,two.raw(e.r,0)]),
    paths:es.filter(e=>e.stage==='clone-source'&&[0xD6,0xEE,0xE7,0xA9,0x47].includes(e.ip))
      .map(e=>[e.stage,e.command,e.ip.toString(16),e.slot,two.raw(e.m,0),two.raw(e.r,0),e.nextIp.toString(16)]),
    starts:es.filter(e=>e.ring&&(e.stage.startsWith('clone-')||e.stage==='done'))
      .filter((e,i,a)=>!i||e.stage!==a[i-1].stage)
      .map(e=>({stage:e.stage,words:Object.fromEntries(['X','Y','Z','T',...Object.keys(r.before)].map(n=>[n,two.raw(e.ring[n])]))}))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,brief};
