#!/usr/bin/env node
'use strict';
// Experimental replacement of the pending request by user opcode 28h.
// The IK1303 decoder prefix is quiet, but whole three-chip preservation,
// placement at Q and a subsequent upper write must be tested separately.
const load=require('./probe_ms_clone_load_x.cjs');
const clone=require('./probe_ms_marker_clone_w.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
function finish(c,o={},record=()=>{}) {
  const result=load.finish(c,{...o,tailActions:undefined},record);
  for(let i=0;i<(o.neutralAttempts??3);i++) {
    record('clone-quiet-'+i);
    if(i)c.runFrames(o.gapFrames??1);
    c.pressSequence(['K','×']).runFrames(o.settleFrames??8);
  }
  for(const [i,keys] of (o.afterQuiet??[['F',',']]).entries()) {
    record('clone-quiet-after-'+i);c.pressSequence(keys).runFrames(o.settleFrames??8);
  }
  return result;
}
const prepare=(o={})=>load.prepare({sourceValue:'-1.234E-42',...o});
const run=(o={})=>clone.runPrepared(prepare(o),o,finish);
function brief(r) {
  const stages=r.traced.events.filter(e=>e.ring).filter((e,i,all)=>i===0||e.stage!==all[i-1].stage);
  return {options:r.options,display:r.traced.display,before:r.before,after:r.after,result:r.result,
    stages:stages.filter(e=>e.stage.startsWith('clone-quiet')||e.stage==='done')
      .map(e=>({stage:e.stage,words:Object.fromEntries(['X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'].map(n=>[n,raw(e.ring[n])]))})),
    paths:r.traced.events.filter(e=>e.stage.startsWith('clone-quiet')&&[0x9C,0xEE,0xE9,0xA3,0xE7,0x47].includes(e.ip))
      .map(e=>[e.stage,e.command,e.ip.toString(16),e.slot,raw(e.m),raw(e.r,0)])};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,run,brief};
