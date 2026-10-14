#!/usr/bin/env node
'use strict';
// Bounded experiment: replace the saved-marker recall with native creation
// or Last-X. The supposedly freed P2/P7/E contain independent data.
const one=require('./probe_ms_upper_write1.cjs');
const two=require('./probe_ms_two_markers.cjs');
const {inputLiteral}=require('./probe_c8_payload.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
function prepare(o={}) {
  const c=one.prepare(o);
  for(const [key,value] of [['2','-9.8765432E99'],['7','-1E-99'],['В↑','1.2345678E-42']]) {
    inputLiteral(c,value);c.pressSequence(['X→П',key]);
  }
  return aligned(c);
}
function optionsFor(o={}) {
  const result=one.optionsFor(o),at=result.tailActions.findIndex(a=>a[0]==='upper-after-4');
  const replacement=o.mode==='last-x'?[['inline-last-x',['F','В↑']]]:
    ['Сx','K','-','ВП','K','0'].map((key,i)=>['inline-marker-'+i,[key],o.markerFrames??12]);
  result.tailActions.splice(at,1,...replacement);return result;
}
const finish=(c,o={},record=()=>{})=>two.finish(c,optionsFor(o),record);
const runPrepared=(c,o={})=>two.runPrepared(c,optionsFor(o));
const run=(o={})=>runPrepared(prepare(o),o);
function brief(r) {
  const es=r.traced.events;
  return {before:r.before,after:r.after,registers:r.afterRegisters,
    kept:[2,7,14].map(i=>[i,r.beforeRegisters[i],r.afterRegisters[i]]),
    program:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),primitives:r.traced.primitives,
    boundaries:es.filter(e=>e.ring).filter((e,i,all)=>all.findIndex(x=>x.stage===e.stage)===i)
      .filter(e=>e.stage.startsWith('inline-')||e.stage.startsWith('upper-after-')||e.stage==='done')
      .map(e=>({stage:e.stage,words:Object.fromEntries(['X1','X','Y','Z','T','U','V','P7','P8','P9','P10'].map(n=>[n,two.raw(e.ring[n])]))})),
    paths:es.filter(e=>(e.stage.startsWith('inline-')||['upper-after-5','upper-after-6'].includes(e.stage))&&
      [0x9C,0xD6,0xEE,0xE7].includes(e.ip)).map(e=>[e.stage,e.ip.toString(16),e.slot,e.raw,two.raw(e.r,0),e.nextIp.toString(16)])};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,optionsFor,finish,runPrepared,run,brief};
