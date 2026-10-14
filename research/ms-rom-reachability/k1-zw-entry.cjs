#!/usr/bin/env node
'use strict';
// ENTER first preserves P7 in visible X; a real-control RCL8 then pushes
// V/W/Q/P7, moving the hidden marker to W without losing the displaced P7.
// Entry only: no clean exit or universal numeric/timing claim.
const deep=require('./k1-z-backed-deep-entry.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const defaults={...deep.defaults,fullUpper:['-3.1415926E42','9022','9033','9044'],
  deepTail:[['K','0'],['В↑'],['П→X','8']],deepTailPhases:[1,0,0]};
function finish(c,o={},record=()=>{}) {
  o={...defaults,...o};deep.finish(c,o,record);
  for(const [i,keys] of (o.afterW??[]).entries()) {
    record('w/tail-phase-'+i);c.runFrames(o.afterWPhases?.[i]??0);
    stack.act(c,record,'w/tail-'+i,keys);
  }
}
const run=(o={})=>frame.run({defaults,finish},o);
const traced=(o={})=>{
  o={...defaults,...o};
  return cap.run(o,finish,['clone-prefix','clone-sign','after-clone-0','rotate/reserve','rotate/tail-0',
    'deep/prepare','deep/clone',...[0,1,2,3,4].map(i=>'deep/marker-'+i),
    ...o.deepTail.map((_,i)=>'deep/tail-'+i),...(o.afterW??[]).map((_,i)=>'w/tail-'+i)]);
};
if(require.main===module) {
  const r=run(JSON.parse(process.env.K1_ZW_OPTIONS||'{}'));
  console.log(JSON.stringify(r.rows.filter(e=>e.stage.startsWith('deep/tail')||e.stage.startsWith('w/')||
    e.stage==='immediate'||e.stage==='done').map(({stage,phase,values,missing})=>({stage,phase,values,missing})),null,2));
}
module.exports={defaults,finish,run,traced};
