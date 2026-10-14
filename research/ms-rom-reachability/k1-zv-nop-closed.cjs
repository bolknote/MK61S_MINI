#!/usr/bin/env node
'use strict';
// Conditional closing suffix after the primary NOP release. Max preserves
// the selected operand, equal subtraction duplicates T, and LastX stores it.
// Numerical/order and timing limits belong to the accompanying checks.
const nop=require('./k1-zv-nop-release.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...nop.defaults,afterW:[['K','9'],['-'],['F','В↑'],['П→X','1'],['П→X','1']],
  afterWPhases:[0,1,0,0,0]};
function finish(c,o={},record=()=>{}) {
  o={...defaults,...o};nop.finish(c,o,record);
  if(o.verifyExit){
    stack.act(c,record,'post/manual',['Сx','2','В↑','3','+']);
    stack.act(c,record,'post/zero',['Сx']);
    stack.act(c,record,'post/program',['В/О','С/П'],12);
  }
}
const run=(o={})=>frame.run({defaults,finish},o);
const traced=(o={})=>{
  o={...defaults,...o};return cap.run(o,finish,
    ['clone-prefix','clone-sign','after-clone-0','rotate/reserve','rotate/tail-0',
     'deep/prepare','deep/clone',...[0,1,2,3,4].map(i=>'deep/marker-'+i),
     ...o.deepTail.map((_,i)=>'deep/tail-'+i),...o.afterW.map((_,i)=>'w/tail-'+i),
     'post/manual','post/zero','post/program']);
};
if(require.main===module) {
  const r=run({verifyExit:true,...JSON.parse(process.env.K1_ZV_CLOSED_OPTIONS||'{}')});
  console.log(JSON.stringify(r.rows.filter(e=>e.stage.startsWith('w/')||e.stage.startsWith('post/')||['immediate','done'].includes(e.stage))
    .map(({stage,phase,values,missing})=>({stage,phase,values,missing})),null,2));
}
module.exports={defaults,finish,run,traced};
