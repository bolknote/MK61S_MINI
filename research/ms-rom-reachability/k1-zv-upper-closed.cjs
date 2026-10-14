#!/usr/bin/env node
'use strict';
// Remove the hidden V marker before RCL8. Its upper push then preserves
// the real/Z geometry of the checked max/equal-drop/LastX closing suffix.
const close=require('./k1-zv-nop-closed.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const defaults={...close.defaults,afterW:[['П→X','8'],...close.defaults.afterW],
  afterWPhases:[0,...close.defaults.afterWPhases]};
const finish=(c,o={},record=()=>{})=>close.finish(c,{...defaults,...o},record);
const run=(o={})=>frame.run({defaults,finish},o);
const traced=(o={})=>close.traced({...defaults,...o});
if(require.main===module) {
  const r=run({verifyExit:true,...JSON.parse(process.env.K1_ZV_UPPER_OPTIONS||'{}')});
  console.log(JSON.stringify(r.rows.filter(e=>e.stage.startsWith('w/')||e.stage.startsWith('post/')||['immediate','done'].includes(e.stage))
    .map(({stage,phase,values,missing})=>({stage,phase,values,missing})),null,2));
}
module.exports={defaults,finish,run,traced};
