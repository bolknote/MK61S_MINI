#!/usr/bin/env node
'use strict';
// Candidate after V capture/reentry. P0 may be overwritten because its v
// still exists in Ms V. No other ordinary register is disposable here.
const capture=require('./k1-bank-v-capture.cjs');
const retained=require('./k1-bank-marker-tail-check.cjs');
const defaults=[['X→П','0'],['П→X','0'],['F'],['В↑']];
function finish(c,o={},record=()=>{}) {
  retained.operation(c,{...o,tail:undefined,recoverCapture:true},record);
  for(const [i,keys] of (o.carrierActions??defaults).entries()) {
    record('carrier-'+i);c.pressSequence(keys).runFrames(o.settleFrames??8);
  }
  return c;
}
const run=(o={})=>capture.run(o,finish);
function brief(r) {
  const b=capture.brief(r);
  const raw=require('./probe_ms_two_markers.cjs').raw;
  return {...b,stages:r.traced.events.filter(e=>e.ring&&r.traced.events.find(x=>x.stage===e.stage)===e)
    .filter(e=>e.stage.startsWith('carrier-')||e.stage==='done')
    .map(e=>({stage:e.stage,words:Object.fromEntries(['X1','X','Y','Z','T','U','V','W','Q'].map(n=>[n,raw(e.ring[n])]))})),
    paths:r.traced.events.filter(e=>e.stage.startsWith('carrier-'))
      .filter(e=>[0x9C,0xEE,0xE7,0xE9,0xD4,0xD6,0xA9].includes(e.ip))
      .map(e=>[e.stage,e.command,e.ip.toString(16),e.slot,e.raw,
        raw(e.r,0),e.nextIp.toString(16)])};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={defaults,finish,run,brief};
