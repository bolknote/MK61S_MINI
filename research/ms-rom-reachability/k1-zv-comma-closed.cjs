#!/usr/bin/env node
'use strict';
// CHS reads the temporary R8 in V; a long reciprocal supplies a class-0
// operand without numeric entry and its destructive fresh-digit stack lift.
const transfer=require('./k1-zv-comma-transfer.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...transfer.defaults,
  afterTransfer:[['/-/'],['F','/'],['K','9'],['-'],['F','В↑'],['П→X','1'],['П→X','1']],
  afterTransferPhases:[0,0,2,1,0,0,0]};
function finish(c,o={},record=()=>{}) {
  o={...defaults,...o};transfer.finish(c,o,record);
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
     ...o.deepTail.map((_,i)=>'deep/tail-'+i),'comma','comma/transfer',
     ...o.afterTransfer.map((_,i)=>'comma/tail-'+i),'post/manual','post/zero','post/program']);
};
if(require.main===module) {
  const r=run({verifyExit:true,...JSON.parse(process.env.K1_COMMA_OPTIONS||'{}')});
  console.log(JSON.stringify(r.rows.filter(e=>e.stage.startsWith('comma')||e.stage.startsWith('post/')||['immediate','done'].includes(e.stage))
    .map(({stage,phase,values,missing})=>({stage,phase,values,missing})),null,2));
}
module.exports={defaults,finish,run,traced};
