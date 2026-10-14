#!/usr/bin/env node
'use strict';
// Isolate keyboard construction of a marker/pointer without raw state input.
const capture=require('./k1-bank-v-capture.cjs');
const recovered=require('./k1-bank-marker-tail-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
function finish(c,o={},record=()=>{}) {
  recovered.operation(c,{...o,recoverCapture:true},record);
  for(const [i,key] of (o.markerTail??[',','0','1','ВП','2']).entries()) {
    record('mantissa-'+i);c.press(key).runFrames(8);
  }
}
const run=(o={})=>capture.run(o,finish);
function brief(r) {
  const first=new Set();
  return r.traced.events.filter(e=>{
    if(!e.ring||(!e.stage.startsWith('mantissa-')&&e.stage!=='done')||first.has(e.stage))return false;
    first.add(e.stage);return true;
  }).map(e=>({stage:e.stage,command:e.command,
    words:Object.fromEntries(['X','Y','Z','T','U','V','W','Q'].map(n=>[n,raw(e.ring[n])]))}));
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={finish,run,brief};
