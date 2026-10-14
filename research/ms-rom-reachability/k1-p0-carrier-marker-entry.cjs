#!/usr/bin/env node
'use strict';
// Causal comparison of the exponent-entry marker writer, not a phase search.
const {MK61,aligned,trace}=require('./probe_ee_ring_source.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
function run(value='0') {
  const c=new MK61();c.pressSequence([...value.replace('.',',')]).runFrames(8);
  c.pressSequence(['K','-']).runFrames(8);aligned(c);
  const t=trace(c,c=>c.press('ВП').runFrames(8),{extraIps:Array.from({length:256},(_,i)=>i),fullState:true});
  const es=t.events,start=es.findIndex(e=>e.ip===0x9C),stop=es.findIndex((e,i)=>i>=start&&e.ip===0xE7);
  return {value,path:es.slice(start,stop+2).map(e=>({ip:e.ip.toString(16),slot:e.slot,a:raw(e.r,0),
    r2:e.r[2],r5:e.r[5],r8:e.r[8],r11:e.r[11],s:e.s,s1:e.s1,l:e.l,next:e.nextIp.toString(16)}))};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2]),null,2));
module.exports={run};
