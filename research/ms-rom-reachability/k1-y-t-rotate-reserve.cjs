#!/usr/bin/env node
'use strict';
// Conditional V reserve with all 23 originals back in stored words and Z
// as the only extra marker. Original ROM/core; keyboard actions only.
const entry=require('./k1-y-t-entry.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...entry.defaults,afterClone:[['F',',']]};
function finish(c,o={},record=()=>{}) {
  entry.finish(c,{...defaults,...o,afterClone:[['F',',']]},record);
  if(o.stopAfterRotate)return;
  stack.act(c,record,'rotate/reserve',['K','0']);
  for(const [i,keys] of (o.afterReserve??[]).entries()) {
    if(o.afterReservePhases?.[i]){record('rotate/tail-phase-'+i);c.runFrames(o.afterReservePhases[i]);}
    stack.act(c,record,'rotate/tail-'+i,keys,o.afterReserveWaits?.[i]??8);
  }
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign','after-clone-0','rotate/reserve',...(o.afterReserve??[]).map((_,i)=>'rotate/tail-'+i)]);
module.exports={defaults,finish,run};
