#!/usr/bin/env node
'use strict';
// Reserve original p from Q before consuming the T marker with RCL0.
// Accepted 9C(Z) is the proved desired entry; native timing is separate.
const nop=require('./k1-vw-nop-read.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const defaults={...nop.defaults,fullUpper:['-1E-99','9022','9033','9044'],reserveLeadPhase:1};
function finish(c,o={},record=()=>{}) {
  nop.finish(c,{...o,afterNop:[]},record);
  record('reserve/phase');c.runFrames(o.reserveLeadPhase??1);
  stack.act(c,record,'reserve/lastx',['F','В↑'],o.reserveWait??8);
  for(const [i,keys] of (o.afterReserve??[]).entries()) {
    record('reserve/tail-phase-'+i);c.runFrames(o.afterReservePhases?.[i]??0);
    stack.act(c,record,'reserve/tail-'+i,keys,o.afterReserveWaits?.[i]??8);
  }
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign','nop/read','reserve/lastx',
    ...(o.afterReserve??[]).map((_,i)=>'reserve/tail-'+i)]);
module.exports={defaults,finish,run};
