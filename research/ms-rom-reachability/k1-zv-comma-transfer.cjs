#!/usr/bin/env node
'use strict';
// The cached comma editor replaces the class-sensitive NOP at real/Z/V.
// Fixed whole-frame waits only; no payload reads, ticks or state restoration.
const zw=require('./k1-zw-entry.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...zw.defaults,fullUpper:['402','9022','9033','9044'],
  deepTail:[['K','0'],['В↑']],deepTailPhases:[1,0],
  afterTransfer:[],afterTransferPhases:[]};
function finish(c,o={},record=()=>{}) {
  o={...defaults,...o};zw.finish(c,o,record);
  stack.act(c,record,'comma',[','],9);
  stack.act(c,record,'comma/transfer',['П→X','8']);
  for(const [i,keys] of o.afterTransfer.entries()) {
    record('comma/tail-phase-'+i);c.runFrames(o.afterTransferPhases[i]??0);
    stack.act(c,record,'comma/tail-'+i,keys);
  }
}
const run=(o={})=>frame.run({defaults,finish},o);
const traced=(o={})=>{
  o={...defaults,...o};return cap.run(o,finish,
    ['clone-prefix','clone-sign','after-clone-0','rotate/reserve','rotate/tail-0',
     'deep/prepare','deep/clone',...[0,1,2,3,4].map(i=>'deep/marker-'+i),
     ...o.deepTail.map((_,i)=>'deep/tail-'+i),'comma','comma/transfer',
     ...o.afterTransfer.map((_,i)=>'comma/tail-'+i)]);
};
if(require.main===module) {
  const r=run(JSON.parse(process.env.K1_COMMA_OPTIONS||'{}'));
  console.log(JSON.stringify(r.rows.filter(e=>e.stage.startsWith('comma')||['immediate','done'].includes(e.stage))
    .map(({stage,phase,values,missing})=>({stage,phase,values,missing})),null,2));
}
module.exports={defaults,finish,run,traced};
