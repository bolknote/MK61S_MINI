#!/usr/bin/env node
'use strict';
// Research candidate: remove V, then make the T-adjacent U header fail
// the primary accepted-9C predicate before issuing a shifted addition.
// No preservation or exact-absorption claim is implied by this driver.
const reserve=require('./k1-single-v-u-reserve.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...reserve.defaults};
function finish(c,o={},record=()=>{}) {
  reserve.finish(c,{...o,afterReserve:[['K','9'],['K','9'],['+']],
    afterReservePhases:[0,1,0],afterReserveWaits:[8,8,8]},record);
  for(const [i,keys] of (o.afterAdd??[]).entries()) {
    if(o.afterAddPhases?.[i]){record('masked-add/phase-'+i);c.runFrames(o.afterAddPhases[i]);}
    stack.act(c,record,'masked-add/tail-'+i,keys,o.afterAddWaits?.[i]??8);
  }
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign','after-clone-0',
    ...[0,1,2].map(i=>'u-reserve/tail-'+i),
    ...(o.afterAdd??[]).map((_,i)=>'masked-add/tail-'+i)]);
module.exports={defaults,finish,run};
