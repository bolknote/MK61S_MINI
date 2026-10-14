#!/usr/bin/env node
'use strict';
// Primary NOP releases V after the upper reader, using whole-frame pauses.
// No secondary request or destructive stack push is needed for the release.
const zw=require('./k1-zw-entry.cjs');
const defaults={...zw.defaults,deepTail:[['K','0'],['В↑'],['K','0']],deepTailPhases:[1,0,2]};
const finish=(c,o={},record=()=>{})=>zw.finish(c,{...defaults,...o},record);
const run=(o={})=>zw.run({...defaults,...o});
const traced=(o={})=>zw.traced({...defaults,...o});
if(require.main===module) {
  const r=run(JSON.parse(process.env.K1_ZV_NOP_OPTIONS||'{}'));
  console.log(JSON.stringify(r.rows.filter(e=>e.stage.startsWith('w/')||['immediate','done'].includes(e.stage))
    .map(({stage,phase,values,missing})=>({stage,phase,values,missing})),null,2));
}
module.exports={defaults,finish,run,traced};
