#!/usr/bin/env node
'use strict';
// Upper rotation with the original lower u/q in the opposite visible order.
// This is not a clean exit: u remains in T and q in Z.
const swapped=require('./k1-upper-exit-structure-probe.cjs').swapped;
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...swapped.defaults,clonePrefix:['F'],cloneKeys:[','],clonePhase:2};
function finish(c,o={},record=()=>{}) {
  swapped.finish(c,{...o,clonePrefix:['F'],cloneKeys:[','],clonePhase:2,
    afterClonePhase:0,afterClone:[['0'],['K','0'],['0'],['F',',']],
    afterCloneWaits:[8,10,9,8]},record);
  if(o.afterUpperPhase){record('after-upper-phase');c.runFrames(o.afterUpperPhase);}
  for(const [i,keys] of (o.afterUpper??[]).entries())
    stack.act(c,record,'after-upper-'+i,keys,o.afterUpperWaits?.[i]??8);
}
function run(o={}) {
  o={...defaults,...o};
  return cap.run(o,finish,['clone-prefix','clone-sign',
    ...Array.from({length:4},(_,i)=>'after-clone-'+i),
    ...(o.afterUpper??[]).map((_,i)=>'after-upper-'+i)]);
}
module.exports={defaults,finish,run};
if(require.main===module) {
  const frame=require('./k1-frame-boundary-probe.cjs');
  const r=frame.run(module.exports,JSON.parse(process.argv[2]??'{}'));
  console.log(JSON.stringify(frame.brief(r).rows.filter(x=>
    x.stage.startsWith('after-')||x.stage==='done'),null,2));
}
