#!/usr/bin/env node
'use strict';
// Structurally selected alternative before the Z/W push: primary Cx may
// erase the disposable V marker without a destructive A3 request.
const zw=require('./k1-zw-entry.cjs');
const defaults={...zw.defaults,deepTail:[['K','0'],['В↑'],['Сx']],deepTailPhases:[1,0,0]};
const finish=(c,o={},record=()=>{})=>zw.finish(c,{...defaults,...o},record);
const run=(o={})=>zw.run({...defaults,...o});
const traced=(o={})=>zw.traced({...defaults,...o});
if(require.main===module) {
  const r=run(JSON.parse(process.env.K1_ZV_CLEAR_OPTIONS||'{}'));
  console.log(JSON.stringify(r.rows.filter(e=>e.stage.startsWith('deep/tail')||['immediate','done'].includes(e.stage))
    .map(({stage,phase,values,missing})=>({stage,phase,values,missing})),null,2));
}
module.exports={defaults,finish,run,traced};
