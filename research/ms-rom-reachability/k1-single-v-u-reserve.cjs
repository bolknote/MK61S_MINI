#!/usr/bin/env node
'use strict';
// Conditional reserve of the live U word before an upper-bank request.
// The earlier Z marker directs LastX to U; a short upper word preserves
// the new X through late formatting. No normal exit is asserted here.
const deep=require('./k1-repack-deep-clone-probe.cjs');
const single=require('./k1-single-v-entry-check.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...deep.defaults,...single.defaults,fullUpper:['-1E-99','9022','9033','9044'],reserveLeadPhase:1};
function finish(c,o={},record=()=>{}) {
  deep.finish(c,{...o,...single.defaults,afterClonePhase:o.reserveLeadPhase??1,
    afterClone:[['F','В↑']],afterCloneWaits:[8]},record);
  for(const [i,keys] of (o.afterReserve??[]).entries()) {
    if(o.afterReservePhases?.[i]){record('u-reserve/phase-'+i);c.runFrames(o.afterReservePhases[i]);}
    stack.act(c,record,'u-reserve/tail-'+i,keys,o.afterReserveWaits?.[i]??8);
  }
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign','after-clone-0',...(o.afterReserve??[]).map((_,i)=>'u-reserve/tail-'+i)]);
module.exports={defaults,finish,run};
